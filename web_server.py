"""
web_server.py
=============
Flask check-in + live queue status endpoints.
v6: QR-first flow — student enters their number, sees live queue position.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from flask import Flask, request, jsonify

log = logging.getLogger(__name__)

_enqueue_callback: Callable | None = None
_status_callback:  Callable | None = None
_queue_callback:   Callable | None = None

flask_app = Flask(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Check-in page  (QR destination)
# ─────────────────────────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clinic Check-In</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: linear-gradient(135deg, #0a4a48 0%, #0e7c7b 50%, #14a5a3 100%);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .card {
    background: #ffffff;
    border-radius: 20px;
    padding: 40px 36px;
    width: 100%;
    max-width: 420px;
    box-shadow: 0 20px 60px rgba(0,0,0,.25);
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 28px;
  }
  .logo-icon {
    width: 48px; height: 48px;
    background: #0e7c7b;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 24px;
  }
  .logo h1 { font-size: 1.25rem; color: #0e7c7b; font-weight: 700; line-height: 1.2; }
  .logo p  { font-size: 0.8rem;  color: #7a9ca5; margin-top: 2px; }
  .divider { height: 1px; background: #e4eef2; margin-bottom: 28px; }
  label {
    display: block;
    font-size: 0.8rem;
    font-weight: 600;
    color: #5a7184;
    letter-spacing: .04em;
    text-transform: uppercase;
    margin-bottom: 6px;
    margin-top: 20px;
  }
  label:first-of-type { margin-top: 0; }
  input, textarea {
    width: 100%;
    padding: 12px 16px;
    background: #f7fafc;
    border: 1.5px solid #d4e2ec;
    border-radius: 10px;
    color: #1a2b3c;
    font-size: 1rem;
    font-family: inherit;
    outline: none;
    transition: border-color .2s, box-shadow .2s;
  }
  input:focus, textarea:focus {
    border-color: #0e7c7b;
    box-shadow: 0 0 0 3px rgba(14,124,123,.12);
    background: #fff;
  }
  input::placeholder, textarea::placeholder { color: #a8bfcc; }
  textarea { resize: vertical; min-height: 80px; }
  .urgent-row {
    display: flex; align-items: center; gap: 12px;
    background: #fff5e6;
    border: 1.5px solid #fddcac;
    border-radius: 10px;
    padding: 12px 16px;
    margin-top: 20px;
    cursor: pointer;
  }
  .urgent-row input[type=checkbox] {
    width: 18px; height: 18px;
    accent-color: #e74c3c;
    flex-shrink: 0;
    background: transparent;
    border: none;
    padding: 0;
    box-shadow: none;
  }
  .urgent-row span { font-size: .9rem; color: #c0392b; font-weight: 600; }
  button {
    margin-top: 28px;
    width: 100%;
    padding: 14px;
    background: #0e7c7b;
    color: #fff;
    font-weight: 700;
    font-size: 1rem;
    font-family: inherit;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    transition: background .2s, transform .1s;
    letter-spacing: .02em;
  }
  button:hover  { background: #0a5c5b; }
  button:active { transform: scale(.98); }
  .hint {
    text-align: center;
    font-size: .78rem;
    color: #a8bfcc;
    margin-top: 16px;
  }
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <div class="logo-icon">🏥</div>
    <div>
      <h1>School Clinic</h1>
      <p>Patient Self Check-In</p>
    </div>
  </div>
  <div class="divider"></div>
  <form method="POST" action="/">
    <label>Student Number *</label>
    <input name="student_id" placeholder="e.g. 2024-12345" required autofocus>
    <label>Reason for Visit *</label>
    <textarea name="reason" placeholder="Briefly describe your concern…" required></textarea>
    <label class="urgent-row" style="text-transform:none;letter-spacing:0;margin-top:20px;">
      <input type="checkbox" name="urgent" id="urg">
      <span>🚨 &nbsp;Emergency / Urgent case</span>
    </label>
    <button type="submit">Join Queue →</button>
  </form>
  <p class="hint">Your position will be shown after joining.</p>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Live status page  (served after successful check-in)
# ─────────────────────────────────────────────────────────────────────────────

STATUS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Queue Status</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: linear-gradient(135deg, #0a4a48 0%, #0e7c7b 50%, #14a5a3 100%);
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    padding: 24px;
  }
  .card {
    background: #fff;
    border-radius: 20px;
    padding: 40px 36px;
    width: 100%;
    max-width: 420px;
    box-shadow: 0 20px 60px rgba(0,0,0,.25);
    text-align: center;
  }
  .logo { display:flex; align-items:center; gap:12px; margin-bottom:24px; justify-content:center; }
  .logo-icon { width:44px;height:44px;background:#0e7c7b;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px; }
  .logo h1 { font-size:1.1rem;color:#0e7c7b;font-weight:700; }
  .divider { height:1px;background:#e4eef2;margin-bottom:28px; }

  .student-badge {
    display: inline-block;
    background: #eaf7f6;
    border: 1.5px solid #b2ddd9;
    color: #0e7c7b;
    font-size: 1.1rem;
    font-weight: 700;
    padding: 8px 20px;
    border-radius: 40px;
    letter-spacing: .05em;
    margin-bottom: 32px;
  }

  .position-ring {
    width: 160px; height: 160px;
    margin: 0 auto 20px;
    border-radius: 50%;
    background: #eaf7f6;
    border: 6px solid #0e7c7b;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    position: relative;
    transition: border-color .4s, background .4s;
  }
  .position-ring.serving  { border-color: #2ecc71; background: #eafaf1; }
  .position-ring.not-found{ border-color: #a8bfcc; background: #f7fafc; }

  .pos-num {
    font-size: 3.5rem;
    font-weight: 800;
    color: #0e7c7b;
    line-height: 1;
    transition: color .4s;
  }
  .pos-num.serving   { color: #2ecc71; }
  .pos-num.not-found { color: #a8bfcc; }
  .pos-label { font-size: .8rem; color: #7a9ca5; font-weight: 600; letter-spacing:.06em; text-transform:uppercase; margin-top:4px; }

  .status-text { font-size: 1.15rem; font-weight: 700; color: #1a2b3c; margin-bottom: 8px; }
  .status-sub  { font-size: .88rem; color: #7a9ca5; line-height: 1.5; }

  .queue-pill {
    display: inline-block;
    padding: 5px 16px;
    border-radius: 40px;
    font-size: .78rem;
    font-weight: 700;
    letter-spacing: .05em;
    text-transform: uppercase;
    margin-top: 18px;
  }
  .pill-urgent { background:#fff2ee; color:#e74c3c; border:1.5px solid #f5bdb3; }
  .pill-normal { background:#eaf7f6; color:#0e7c7b; border:1.5px solid #b2ddd9; }

  .pulse { animation: pulse 2s ease-in-out infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

  .refresh-note { font-size:.75rem; color:#c0d0da; margin-top:24px; }
  a.back { display:inline-block;margin-top:12px;color:#0e7c7b;font-weight:600;text-decoration:none;font-size:.9rem; }
  a.back:hover { text-decoration:underline; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <div class="logo-icon">🏥</div>
    <h1>School Clinic Queue</h1>
  </div>
  <div class="divider"></div>

  <div class="student-badge" id="sid-badge">⋯</div>

  <div class="position-ring" id="ring">
    <div class="pos-num" id="pos-num">—</div>
    <div class="pos-label" id="pos-label">Position</div>
  </div>

  <div class="status-text" id="status-text">Checking status…</div>
  <div class="status-sub"  id="status-sub"></div>
  <div id="queue-pill"></div>

  <p class="refresh-note pulse" id="refresh-note">🔄 Auto-refreshing every 3 seconds…</p>
  <br>
  <a class="back" href="/">← New check-in</a>
</div>
<script>
  const studentId = window.location.pathname.split('/').pop();
  document.getElementById('sid-badge').textContent = '🎓 ' + studentId;

  function update(data) {
    const ring    = document.getElementById('ring');
    const posNum  = document.getElementById('pos-num');
    const posLab  = document.getElementById('pos-label');
    const stText  = document.getElementById('status-text');
    const stSub   = document.getElementById('status-sub');
    const pill    = document.getElementById('queue-pill');

    ring.className = 'position-ring';
    posNum.className = 'pos-num';

    if (data.status === 'serving') {
      ring.classList.add('serving');
      posNum.classList.add('serving');
      posNum.textContent = '✓';
      posLab.textContent = 'Now Serving';
      stText.textContent = 'You are being attended to!';
      stSub.textContent  = 'Please proceed to the clinic.';
      pill.innerHTML = '';
      document.getElementById('refresh-note').style.display = 'none';

    } else if (data.status === 'waiting') {
      posNum.textContent = '#' + data.position;
      posLab.textContent = 'in queue';
      const total = data.total;
      stText.textContent = data.position === 1
        ? 'You are next! 🎉'
        : 'You are in the queue.';
      stSub.textContent  = total + ' patient' + (total !== 1 ? 's' : '') + ' total in queue.';
      const isUrgent = data.queue_type === 'urgent';
      pill.innerHTML = isUrgent
        ? '<span class="queue-pill pill-urgent">🚨 Urgent / Priority Queue</span>'
        : '<span class="queue-pill pill-normal">📋 Normal Queue</span>';

    } else {
      ring.classList.add('not-found');
      posNum.classList.add('not-found');
      posNum.textContent = '?';
      posLab.textContent = 'Status';
      stText.textContent = 'Not found in queue.';
      stSub.textContent  = 'You may have already been served, or your session has expired.';
      pill.innerHTML = '';
    }
  }

  function poll() {
    fetch('/api/status/' + encodeURIComponent(studentId))
      .then(r => r.json())
      .then(update)
      .catch(() => {});
  }

  poll();
  setInterval(poll, 3000);
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────────────────────────────────────────

@flask_app.route("/", methods=["GET", "POST"])
def checkin():
    if request.method == "POST":
        sid    = (request.form.get("student_id") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        urgent = bool(request.form.get("urgent"))

        if sid and reason and _enqueue_callback:
            # name == student_id (no separate name in v6)
            _enqueue_callback(sid, sid, reason, urgent)

        from flask import redirect
        return redirect(f"/status/{sid}")

    return HTML_PAGE


@flask_app.route("/status/<student_id>")
def status_page(student_id):
    return STATUS_PAGE


@flask_app.route("/api/status/<student_id>")
def api_status(student_id):
    if _status_callback:
        data = _status_callback(student_id)
        return jsonify(data)
    return jsonify({"status": "unavailable"})


@flask_app.route("/api/queue")
def api_queue():
    """Returns the full queue state for the desktop app to poll."""
    if _queue_callback:
        return jsonify(_queue_callback())
    return jsonify({"priority": [], "normal": [], "total": 0})


# ─────────────────────────────────────────────────────────────────────────────
#  Start
# ─────────────────────────────────────────────────────────────────────────────

def start(
    enqueue_callback: Callable,
    status_callback:  Callable | None = None,
    queue_callback:   Callable | None = None,
    host: str = "0.0.0.0",
    port: int = 5000,
) -> None:
    global _enqueue_callback, _status_callback, _queue_callback
    _enqueue_callback = enqueue_callback
    _status_callback  = status_callback
    _queue_callback   = queue_callback

    t = threading.Thread(
        target=lambda: flask_app.run(host=host, port=port,
                                     debug=False, use_reloader=False),
        daemon=True,
        name="FlaskCheckin",
    )
    t.start()
    log.info("Web check-in server started on http://%s:%d", host, port)
