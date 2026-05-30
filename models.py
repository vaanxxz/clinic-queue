"""
models.py
=========
Pure data classes — no UI, no I/O.
v6: Student number is the primary identifier. Name is optional.
"""

from __future__ import annotations

import datetime
import uuid


class Patient:
    """Value object representing one clinic patient (identified by student number)."""

    _counter: int = 0

    def __init__(
        self,
        name: str,
        student_id: str,
        reason: str,
        urgent: bool = False,
        *,
        timestamp: datetime.datetime | None = None,
        uid: str | None = None,
        order: int | None = None,
    ) -> None:
        Patient._counter += 1

        raw_sid = student_id.strip()
        self.student_id = raw_sid or self._auto_id()
        # name falls back to student_id so all display code still works
        self.name       = name.strip() or self.student_id
        self.reason     = reason.strip()
        self.urgent     = urgent
        self.timestamp  = timestamp or datetime.datetime.now()
        self.uid        = uid or str(uuid.uuid4())[:8]
        self._order     = order if order is not None else Patient._counter

    # ── helpers ───────────────────────────────

    @staticmethod
    def _auto_id() -> str:
        Patient._counter += 1
        year = datetime.datetime.now().year
        return f"{year}-{Patient._counter:05d}"

    def time_str(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")

    def date_str(self) -> str:
        return self.timestamp.strftime("%b %d, %Y")

    # ── serialisation ─────────────────────────

    def to_dict(self) -> dict:
        return {
            "name":       self.name,
            "student_id": self.student_id,
            "reason":     self.reason,
            "urgent":     self.urgent,
            "timestamp":  self.timestamp.isoformat(),
            "uid":        self.uid,
            "order":      self._order,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Patient":
        return cls(
            name       = d["name"],
            student_id = d["student_id"],
            reason     = d["reason"],
            urgent     = d.get("urgent", False),
            timestamp  = datetime.datetime.fromisoformat(d["timestamp"]),
            uid        = d["uid"],
            order      = d.get("order"),
        )

    def __repr__(self) -> str:
        tag = "URGENT" if self.urgent else "Normal"
        return f"Patient({self.student_id!r}, {tag})"
