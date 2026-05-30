"""
persistence.py
==============
JSON-based queue state persistence.
Auto-saves on every mutation; loads on startup.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).parent / "data" / "queue_state.json"


def save(queue_manager, path: Path = DEFAULT_PATH) -> None:
    """
    Serialize both queues to JSON.
    Writes atomically via a temp file to avoid corruption on crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(queue_manager.to_dict(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)   # atomic on POSIX; best-effort on Windows
    except OSError as exc:
        log.error("Failed to save queue state: %s", exc)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def load(queue_manager, path: Path = DEFAULT_PATH) -> bool:
    """
    Restore queue state from JSON.
    Returns True on success, False if the file is missing or corrupt.
    """
    if not path.exists():
        log.info("No saved state found at %s — starting fresh.", path)
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        queue_manager.load_dict(data)
        total = queue_manager.total_count()
        log.info("Restored %d patient(s) from %s", total, path)
        return True
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.error("Corrupt save file (%s) — starting fresh. Error: %s", path, exc)
        return False
