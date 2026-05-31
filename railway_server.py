"""
railway_server.py
=================
Railway deployment entry point.
Runs the Flask web check-in server ONLY (no GUI/CustomTkinter).
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

# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_in_queue(student_id: str) -> dict | None:
    """
    Search both priority_heap and normal_queue for a patient by student_id.
    Returns a dict with keys: position, total, queue_type
    or None if not found.
    Priority patients always rank before normal ones, so their effective
    position is their index within the heap (sorted by insertion order).
    Normal patients' effective position starts after all priority patients.
    """
    # Priority heap: sort by _order key so position reflects insertion order
    priority_patients = [p for _, p in sorted(_qm.priority_heap)]
    for i, p in enumerate(priority_patients):
        if getattr(p, "student_id", None) == student_id:
            return {
                "position": i + 1,
                "total": _qm.total_count(),
                "queue_type": "urgent",
            }

    # Normal queue
    for i, p in enumerate(_qm.normal_queue):
        if getattr(p, "student_id", None) == student_id:
            return {
                "position": len(priority_patients) + i + 1,
                "total": _qm.total_count(),
                "queue_type": "normal",
            }

    return None


# ── Stub callbacks (no GUI) ───────────────────────────────────────────────────

def _enqueue(student_id: str, reason: str, urgent: bool) -> dict:
    from models import Patient

    p = Patient(
        name=student_id,
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
      { status: "waiting" | "not_found", position, total, queue_type }
    """
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

web_server._enqueue_callback = _enqueue
web_server._status_callback = _get_status
web_server._queue_callback = _qm.to_dict

log.info("Starting Flask on 0.0.0.0:%d …", C.FLASK_PORT)
web_server.flask_app.run(
    host="0.0.0.0",
    port=C.FLASK_PORT,
    debug=False,
    use_reloader=False,
    threaded=True,
)