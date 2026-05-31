# ============================================================
#  app.py  –  TWO METHOD REPLACEMENTS  (desktop / GUI side)
# ============================================================
#
#  Apply these as drop-in replacements for the matching methods
#  inside the ClinicApp class.
#
#  Changes:
#   1. _serve_patient  — sets self.qm.now_serving BEFORE pushing
#      the undo snapshot, so the snapshot captures the pre-serve
#      now_serving state (i.e. None or whoever was serving before).
#
#   2. _undo           — after calling self.qm.undo() the local
#      now_serving display is refreshed from self.qm.now_serving
#      (which the snapshot-based undo has already restored).
#      The sync payload sent to Railway already includes now_serving
#      because QueueManager.to_dict() now includes it.
#
#   3. _notify_railway_undo — no change needed; it just calls
#      self.qm.to_dict() which now includes now_serving automatically.
# ============================================================


    def _serve_patient(self):
        # ── FIX: capture snapshot BEFORE mutating now_serving ─────────────────
        # QueueManager.dequeue() pushes a snapshot internally.
        # We update self.qm.now_serving AFTER dequeue so the snapshot it
        # pushed contains the old now_serving value — enabling a full rollback.
        p = self.qm.dequeue()
        if p is None:
            messagebox.showinfo("Empty", "No patients waiting.")
            return

        # FIX: store now_serving on the QueueManager (not only on self) so
        # that to_dict() / undo snapshots include it.
        self._now_serving     = p
        self.qm.now_serving   = {
            "student_id": p.student_id,
            "name":       p.name,
            "reason":     p.reason,
            "urgent":     p.urgent,
        }
        self._serving_in_flight = True   # block poll from restoring this patient
        persistence.save(self.qm)
        self._status(f"▶  Now serving: {p.student_id}", C.ACCENT_TEAL)
        self._now_widget.update_patient(p)
        self._refresh()
        # Notify Railway so its queue state and serving status stay in sync
        if C.RAILWAY_URL:
            self._notify_railway_serve(p.student_id)
        else:
            self._serving_in_flight = False

    def _undo(self):
        msg = self.qm.undo()   # snapshot-based: fully restores queue + now_serving
        if msg:
            # FIX: sync local _now_serving display from the restored QM state
            ns = self.qm.now_serving
            if ns:
                # Re-wrap as a Patient-like object your UI widget expects
                # (or just pass None to clear; adapt to your _now_widget API)
                from models import Patient
                from datetime import datetime
                restored_patient = Patient(
                    name=ns.get("name", ""),
                    student_id=ns.get("student_id", ""),
                    reason=ns.get("reason", ""),
                    urgent=ns.get("urgent", False),
                    timestamp=datetime.now(),
                )
                self._now_serving = restored_patient
                self._now_widget.update_patient(restored_patient)
            else:
                self._now_serving = None
                self._now_widget.clear()   # or however you blank the widget

            persistence.save(self.qm)
            self._status(f"↩  {msg}", C.TEXT_MUTED)
            self._refresh()

            # Block next poll(s) from overwriting the undo'd state
            self._undo_in_flight = True

            # Notify Railway — to_dict() now includes now_serving automatically
            if C.RAILWAY_URL:
                self._notify_railway_undo()
            else:
                self.after(6000, lambda: setattr(self, "_undo_in_flight", False))
        else:
            messagebox.showinfo("Nothing to Undo", "Undo history is empty.")

    # _notify_railway_undo — NO CHANGES NEEDED.
    # It calls self.qm.to_dict() which now includes "now_serving" automatically,
    # and Railway's /api/sync_queue now reads and applies that field.
