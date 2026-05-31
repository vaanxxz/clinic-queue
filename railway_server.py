"""
railway_server.py
=================
Railway deployment entry point.
Runs the Flask web check-in server ONLY (no GUI/CustomTkinter).

FIX SUMMARY
-----------
  • _now_serving is now kept in sync with _qm.now_serving (single source
    of truth). On startup it is restored from the persisted JSON via
    QueueManager.load_dict() which now carries now_serving.
  • /api/serve  : sets _qm.now_serving alongside the module-level
    _now_serving so they never diverge.
  • /api/sync_queue : now reads "now_serving" from the posted snapshot and
    applies it to both _now_serving and _qm.now_serving, so an undo that
    clears the serving state is correctly reflected on the web frontend.
  • /api/queue  : returns _qm.to_dict() which now includes now_serving, so
    the desktop app's _apply_remote_queue() can sync serving state.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Ensure data dir exists ────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Override config for Railway ───────────────────────────────────────────────
import config as C
C.DATA_DIR = DATA_DIR
C.FLASK_HOST = "0.0.0.0"
C.FLASK_PORT = int(os.environ.get("PORT", 5000))

# ── Boot queue manager ────────────────────────────────────────────────────────
from queue_manager import QueueManager
import persistence

_qm = QueueManager()
persistence.load(_qm)
log.info("Queue manager ready.")

# FIX: _now_serving is now derived from _qm.now_serving (restored by load_dict).
# We keep it as a module-level alias so existing code reads it naturally.
# Both are always updated together — see the helper below.

def _set_now_serving(value: dict | None) -> None:
    """Update both the module alias and _qm.now_serving atomically."""
    global _now_serving
    _now_serving = value
    _qm.now_serving = value

_now_serving: dict | None = _qm.now_serving   # initialised from persisted state

# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_in_queue(student_id: str) -> dict | None:
    """
    Search both priority_heap and normal_queue for a patient by student_id.
    Returns a dict with keys: position, total, queue_type
    or None if not found.
    """
    priority_patients = [p for _, p in sorted(_qm.priority_heap)]
    for i, p in enumerate(priority_patients):
        if getattr(p, "student_id", None) == student_id:
            return {
                "position": i + 1,
                "total": _qm.total_count(),
                "queue_type": "urgent",
            }

    for i, p in enumerate(_qm.normal_queue):
        if getattr(p, "student_id", None) == student_id:
            return {
                "position": len(priority_patients) + i + 1,
                "total": _qm.total_count(),
                "queue_type": "normal",
            }

    return None


# ── Stub callbacks (no GUI) ───────────────────────────────────────────────────

def _enqueue(name: str, student_id: str, reason: str, urgent: bool) -> dict:
    from models import Patient

    p = Patient(
        name=name or student_id,
        student_id=student_id,
        reason=reason,
        urgent=urgent,
        timestamp=datetime.now(),
    )

    _qm.enqueue(p)
    persistence.save(_qm)

    found = _find_in_queue(student_id)
    pos = found["position"] if found else None

    log.info("Enqueued %s (urgent=%s) -> pos %s", student_id, urgent, pos)
    return {"ok": True, "position": pos, "student_id": student_id}


def _get_status(student_id: str) -> dict:
    """
    Returns a status dict that matches what the JS frontend expects:
      { status: "serving" | "waiting" | "not_found", position, total, queue_type }
    """
    if _now_serving and _now_serving.get("student_id") == student_id:
        return {
            "status": "serving",
            "student_id": student_id,
            "position": 0,
            "total": _qm.total_count(),
        }

    found = _find_in_queue(student_id)

    if found:
        return {
            "status": "waiting",
            "position": found["position"],
            "total": found["total"],
            "queue_type": found["queue_type"],
        }

    return {
        "status": "not_found",
        "position": None,
        "total": _qm.total_count(),
    }


# ── Wire callbacks then run Flask on the MAIN thread (blocks) ─────────────────
import web_server


@web_server.flask_app.route("/api/enqueue", methods=["POST"])
def api_enqueue():
    """
    Called by the desktop app when a patient is added locally (manual entry).
    Adds the patient to Railway's queue so both sides stay in sync.
    Body JSON: { name, student_id, reason, urgent }
    """
    from flask import request, jsonify

    data = request.get_json(silent=True) or {}
    name       = data.get("name", "").strip()
    student_id = data.get("student_id", "").strip()
    reason     = data.get("reason", "").strip()
    urgent     = bool(data.get("urgent", False))

    if not student_id or not reason:
        return jsonify({"ok": False, "error": "missing student_id or reason"}), 400

    already = _find_in_queue(student_id)
    if already:
        log.info("Skipping duplicate enqueue for %s", student_id)
        return jsonify({"ok": True, "skipped": True})

    result = _enqueue(name or student_id, student_id, reason, urgent)
    return jsonify(result)


@web_server.flask_app.route("/api/serve", methods=["POST"])
def api_serve():
    """
    Called by the desktop app when it serves a patient.
    Removes that patient from Railway's queue and records who is being served.
    Body JSON: { student_id: str }
    """
    from flask import request, jsonify

    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id", "").strip()

    if not student_id:
        return jsonify({"ok": False, "error": "missing student_id"}), 400

    removed = False
    new_heap = []
    import heapq

    new_serving = None

    for order, p in _qm.priority_heap:
        if p.student_id == student_id:
            removed = True
            new_serving = {
                "student_id": p.student_id, "name": p.name,
                "reason": p.reason, "urgent": p.urgent,
            }
        else:
            new_heap.append((order, p))
    _qm.priority_heap = new_heap
    heapq.heapify(_qm.priority_heap)

    if not removed:
        import collections
        new_norm = collections.deque()
        for p in _qm.normal_queue:
            if p.student_id == student_id:
                removed = True
                new_serving = {
                    "student_id": p.student_id, "name": p.name,
                    "reason": p.reason, "urgent": p.urgent,
                }
            else:
                new_norm.append(p)
        _qm.normal_queue = new_norm

    if new_serving is not None:
        _set_now_serving(new_serving)   # FIX: keep _qm.now_serving in sync

    persistence.save(_qm)
    log.info("Serving %s (found_and_removed=%s)", student_id, removed)
    return jsonify({"ok": True, "now_serving": _now_serving})


@web_server.flask_app.route("/api/now_serving")
def api_now_serving():
    """Returns who is currently being served."""
    from flask import jsonify
    return jsonify({"now_serving": _now_serving})


@web_server.flask_app.route("/api/sync_queue", methods=["POST"])
def api_sync_queue():
    """
    Called by the desktop app after an undo to push the corrected queue
    snapshot directly to Railway, bypassing Railway's own undo stack.

    FIX: now reads and applies "now_serving" from the snapshot so that
    undoing a SERVE correctly clears the serving state on Railway too.

    Body JSON: { priority: [...], normal: [...], now_serving: dict|null }
    """
    from flask import request, jsonify
    from models import Patient
    import heapq, collections

    data = request.get_json(silent=True)
    if not data or ("priority" not in data and "normal" not in data):
        return jsonify({"ok": False, "error": "invalid payload"}), 400

    _qm.priority_heap = []
    for d in data.get("priority", []):
        p = Patient.from_dict(d)
        heapq.heappush(_qm.priority_heap, (p._order, p))

    _qm.normal_queue = collections.deque(
        Patient.from_dict(d) for d in data.get("normal", [])
    )

    # FIX: restore now_serving from the undo snapshot
    # The key is present (possibly null/None) in snapshots from the fixed
    # QueueManager.to_dict().  For backward compat we use .get() with a
    # sentinel so old clients that omit the key don't accidentally clear it.
    _MISSING = object()
    raw_serving = data.get("now_serving", _MISSING)
    if raw_serving is not _MISSING:
        _set_now_serving(raw_serving)   # None clears, dict sets

    persistence.save(_qm)
    log.info(
        "Queue synced via undo: %d priority, %d normal, now_serving=%s",
        len(_qm.priority_heap), len(_qm.normal_queue), _now_serving,
    )
    return jsonify({"ok": True})


web_server._enqueue_callback = _enqueue
web_server._status_callback  = _get_status
web_server._queue_callback   = _qm.to_dict   # FIX: to_dict now includes now_serving

log.info("Starting Flask on 0.0.0.0:%d …", C.FLASK_PORT)
web_server.flask_app.run(
    host="0.0.0.0",
    port=C.FLASK_PORT,
    debug=False,
    use_reloader=False,
    threaded=True,
)
