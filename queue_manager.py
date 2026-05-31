"""
queue_manager.py
================
Core data-structure logic — no UI dependency.

Data structures used
--------------------
  normal_queue   : collections.deque        — FIFO for regular patients
  priority_heap  : list (via heapq)         — min-heap keyed on _order
  now_serving    : dict | None              — current serving state
                   keys: student_id, name, reason, urgent
  undo_stack     : list of state snapshots  — each snapshot is a dict with
                   keys: priority, normal, now_serving

FIX SUMMARY
-----------
  • Added `now_serving` field to QueueManager so it is the single source
    of truth for the serving state (app.py previously kept this separately,
    which caused the undo to restore the queue but not the serving display).
  • Changed undo_stack from (action, patient) tuples to full state snapshots.
    This means every undo() call atomically restores queue + serving state,
    with no possibility of partial rollback.
  • to_dict() now includes now_serving so /api/queue and persistence both
    carry the full state.  load_dict() restores it on startup.
"""

from __future__ import annotations

import collections
import copy
import heapq

from models import Patient


class QueueManager:
    """Thread-safe-ish queue manager (single-threaded GUI; no locks needed)."""

    def __init__(self) -> None:
        self.normal_queue:  collections.deque[Patient] = collections.deque()
        self.priority_heap: list[tuple[int, Patient]]  = []
        self.now_serving:   dict | None                = None
        self.undo_stack:    list[dict]                 = []   # snapshots

    # ── snapshot helpers ──────────────────────────────────────────────────────

    def _take_snapshot(self) -> dict:
        """Deep-copy the full mutable state into a snapshot dict."""
        return {
            "priority":    copy.deepcopy(self.priority_heap),
            "normal":      list(self.normal_queue),  # Patient objects are not mutated
            "now_serving": copy.copy(self.now_serving),   # shallow ok (flat dict)
        }

    def _push_snapshot(self) -> None:
        self.undo_stack.append(self._take_snapshot())

    def _restore_snapshot(self, snap: dict) -> None:
        """Atomically restore all state from a snapshot."""
        self.priority_heap = snap["priority"]
        heapq.heapify(self.priority_heap)   # restore heap invariant after deepcopy
        self.normal_queue  = collections.deque(snap["normal"])
        self.now_serving   = snap["now_serving"]

    # ── enqueue ───────────────────────────────────────────────────────────────

    def enqueue(self, patient: Patient) -> None:
        """Route patient to the correct queue; push a full snapshot for undo."""
        self._push_snapshot()
        if patient.urgent:
            heapq.heappush(self.priority_heap, (patient._order, patient))
        else:
            self.normal_queue.append(patient)

    # ── dequeue ───────────────────────────────────────────────────────────────

    def dequeue(self) -> Patient | None:
        """
        Serve next patient — priority queue always wins.
        Caller MUST update self.now_serving after this call
        (before any other snapshot is taken) so that a subsequent
        undo() can restore the pre-serve now_serving state.
        Returns None when both queues are empty.
        """
        if not self.priority_heap and not self.normal_queue:
            return None

        self._push_snapshot()   # snapshot includes current now_serving

        if self.priority_heap:
            _, patient = heapq.heappop(self.priority_heap)
        else:
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
        Atomically restore the full state (queues + now_serving) to what it
        was before the last enqueue / dequeue / prioritize call.
        Returns a human-readable description, or '' if nothing to undo.
        """
        if not self.undo_stack:
            return ""

        snap = self.undo_stack.pop()
        prev_serving = self.now_serving
        self._restore_snapshot(snap)

        # Build a helpful description
        if self.now_serving != prev_serving:
            if prev_serving is not None and self.now_serving is None:
                return f"Undid SERVE — {prev_serving['name']} restored to queue"
            if prev_serving is None and self.now_serving is not None:
                return f"Undid SERVE — {self.now_serving['name']} back to serving"
        return "Undid last action"

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
        """
        Serialise full state — queues AND now_serving.
        Used by persistence.save(), /api/queue endpoint, and undo sync.
        """
        return {
            "priority":    [p.to_dict() for _, p in sorted(self.priority_heap)],
            "normal":      [p.to_dict() for p in self.normal_queue],
            "now_serving": self.now_serving,   # FIX: include serving state
        }

    def load_dict(self, data: dict) -> None:
        """Restore full state from a previously saved dict."""
        self.clear()
        for d in data.get("priority", []):
            p = Patient.from_dict(d)
            heapq.heappush(self.priority_heap, (p._order, p))
        for d in data.get("normal", []):
            self.normal_queue.append(Patient.from_dict(d))
        self.now_serving = data.get("now_serving", None)   # FIX: restore serving state
