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

    # FIX: manual position calculation (replaces missing position_of)
    queue_list = getattr(_qm, "queue", None) or getattr(_qm, "normal_queue", []) or []

    pos = None
    for i, patient in enumerate(queue_list):
        if getattr(patient, "student_id", None) == student_id:
            pos = i + 1
            break

    log.info("Enqueued %s (urgent=%s) -> pos %s", student_id, urgent, pos)
    return {"ok": True, "position": pos, "student_id": student_id}


def _get_status(student_id: str) -> dict:
    queue_list = getattr(_qm, "queue", None) or getattr(_qm, "normal_queue", []) or []

    pos = None
    for i, p in enumerate(queue_list):
        if getattr(p, "student_id", None) == student_id:
            pos = i + 1
            break

    total = _qm.total_count()

    return {
        "student_id": student_id,
        "position": pos,
        "total": total,
        "found": pos is not None,
    }


# ── Wire callbacks then run Flask on the MAIN thread (blocks) ─────────────────
import web_server

web_server._enqueue_callback = _enqueue
web_server._status_callback = _get_status

log.info("Starting Flask on 0.0.0.0:%d …", C.FLASK_PORT)
web_server.flask_app.run(
    host="0.0.0.0",
    port=C.FLASK_PORT,
    debug=False,
    use_reloader=False,
    threaded=True,
)