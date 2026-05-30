"""
queue_manager.py
================
Core data-structure logic — no UI dependency.

Data structures used
--------------------
  normal_queue   : collections.deque        — FIFO for regular patients
  priority_heap  : list (via heapq)         — min-heap keyed on _order
  undo_stack     : list                     — stack of (action, patient) tuples
"""

from __future__ import annotations

import collections
import heapq
from typing import Literal

from models import Patient

ActionType = Literal["enqueue", "dequeue", "prioritize"]


class QueueManager:
    """Thread-safe-ish queue manager (single-threaded GUI; no locks needed)."""

    def __init__(self) -> None:
        self.normal_queue:  collections.deque[Patient] = collections.deque()
        self.priority_heap: list[tuple[int, Patient]]  = []
        self.undo_stack:    list[tuple[ActionType, Patient]] = []

    # ── enqueue ──────────────────────────────

    def enqueue(self, patient: Patient) -> None:
        """Route patient to the correct queue and push to undo stack."""
        if patient.urgent:
            heapq.heappush(self.priority_heap, (patient._order, patient))
        else:
            self.normal_queue.append(patient)
        self.undo_stack.append(("enqueue", patient))

    # ── dequeue ──────────────────────────────

    def dequeue(self) -> Patient | None:
        """
        Serve next patient — priority queue always wins.
        Returns None when both queues are empty.
        """
        if self.priority_heap:
            _, patient = heapq.heappop(self.priority_heap)
            self.undo_stack.append(("dequeue", patient))
            return patient

        if self.normal_queue:
            patient = self.normal_queue.popleft()
            self.undo_stack.append(("dequeue", patient))
            return patient

        return None

    # ── prioritize ───────────────────────────

    def prioritize(self, uid: str) -> bool:
        """
        Escalate a normal-queue patient to the priority heap.
        O(n) scan — acceptable at clinic scale (<500 patients).
        """
        for i, p in enumerate(self.normal_queue):
            if p.uid == uid:
                del self.normal_queue[i]
                p.urgent = True
                heapq.heappush(self.priority_heap, (p._order, p))
                self.undo_stack.append(("prioritize", p))
                return True
        return False

    # ── undo ─────────────────────────────────

    def undo(self) -> str:
        """
        Reverse the last action.
        Returns a human-readable description, or '' if nothing to undo.
        """
        if not self.undo_stack:
            return ""

        action, patient = self.undo_stack.pop()

        if action == "enqueue":
            if patient.urgent:
                self.priority_heap = [
                    (o, p) for o, p in self.priority_heap if p.uid != patient.uid
                ]
                heapq.heapify(self.priority_heap)
            else:
                self.normal_queue = collections.deque(
                    p for p in self.normal_queue if p.uid != patient.uid
                )
            return f"Undid ADD — {patient.name} removed from queue"

        if action == "dequeue":
            if patient.urgent:
                heapq.heappush(self.priority_heap, (patient._order, patient))
            else:
                self.normal_queue.appendleft(patient)
            return f"Undid SERVE — {patient.name} restored to queue"

        if action == "prioritize":
            self.priority_heap = [
                (o, p) for o, p in self.priority_heap if p.uid != patient.uid
            ]
            heapq.heapify(self.priority_heap)
            patient.urgent = False
            self.normal_queue.appendleft(patient)
            return f"Undid PRIORITIZE — {patient.name} returned to normal queue"

        return ""

    # ── clear ────────────────────────────────

    def clear(self) -> None:
        self.normal_queue.clear()
        self.priority_heap.clear()
        self.undo_stack.clear()

    # ── read-only views ───────────────────────

    def priority_patients(self) -> list[Patient]:
        """Priority patients sorted by insertion order (stable FIFO within urgents)."""
        return [p for _, p in sorted(self.priority_heap)]

    def normal_patients(self) -> list[Patient]:
        return list(self.normal_queue)

    def total_count(self) -> int:
        return len(self.priority_heap) + len(self.normal_queue)

    def is_empty(self) -> bool:
        return self.total_count() == 0

    # ── serialisation helpers ─────────────────

    def to_dict(self) -> dict:
        return {
            "priority": [p.to_dict() for _, p in sorted(self.priority_heap)],
            "normal":   [p.to_dict() for p in self.normal_queue],
        }

    def load_dict(self, data: dict) -> None:
        """Restore queue state from a previously saved dict."""
        self.clear()
        for d in data.get("priority", []):
            p = Patient.from_dict(d)
            heapq.heappush(self.priority_heap, (p._order, p))
        for d in data.get("normal", []):
            self.normal_queue.append(Patient.from_dict(d))
