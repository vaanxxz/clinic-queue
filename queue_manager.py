"""
queue_manager.py  (FIXED)
=========================
Core data-structure logic — no UI dependency.

Key change: undo_stack now stores *full system snapshots* instead of
individual (action, patient) tuples.  This guarantees that:
  • "now_serving" state is captured before every mutation
  • undo always restores the complete prior state (queue + serving)
  • no partial rollbacks, no stale serving display

Data structures
---------------
  normal_queue   : collections.deque        – FIFO for regular patients
  priority_heap  : list (via heapq)         – min-heap keyed on _order
  now_serving    : dict | None              – currently served patient info
  undo_stack     : list[dict]               – list of full-state snapshots
"""

from __future__ import annotations

import collections
import copy
import heapq
from typing import Literal

from models import Patient

ActionType = Literal["enqueue", "dequeue", "prioritize"]


class QueueManager:
    """Thread-safe-ish queue manager (single-threaded GUI; no locks needed)."""

    def __init__(self) -> None:
        self.normal_queue:  collections.deque[Patient] = collections.deque()
        self.priority_heap: list[tuple[int, Patient]]  = []
        self.now_serving:   dict | None                = None
        self.undo_stack:    list[dict]                 = []  # list of snapshots

    # ── snapshot helpers ──────────────────────────────────────────────────────

    def _snapshot(self) -> dict:
        """Capture a deep copy of the full mutable state."""
        return {
            "priority": copy.deepcopy(self.priority_heap),
            "normal":   copy.deepcopy(list(self.normal_queue)),
            "serving":  copy.deepcopy(self.now_serving),
        }

    def _push_snapshot(self) -> None:
        """Push current state onto the undo stack BEFORE mutating."""
        self.undo_stack.append(self._snapshot())

    def _restore_snapshot(self, snap: dict) -> None:
        """Atomically restore all state from a snapshot."""
        self.priority_heap = snap["priority"]
        heapq.heapify(self.priority_heap)           # re-establish heap invariant
        self.normal_queue  = collections.deque(snap["normal"])
        self.now_serving   = snap["serving"]

    # ── enqueue ───────────────────────────────────────────────────────────────

    def enqueue(self, patient: Patient) -> None:
        """Route patient to the correct queue and push to undo stack."""
        self._push_snapshot()
        if patient.urgent:
            heapq.heappush(self.priority_heap, (patient._order, patient))
        else:
            self.normal_queue.append(patient)

    # ── dequeue ───────────────────────────────────────────────────────────────

    def dequeue(self) -> Patient | None:
        """
        Serve next patient — priority queue always wins.
        Returns None when both queues are empty.
        NOTE: caller is responsible for setting self.now_serving AFTER
        calling this method (so the snapshot captured here holds the
        pre-serve state correctly).
        """
        if not self.priority_heap and not self.normal_queue:
            return None

        self._push_snapshot()

        if self.priority_heap:
            _, patient = heapq.heappop(self.priority_heap)
            return patient

        patient = self.normal_queue.popleft()
        return patient

    # ── prioritize ────────────────────────────────────────────────────────────

    def prioritize(self, uid: str) -> bool:
        """
        Escalate a normal-queue patient to the priority heap.
        O(n) scan — acceptable at clinic scale (<500 patients).
        """
        for i, p in enumerate(self.normal_queue):
            if p.uid == uid:
                self._push_snapshot()
                del self.normal_queue[i]
                p.urgent = True
                heapq.heappush(self.priority_heap, (p._order, p))
                return True
        return False

    # ── undo ──────────────────────────────────────────────────────────────────

    def undo(self) -> str:
        """
        Reverse the last action by restoring the previous full snapshot.
        Returns a human-readable description, or '' if nothing to undo.
        """
        if not self.undo_stack:
            return ""

        snap = self.undo_stack.pop()
        self._restore_snapshot(snap)
        return "State restored to before last action"

    # ── clear ─────────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self.normal_queue.clear()
        self.priority_heap.clear()
        self.undo_stack.clear()
        self.now_serving = None

    # ── read-only views ───────────────────────────────────────────────────────

    def priority_patients(self) -> list[Patient]:
        """Priority patients sorted by insertion order (stable FIFO within urgents)."""
        return [p for _, p in sorted(self.priority_heap)]

    def normal_patients(self) -> list[Patient]:
        return list(self.normal_queue)

    def total_count(self) -> int:
        return len(self.priority_heap) + len(self.normal_queue)

    def is_empty(self) -> bool:
        return self.total_count() == 0

    # ── serialisation helpers ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "priority":    [p.to_dict() for _, p in sorted(self.priority_heap)],
            "normal":      [p.to_dict() for p in self.normal_queue],
            "now_serving": self.now_serving,
        }

    def load_dict(self, data: dict) -> None:
        """Restore full system state from a previously saved dict."""
        self.clear()
        for d in data.get("priority", []):
            p = Patient.from_dict(d)
            heapq.heappush(self.priority_heap, (p._order, p))
        for d in data.get("normal", []):
            self.normal_queue.append(Patient.from_dict(d))
        self.now_serving = data.get("now_serving", None)
