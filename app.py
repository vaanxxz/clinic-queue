"""
app.py  —  Clinic Queue v6
===========================
Changes from v5:
  • Student number as primary identifier (no name field by default)
  • QR-first mode: manual entry panel hidden by default, toggled by button
  • "Serve Next Patient" always visible regardless of mode
  • Polished GUI: better card hierarchy, tighter spacing, smoother sections
  • Live queue status API support for QR status page
"""

from __future__ import annotations

import datetime
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

import customtkinter as ctk
from PIL import Image

import config as C
import persistence
from models import Patient
from queue_manager import QueueManager

log = logging.getLogger(__name__)

ctk.set_appearance_mode(C.CTK_APPEARANCE)
ctk.set_default_color_theme(C.CTK_COLOR_THEME)


# ─────────────────────────────────────────────────────────────────────────────
#  Colour helpers
# ─────────────────────────────────────────────────────────────────────────────

def _darken(hex_color: str, amount: int = 20) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        max(0, r - amount), max(0, g - amount), max(0, b - amount))

def _lighten(hex_color: str, amount: int = 20) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        min(255, r + amount), min(255, g + amount), min(255, b + amount))


# ─────────────────────────────────────────────────────────────────────────────
#  Widget factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def _card(parent, **kw) -> ctk.CTkFrame:
    kw.setdefault("corner_radius", C.CORNER_R)
    kw.setdefault("fg_color",      C.BG_CARD)
    kw.setdefault("border_width",  1)
    kw.setdefault("border_color",  C.BORDER_COLOR)
    return ctk.CTkFrame(parent, **kw)

def _lbl(parent, text: str, font, fg: str = C.TEXT_PRIMARY,
         anchor="w", **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font,
                        text_color=fg, anchor=anchor, **kw)

def _btn(parent, text: str, cmd, fg_color: str,
         text_color: str = C.TEXT_ON_DARK,
         height: int = C.BTN_HEIGHT, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg_color, hover_color=_darken(fg_color, 22),
        text_color=text_color, corner_radius=C.CORNER_R,
        font=ctk.CTkFont("Segoe UI", 11, "bold"),
        height=height, **kw)


# ─────────────────────────────────────────────────────────────────────────────
#  Smooth drag mixin
# ─────────────────────────────────────────────────────────────────────────────

class _DragMixin:
    _DRAG_THRESHOLD = 1

    def _bind_drag(self, *widgets):
        for w in widgets:
            w.bind("<ButtonPress-1>",   self._on_press)
            w.bind("<B1-Motion>",       self._on_motion)
            w.bind("<ButtonRelease-1>", self._on_release)
            w.bind("<Enter>",  lambda e: self._hover(True))
            w.bind("<Leave>",  lambda e: self._hover(False))

    def _on_press(self, event):
        self._drag_y       = event.y_root
        self._drag_pending = False

    def _on_motion(self, event):
        if self._drag_y is None:
            return
        delta = event.y_root - self._drag_y
        if abs(delta) < self._DRAG_THRESHOLD:
            return
        self._drag_y = event.y_root
        new_h = max(self._min_h, min(self._max_h, self._cur_h + delta))
        if new_h == self._cur_h:
            return
        self._cur_h = new_h
        if not self._drag_pending:
            self._drag_pending = True
            self.after_idle(self._flush_drag)

    def _flush_drag(self):
        self._drag_pending = False
        self._apply_size(self._cur_h)

    def _on_release(self, _event):
        self._drag_y = None
        self._apply_size(self._cur_h)

    def _hover(self, on: bool):
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
#  Handle strip
# ─────────────────────────────────────────────────────────────────────────────

class _HandleStrip(tk.Frame):
    H = 12
    DOT_COLOR = "#2ECECE"
    DOT_HOVER = "#60E8E8"

    def __init__(self, parent, bg_normal: str, bg_hover: str,
                 cursor: str = "sb_v_double_arrow"):
        super().__init__(parent, height=self.H, bg=bg_normal, cursor=cursor)
        self._bg_n = bg_normal
        self._bg_h = bg_hover
        self._canvas = tk.Canvas(self, height=self.H,
                                 bg=bg_normal, highlightthickness=0)
        self._canvas.pack(fill="x", expand=True)
        self._canvas.bind("<Configure>", self._redraw)

    def set_hover(self, on: bool):
        color = self._bg_h if on else self._bg_n
        self.configure(bg=color)
        self._canvas.configure(bg=color)
        dot = self.DOT_HOVER if on else self.DOT_COLOR
        for item in self._canvas.find_withtag("dot"):
            self._canvas.itemconfig(item, fill=dot)

    def bind_to(self, *extras):
        return (self, self._canvas) + extras

    def _redraw(self, _e=None):
        self._canvas.delete("all")
        w = self._canvas.winfo_width()
        cy = self.H // 2
        n, gap = 13, 7
        sx = w // 2 - (n * gap) // 2
        for i in range(n):
            x = sx + i * gap
            self._canvas.create_oval(x-2, cy-2, x+2, cy+2,
                                     fill=self.DOT_COLOR, outline="", tags="dot")


# ─────────────────────────────────────────────────────────────────────────────
#  ResizableNowServing  (shows student number prominently)
# ─────────────────────────────────────────────────────────────────────────────

class ResizableNowServing(_DragMixin, ctk.CTkFrame):
    _FONT_BUCKET = 10

    # Colour sets: (ring, card_bg, accent_stripe, id_color, sub_color, detail_color, badge_bg, badge_fg)
    _COLORS_IDLE   = ("#0A5C5B", "#0C7472", "#0E8A88", "#C8F0EF", "#7FD9D7", "#5BBFBC", "#1A9E9C", "#FFFFFF")
    _COLORS_NORMAL = ("#065957", "#0C7472", "#0E8A88", "#FFFFFF",  "#A8E6E4", "#7FD9D7", "#19B8B6", "#FFFFFF")
    _COLORS_URGENT = ("#7A1010", "#9B1C1C", "#C0392B", "#FFEE58",  "#FFB3B3", "#FF8A80", "#C0392B", "#FFEE58")

    def __init__(self, parent, initial_height, min_h, max_h, **kw):
        ctk.CTkFrame.__init__(self, parent, fg_color="transparent",
                              corner_radius=0, **kw)
        self._cur_h        = float(initial_height)
        self._min_h        = float(min_h)
        self._max_h        = float(max_h)
        self._drag_y       = None
        self._drag_pending = False
        self._last_bucket  = -1
        self._is_urgent    = False
        self._flash_phase  = 0
        self._patient      : Optional[Patient] = None

        # ── Outer glow ring ──────────────────────────────────────────────────
        self._ring = ctk.CTkFrame(self, fg_color=self._COLORS_IDLE[0],
                                  corner_radius=20, height=int(self._cur_h) + 6)
        self._ring.pack(fill="x", padx=0, pady=0)
        self._ring.pack_propagate(False)

        # ── Main card ────────────────────────────────────────────────────────
        self._card = ctk.CTkFrame(self._ring, fg_color=self._COLORS_IDLE[1],
                                  corner_radius=18, border_width=0,
                                  height=int(self._cur_h))
        self._card.pack(fill="x", padx=3, pady=3)
        self._card.pack_propagate(False)

        # ── Accent stripe (left edge) ────────────────────────────────────────
        self._stripe = ctk.CTkFrame(self._card, fg_color=self._COLORS_IDLE[2],
                                    corner_radius=0, width=8)
        self._stripe.place(x=0, y=0, relheight=1)

        # ── Content area ─────────────────────────────────────────────────────
        inner = ctk.CTkFrame(self._card, fg_color="transparent")
        inner.place(x=20, y=0, relwidth=1, relheight=1)

        # LEFT column
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # ── Top badge row ─────────────────────────────────────────────────────
        badge_row = ctk.CTkFrame(left, fg_color="transparent")
        badge_row.pack(anchor="w", pady=(14, 0))

        # Live dot canvas
        self._dot_cv = tk.Canvas(badge_row, width=14, height=14,
                                 bg=self._COLORS_IDLE[1], highlightthickness=0)
        self._dot_cv.pack(side="left", padx=(0, 8))
        self._dot_cv.create_oval(1, 1, 13, 13, fill="#2ECC71",
                                 outline="#1AAD5B", width=1, tags="dot")

        # "NOW SERVING" pill
        self._badge_frame = ctk.CTkFrame(badge_row, fg_color=self._COLORS_IDLE[6],
                                          corner_radius=20, height=30)
        self._badge_frame.pack(side="left")
        self._badge_frame.pack_propagate(False)
        self._badge_lbl = ctk.CTkLabel(
            self._badge_frame, text="  ◉  NOW SERVING  ",
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            text_color=self._COLORS_IDLE[7])
        self._badge_lbl.pack(padx=10, pady=5)

        # ── Giant student ID ──────────────────────────────────────────────────
        self._name_lbl = ctk.CTkLabel(
            left, text="No patient yet",
            font=ctk.CTkFont("Segoe UI", self._name_sz(), "bold"),
            text_color=self._COLORS_IDLE[3], anchor="w", wraplength=700)
        self._name_lbl.pack(anchor="w", pady=(2, 0))

        # ── Sub-label: "STUDENT NO." ──────────────────────────────────────────
        self._sub_lbl = ctk.CTkLabel(
            left, text="WAITING FOR NEXT PATIENT",
            font=ctk.CTkFont("Segoe UI", self._det_sz(), "bold"),
            text_color=self._COLORS_IDLE[4], anchor="w")
        self._sub_lbl.pack(anchor="w", pady=(0, 4))

        # ── Separator line ────────────────────────────────────────────────────
        self._sep_cv = tk.Canvas(left, height=2, bg=self._COLORS_IDLE[1],
                                 highlightthickness=0)
        self._sep_cv.pack(fill="x", pady=(0, 6))
        self._sep_cv.create_rectangle(0, 0, 2000, 2, fill="#1A9E9C",
                                      outline="", tags="sep")

        # ── Reason + time row ─────────────────────────────────────────────────
        det = ctk.CTkFrame(left, fg_color="transparent")
        det.pack(anchor="w", fill="x", pady=(0, 10))

        self._reason_icon = ctk.CTkLabel(det, text="",
            font=ctk.CTkFont("Segoe UI", self._det_sz()),
            text_color=self._COLORS_IDLE[5])
        self._reason_icon.pack(side="left")

        self._reason_lbl = ctk.CTkLabel(det, text="",
            font=ctk.CTkFont("Segoe UI", self._det_sz()),
            text_color=self._COLORS_IDLE[5])
        self._reason_lbl.pack(side="left")

        self._time_lbl = ctk.CTkLabel(det, text="",
            font=ctk.CTkFont("Segoe UI", self._time_sz()),
            text_color=self._COLORS_IDLE[5])
        self._time_lbl.pack(side="right", padx=(0, 24))

        # RIGHT column — priority badge
        right = ctk.CTkFrame(inner, fg_color="transparent", width=190)
        right.pack(side="right", fill="y", padx=(0, 16))
        right.pack_propagate(False)

        self._type_badge = ctk.CTkFrame(right, fg_color="#1A9E9C",
                                        corner_radius=16, width=168, height=84)
        self._type_badge.pack(expand=True)
        self._type_badge.pack_propagate(False)

        self._type_icon = ctk.CTkLabel(
            self._type_badge, text="—",
            font=ctk.CTkFont("Segoe UI", self._icon_sz()),
            text_color="#B2DDD9")
        self._type_icon.place(relx=0.5, rely=0.35, anchor="center")

        self._type_lbl = ctk.CTkLabel(
            self._type_badge, text="",
            font=ctk.CTkFont("Segoe UI", self._type_sz(), "bold"),
            text_color="#B2DDD9")
        self._type_lbl.place(relx=0.5, rely=0.72, anchor="center")

        # ── Drag handle ───────────────────────────────────────────────────────
        self._strip = _HandleStrip(self, bg_normal="#0B6160", bg_hover="#14A5A3")
        self._strip.pack(fill="x")
        self._bind_drag(*self._strip.bind_to())

        self._pulse_phase = 0
        self._pulse()

    # ── Animation ─────────────────────────────────────────────────────────────

    def _pulse(self):
        self._pulse_phase = (self._pulse_phase + 1) % 24

        # Green dot breathe
        r = 6 if self._pulse_phase < 12 else 5
        x0, y0, x1, y1 = 7-r, 7-r, 7+r, 7+r
        self._dot_cv.coords("dot", x0, y0, x1, y1)

        # Urgent flash: alternate ring colour
        if self._is_urgent:
            self._flash_phase = (self._flash_phase + 1) % 16
            ring_col = "#9B1C1C" if self._flash_phase < 8 else "#C0392B"
            self._ring.configure(fg_color=ring_col)

        self.after(130, self._pulse)

    # ── Size helpers ──────────────────────────────────────────────────────────

    def _ratio(self) -> float:
        return (self._cur_h - self._min_h) / max(1, self._max_h - self._min_h)

    def _name_sz(self)  -> int: return int(42 + self._ratio() * 52)
    def _det_sz(self)   -> int: return int(12 + self._ratio() * 10)
    def _time_sz(self)  -> int: return int(10 + self._ratio() *  8)
    def _type_sz(self)  -> int: return int(11 + self._ratio() *  9)
    def _icon_sz(self)  -> int: return int(24 + self._ratio() * 10)

    def _bucket(self)   -> int: return int(self._cur_h) // self._FONT_BUCKET

    def _refresh_fonts(self):
        b = self._bucket()
        if b == self._last_bucket:
            return
        self._last_bucket = b
        self._name_lbl.configure(font=ctk.CTkFont("Segoe UI", self._name_sz(), "bold"))
        self._sub_lbl.configure(font=ctk.CTkFont("Segoe UI", self._det_sz(), "bold"))
        self._reason_icon.configure(font=ctk.CTkFont("Segoe UI", self._det_sz()))
        self._reason_lbl.configure(font=ctk.CTkFont("Segoe UI", self._det_sz()))
        self._time_lbl.configure(font=ctk.CTkFont("Segoe UI", self._time_sz()))
        self._type_icon.configure(font=ctk.CTkFont("Segoe UI", self._icon_sz()))
        self._type_lbl.configure(font=ctk.CTkFont("Segoe UI", self._type_sz(), "bold"))

    def _apply_size(self, h: float):
        hi = int(h)
        self._card.configure(height=hi)
        self._ring.configure(height=hi + 6)
        self._refresh_fonts()

    def _hover(self, on: bool):
        self._strip.set_hover(on)

    # ── Apply colour scheme ───────────────────────────────────────────────────

    def _apply_colors(self, cols):
        ring, card, stripe, id_col, sub_col, det_col, badge_bg, badge_fg = cols
        if not self._is_urgent:
            self._ring.configure(fg_color=ring)
        self._card.configure(fg_color=card)
        self._stripe.configure(fg_color=stripe)
        self._dot_cv.configure(bg=card)
        self._sep_cv.configure(bg=card)
        self._name_lbl.configure(text_color=id_col)
        self._sub_lbl.configure(text_color=sub_col)
        self._reason_icon.configure(text_color=det_col)
        self._reason_lbl.configure(text_color=det_col)
        self._time_lbl.configure(text_color=det_col)
        self._badge_frame.configure(fg_color=badge_bg)
        self._badge_lbl.configure(text_color=badge_fg)

    # ── Public update ─────────────────────────────────────────────────────────

    def update_patient(self, patient: Optional[Patient]) -> None:
        self._patient   = patient
        self._is_urgent = bool(patient and patient.urgent)

        if patient is None:
            self._apply_colors(self._COLORS_IDLE)
            self._name_lbl.configure(text="No patient yet")
            self._sub_lbl.configure(text="WAITING FOR NEXT PATIENT")
            self._reason_icon.configure(text="")
            self._reason_lbl.configure(text="")
            self._time_lbl.configure(text="")
            self._type_icon.configure(text="—", text_color="#7FD9D7")
            self._type_lbl.configure(text="", text_color="#7FD9D7")
            self._type_badge.configure(fg_color="#1A9E9C")
            self._badge_lbl.configure(text="  ◉  NOW SERVING  ")
        elif patient.urgent:
            self._apply_colors(self._COLORS_URGENT)
            self._name_lbl.configure(text=patient.student_id)
            self._sub_lbl.configure(text="▲  STUDENT NO.  —  URGENT CASE")
            self._reason_icon.configure(text="🚨  ")
            self._reason_lbl.configure(text=patient.reason)
            self._time_lbl.configure(
                text=f"⏱  {patient.time_str()}  ·  {patient.date_str()}")
            self._type_icon.configure(text="🚨", text_color="#FFEE58")
            self._type_lbl.configure(text="URGENT", text_color="#FFEE58")
            self._type_badge.configure(fg_color="#7A1010")
            self._badge_lbl.configure(text="  🚨  URGENT — NOW SERVING  ")
        else:
            self._apply_colors(self._COLORS_NORMAL)
            self._name_lbl.configure(text=patient.student_id)
            self._sub_lbl.configure(text="STUDENT NO.")
            self._reason_icon.configure(text="📋  ")
            self._reason_lbl.configure(text=patient.reason)
            self._time_lbl.configure(
                text=f"⏱  {patient.time_str()}  ·  {patient.date_str()}")
            self._type_icon.configure(text="✅", text_color="#A8E6E4")
            self._type_lbl.configure(text="NORMAL", text_color="#A8E6E4")
            self._type_badge.configure(fg_color="#0A6B69")
            self._badge_lbl.configure(text="  ◉  NOW SERVING  ")


# ─────────────────────────────────────────────────────────────────────────────
#  ResizableQueueFrame
# ─────────────────────────────────────────────────────────────────────────────

class ResizableQueueFrame(_DragMixin, ctk.CTkFrame):
    def __init__(self, parent, label, icon, sublabel,
                 accent, columns, row_tags,
                 initial_height, min_h, max_h, **kw):
        ctk.CTkFrame.__init__(self, parent, fg_color="transparent",
                              corner_radius=0, **kw)
        self._cur_h        = float(initial_height)
        self._min_h        = float(min_h)
        self._max_h        = float(max_h)
        self._drag_y       = None
        self._drag_pending = False
        self._accent       = accent

        self._box = ctk.CTkFrame(self, fg_color="transparent",
                                 corner_radius=0, height=int(self._cur_h))
        self._box.pack(fill="x")
        self._box.pack_propagate(False)

        # Section header
        hdr = ctk.CTkFrame(self._box, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 5))
        ctk.CTkFrame(hdr, fg_color=accent, width=4,
                     corner_radius=2, height=20).pack(side="left", padx=(0, 8))
        _lbl(hdr, f"{icon}  {label}",
             font=ctk.CTkFont("Segoe UI", 11, "bold"), fg=accent).pack(side="left")
        _lbl(hdr, f"  —  {sublabel}",
             font=ctk.CTkFont("Segoe UI", 9),
             fg=C.TEXT_DISABLED).pack(side="left", padx=4)

        self._card_frame = _card(self._box)
        self._card_frame.pack(fill="both", expand=True)

        tf = ctk.CTkFrame(self._card_frame, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=2, pady=2)

        self.tree = _treeview(tf, columns, row_tags)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        self._strip = _HandleStrip(self,
                                   bg_normal=_lighten(C.BORDER_COLOR, 5),
                                   bg_hover=_lighten(accent, 30))
        self._strip._bg_n = "#D9E6EE"
        self._strip._bg_h = _lighten(accent, 40)
        self._strip.pack(fill="x")
        self._bind_drag(*self._strip.bind_to())

    def _apply_size(self, h: float):
        self._box.configure(height=int(h))

    def _hover(self, on: bool):
        self._strip.set_hover(on)


# ─────────────────────────────────────────────────────────────────────────────
#  Treeview builder
# ─────────────────────────────────────────────────────────────────────────────

def _treeview(parent, columns, row_tags, row_height=36) -> ttk.Treeview:
    sn = f"CQ{id(parent)}.Treeview"
    s  = ttk.Style()
    s.theme_use("default")
    s.configure(sn,
                background=C.BG_CARD, foreground=C.TEXT_PRIMARY,
                fieldbackground=C.BG_CARD, rowheight=row_height,
                font=("Segoe UI", 10), borderwidth=0, relief="flat")
    s.configure(f"{sn}.Heading",
                background="#EAF3F3", foreground=C.ACCENT_TEAL,
                font=("Segoe UI", 9, "bold"), borderwidth=0,
                relief="flat", padding=(8, 6))
    s.map(sn,
          background=[("selected", C.ROW_SELECT)],
          foreground=[("selected", C.ACCENT_TEAL)])
    s.map(f"{sn}.Heading", background=[("active", "#C8E8E7")])

    t = ttk.Treeview(parent, columns=columns, show="headings",
                     style=sn, selectmode="browse")
    for col in columns:
        w = C.COL_WIDTHS.get(col, 120)
        t.heading(col, text=col)
        t.column(col, width=w, minwidth=40, anchor="w")
    for tag, cfg in row_tags.items():
        t.tag_configure(tag, **cfg)
    return t


# ─────────────────────────────────────────────────────────────────────────────
#  Main application window
# ─────────────────────────────────────────────────────────────────────────────

class ClinicApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        self.title(C.APP_TITLE)
        self.minsize(C.MIN_WIDTH, C.MIN_HEIGHT)
        self.configure(fg_color=C.BG_APP)

        self.qm              = QueueManager()
        self._selected_uid   : Optional[str] = None
        self._now_serving    : Optional[Patient] = None
        self._norm_uids      : list = []
        self._manual_mode    : bool = False   # left panel toggle

        restored = persistence.load(self.qm)
        self._build_ui()
        self._refresh()

        if restored and self.qm.total_count() > 0:
            self._status(
                f"✅  Restored {self.qm.total_count()} patient(s) from previous session.",
                C.ACCENT_GREEN)

        self._center()
        self._tick_clock()
        self.after(C.REFRESH_MS, self._auto_refresh)

    # ── Housekeeping ──────────────────────────────────────────────────────────

    def _center(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{C.DEFAULT_WIDTH}x{C.DEFAULT_HEIGHT}"
                      f"+{(sw-C.DEFAULT_WIDTH)//2}+{(sh-C.DEFAULT_HEIGHT)//2}")

    def _auto_refresh(self):
        self._refresh()
        self.after(C.REFRESH_MS, self._auto_refresh)

    # ── Web callbacks ─────────────────────────────────────────────────────────

    def web_enqueue(self, name, sid, reason, urgent):
        """Thread-safe: called from Flask thread → deferred to Tk thread."""
        self.after(0, self._do_web_enqueue, name, sid, reason, urgent)

    def _do_web_enqueue(self, name, sid, reason, urgent):
        p = Patient(name, sid, reason, urgent)
        self.qm.enqueue(p)
        persistence.save(self.qm)
        self._status(
            f"🌐  QR Check-in: {p.student_id}  [{'URGENT 🚨' if urgent else 'Normal'}]",
            C.ACCENT_BLUE)
        self._refresh()

    def web_get_status(self, student_id: str) -> dict:
        """Called from Flask thread — read-only, GIL-safe."""
        if self._now_serving and self._now_serving.student_id == student_id:
            return {"status": "serving", "student_id": student_id,
                    "position": 0, "total": self.qm.total_count()}

        prio = self.qm.priority_patients()
        for i, p in enumerate(prio, 1):
            if p.student_id == student_id:
                return {"status": "waiting", "student_id": student_id,
                        "queue_type": "urgent", "position": i,
                        "total": self.qm.total_count()}

        norm = self.qm.normal_patients()
        for i, p in enumerate(norm, 1):
            if p.student_id == student_id:
                return {"status": "waiting", "student_id": student_id,
                        "queue_type": "normal", "position": len(prio) + i,
                        "total": self.qm.total_count()}

        return {"status": "not_found", "student_id": student_id}

    # =========================================================================
    #  UI construction
    # =========================================================================

    def _build_ui(self):
        self._build_header()
        self._build_body()
        self._build_footer()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=C.BG_HEADER, corner_radius=0, height=70)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        left = ctk.CTkFrame(hdr, fg_color="transparent")
        left.pack(side="left", padx=C.PAD_OUTER, fill="y")

        icon_box = ctk.CTkFrame(left, fg_color="#0A5C5B",
                                corner_radius=10, width=44, height=44)
        icon_box.pack(side="left", padx=(0, 14))
        icon_box.pack_propagate(False)
        _lbl(icon_box, "🏥", font=ctk.CTkFont("Segoe UI", 22),
             fg="#FFFFFF", anchor="center").place(relx=0.5, rely=0.5, anchor="center")

        text_col = ctk.CTkFrame(left, fg_color="transparent")
        text_col.pack(side="left", fill="y", pady=12)
        _lbl(text_col, "School Clinic",
             font=ctk.CTkFont("Segoe UI", 19, "bold"), fg="#FFFFFF").pack(anchor="w")
        _lbl(text_col, "Patient Queue Management  ·  v6",
             font=ctk.CTkFont("Segoe UI", 9), fg="#7ECFCD").pack(anchor="w")

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right", padx=C.PAD_OUTER, fill="y")

        live_pill = ctk.CTkFrame(right, fg_color="#0A5C5B", corner_radius=20, height=28)
        live_pill.pack(side="right", pady=20)
        live_pill.pack_propagate(False)
        dot_cv = tk.Canvas(live_pill, width=8, height=8,
                           bg="#0A5C5B", highlightthickness=0)
        dot_cv.pack(side="left", padx=(10, 4), pady=10)
        dot_cv.create_oval(0, 0, 8, 8, fill="#2ECC71", outline="")
        _lbl(live_pill, "LIVE  ",
             font=ctk.CTkFont("Segoe UI", 9, "bold"), fg="#2ECC71").pack(side="left")

        self._clock_lbl = _lbl(right, text="",
                               font=ctk.CTkFont("Segoe UI", 11),
                               fg="#8FCFCD", anchor="e")
        self._clock_lbl.pack(side="right", padx=(0, 14), pady=20)

        # Status bar
        sbar = ctk.CTkFrame(self, fg_color="#E6F7F6", corner_radius=0, height=36)
        sbar.pack(fill="x")
        sbar.pack_propagate(False)

        self._status_accent = ctk.CTkFrame(sbar, fg_color=C.ACCENT_TEAL,
                                           width=4, corner_radius=0)
        self._status_accent.pack(side="left", fill="y")

        self._status_lbl = _lbl(sbar,
            text="🏥  System ready. Waiting for first patient…",
            font=ctk.CTkFont("Segoe UI", 11), fg=C.ACCENT_TEAL)
        self._status_lbl.pack(side="left", padx=14)

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color=C.BG_APP, corner_radius=0)
        body.pack(fill="both", expand=True, padx=C.PAD_OUTER, pady=C.PAD_SMALL)
        self._build_left(body)
        self._build_right(body)

    # ── LEFT panel ────────────────────────────────────────────────────────────

    def _build_left(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=C.BG_PANEL,
                             corner_radius=C.CORNER_R, width=340,
                             border_width=1, border_color=C.BORDER_COLOR)
        panel.pack(side="left", fill="y", padx=(0, C.PAD_SMALL))
        panel.pack_propagate(False)

        inner = ctk.CTkScrollableFrame(
            panel, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=C.BORDER_COLOR,
            scrollbar_button_hover_color=C.ACCENT_TEAL)
        inner.pack(fill="both", expand=True, padx=C.PAD_INNER, pady=C.PAD_INNER)

        # ── QR Section ───────────────────────────────────────────────────────
        self._sec_header(inner, "📷", "Scan to Join Queue",
                         "Point camera at QR code below")
        self._build_qr(inner)

        self._div(inner)

        # ── Core Actions (always visible) ─────────────────────────────────────
        self._sec_header(inner, "⚡", "Actions", "")

        _btn(inner, "▶   Serve Next Patient",
             self._serve_patient, C.ACCENT_GOLD).pack(fill="x", pady=(0, 6))

        _btn(inner, "⬆   Prioritize Selected",
             self._prioritize, C.ACCENT_BLUE).pack(fill="x", pady=(0, 6))

        # Sub-row: undo + clear
        sub_row = ctk.CTkFrame(inner, fg_color="transparent")
        sub_row.pack(fill="x", pady=(0, 4))
        _btn(sub_row, "↩  Undo", self._undo, "#ECF0F1",
             C.TEXT_MUTED, height=36).pack(side="left", expand=True, fill="x", padx=(0, 4))
        _btn(sub_row, "🗑  Clear All", self._clear_all, C.ACCENT_RED,
             height=36).pack(side="left", expand=True, fill="x")

        self._div(inner)

        # ── Manual Mode Toggle ────────────────────────────────────────────────
        self._toggle_btn = ctk.CTkButton(
            inner,
            text="🔓  Enable Manual Entry",
            command=self._toggle_manual,
            fg_color="#F0F7F7",
            hover_color="#D8EFEE",
            text_color=C.ACCENT_TEAL,
            border_width=1,
            border_color=C.ACCENT_TEAL,
            corner_radius=C.CORNER_R,
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            height=38,
        )
        self._toggle_btn.pack(fill="x", pady=(0, 6))

        # ── Manual Entry Section (hidden by default) ──────────────────────────
        self._manual_frame = ctk.CTkFrame(inner, fg_color="transparent")
        # Not packed initially — shown/hidden by toggle

        mf = self._manual_frame
        manual_card = ctk.CTkFrame(mf, fg_color="#F7FBFB",
                                   corner_radius=10,
                                   border_width=1, border_color="#B2DDD9")
        manual_card.pack(fill="x", pady=(0, 6))

        mc = ctk.CTkFrame(manual_card, fg_color="transparent")
        mc.pack(fill="x", padx=14, pady=12)

        _lbl(mc, "Manual Patient Entry",
             font=ctk.CTkFont("Segoe UI", 10, "bold"),
             fg=C.ACCENT_TEAL).pack(anchor="w", pady=(0, 10))

        self._entry_id     = self._field(mc, "Student Number *", "e.g. 2024-12345")
        self._entry_reason = self._field(mc, "Reason for Visit *", "e.g. Headache, Fever…")

        self._urgent_var = ctk.BooleanVar(value=False)
        uf = ctk.CTkFrame(mc, fg_color="#FFF5E6", corner_radius=8,
                          border_width=1, border_color="#FDDCAC")
        uf.pack(fill="x", pady=(10, 12))
        ctk.CTkCheckBox(
            uf, text="🚨  Mark as URGENT",
            variable=self._urgent_var,
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            text_color="#C0392B",
            fg_color=C.ACCENT_RED,
            hover_color=_darken(C.ACCENT_RED),
            checkmark_color=C.TEXT_ON_DARK,
            corner_radius=4).pack(anchor="w", padx=10, pady=6)

        _btn(mc, "➕   Add to Queue",
             self._add_patient, C.ACCENT_TEAL, height=40).pack(fill="x")

        self._div(inner)

        # ── Legend ────────────────────────────────────────────────────────────
        self._sec_header(inner, "📖", "Legend", "")
        self._build_legend(inner)

        self._div(inner)

        # ── Resize tip ────────────────────────────────────────────────────────
        tip = ctk.CTkFrame(inner, fg_color="#EAF7F6", corner_radius=8,
                           border_width=1, border_color="#B2DDD9")
        tip.pack(fill="x", pady=4)
        _lbl(tip,
             "↕  Drag handles to resize sections:\n"
             "  • NOW SERVING card  (text scales)\n"
             "  • Priority Queue table\n"
             "  • Normal Queue table",
             font=ctk.CTkFont("Segoe UI", 9),
             fg=C.ACCENT_TEAL, justify="left",
             anchor="w").pack(padx=12, pady=10)

    def _sec_header(self, parent, icon: str, title: str, sub: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(10, 4))
        _lbl(row, f"{icon}  {title}",
             font=ctk.CTkFont("Segoe UI", 11, "bold"),
             fg=C.TEXT_PRIMARY).pack(side="left")
        if sub:
            _lbl(row, f"  {sub}",
                 font=ctk.CTkFont("Segoe UI", 9),
                 fg=C.TEXT_DISABLED).pack(side="left")

    def _field(self, parent, label, placeholder=""):
        _lbl(parent, label,
             font=ctk.CTkFont("Segoe UI", 9, "bold"),
             fg=C.TEXT_MUTED).pack(anchor="w", pady=(6, 2))
        e = ctk.CTkEntry(
            parent, placeholder_text=placeholder,
            fg_color=C.BG_INPUT, border_color=C.BORDER_COLOR,
            border_width=1, text_color=C.TEXT_PRIMARY,
            placeholder_text_color=C.TEXT_DISABLED,
            corner_radius=8, height=38)
        e.pack(fill="x")
        return e

    def _build_qr(self, parent):
        c = _card(parent, fg_color="#EAF7F6", border_color="#B2DDD9")
        c.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(padx=14, pady=14)

        loaded = False
        if C.QR_IMAGE_PATH.exists():
            try:
                img = Image.open(C.QR_IMAGE_PATH).convert("RGBA").resize((200, 200))
                self._qr = ctk.CTkImage(light_image=img, dark_image=img, size=(200, 200))
                ctk.CTkLabel(inner, image=self._qr, text="").pack()
                loaded = True
            except Exception as e:
                log.warning("QR load failed: %s", e)

        if not loaded:
            ph = ctk.CTkFrame(inner, width=200, height=200,
                              fg_color=C.BG_INPUT, corner_radius=10,
                              border_width=1, border_color=C.BORDER_COLOR)
            ph.pack()
            ph.pack_propagate(False)
            ctk.CTkLabel(ph,
                text="📷\n\nPlace QR image at\nassets/clinic_qr.png",
                font=ctk.CTkFont("Segoe UI", 9),
                text_color=C.TEXT_DISABLED,
                justify="center").place(relx=0.5, rely=0.5, anchor="center")

        url_pill = ctk.CTkFrame(inner, fg_color="#D4F0EE", corner_radius=20, height=26)
        url_pill.pack(pady=(10, 0))
        url_pill.pack_propagate(False)
        _lbl(url_pill, f"  localhost:{C.FLASK_PORT}  ",
             font=ctk.CTkFont("Consolas", 9, "bold"),
             fg=C.ACCENT_TEAL, anchor="center").pack(padx=8, pady=4)

        _lbl(inner, "Students scan to join · see live position",
             font=ctk.CTkFont("Segoe UI", 8),
             fg=C.TEXT_DISABLED, anchor="center").pack(pady=(4, 0))

    def _build_legend(self, parent):
        for icon, color, desc in [
            ("🚨", C.ACCENT_RED,   "Urgent — Priority Queue (served first)"),
            ("📋", C.ACCENT_TEAL,  "Normal — FIFO Queue"),
            ("🕐", C.TEXT_MUTED,   "Timestamp of arrival"),
            ("✅", C.ACCENT_GREEN, "Currently being served"),
        ]:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=2)
            _lbl(row, icon, font=ctk.CTkFont("Segoe UI", 12),
                 fg=color, width=28).pack(side="left")
            _lbl(row, desc, font=ctk.CTkFont("Segoe UI", 9),
                 fg=C.TEXT_MUTED).pack(side="left", padx=(6, 0))

    # ── Toggle manual entry ───────────────────────────────────────────────────

    def _toggle_manual(self):
        self._manual_mode = not self._manual_mode
        if self._manual_mode:
            self._manual_frame.pack(fill="x", after=self._toggle_btn)
            self._toggle_btn.configure(
                text="🔒  Hide Manual Entry",
                fg_color="#FFF5E6",
                hover_color="#FDEBD0",
                text_color=C.ACCENT_GOLD,
                border_color=C.ACCENT_GOLD)
        else:
            self._manual_frame.pack_forget()
            self._toggle_btn.configure(
                text="🔓  Enable Manual Entry",
                fg_color="#F0F7F7",
                hover_color="#D8EFEE",
                text_color=C.ACCENT_TEAL,
                border_color=C.ACCENT_TEAL)

    # ── RIGHT panel ───────────────────────────────────────────────────────────

    def _build_right(self, parent):
        panel = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        panel.pack(side="left", fill="both", expand=True)

        self._now_widget = ResizableNowServing(
            panel,
            initial_height=C.NOW_SERVING_DEF_H,
            min_h=C.NOW_SERVING_MIN_H,
            max_h=C.NOW_SERVING_MAX_H)
        self._now_widget.pack(fill="x", pady=(0, C.PAD_SMALL))

        self._build_stats(panel)

        tables = ctk.CTkFrame(panel, fg_color="transparent")
        tables.pack(fill="both", expand=True, pady=(C.PAD_SMALL, 0))
        self._build_prio_table(tables)
        self._build_norm_table(tables)

    def _build_stats(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, C.PAD_SMALL))

        for label, val, color, attr, icon, bg in [
            ("URGENT", "0", C.ACCENT_RED,  "urgent", "🚨", "#FFF5E6"),
            ("NORMAL", "0", C.ACCENT_TEAL, "normal", "📋", "#EAF7F6"),
            ("TOTAL",  "0", C.ACCENT_BLUE, "total",  "👥", "#EAF2FF"),
        ]:
            c = ctk.CTkFrame(row, corner_radius=C.CORNER_R,
                             fg_color=bg, border_width=1,
                             border_color=C.BORDER_COLOR)
            c.pack(side="left", expand=True, fill="x", padx=(0, C.PAD_SMALL))

            top = ctk.CTkFrame(c, fg_color="transparent")
            top.pack(pady=(14, 0), padx=14, fill="x")
            _lbl(top, icon, font=ctk.CTkFont("Segoe UI", 18),
                 fg=color, anchor="w").pack(side="left")
            num = ctk.CTkLabel(top, text=val,
                               font=ctk.CTkFont("Segoe UI", 34, "bold"),
                               text_color=color, anchor="e")
            num.pack(side="right")
            _lbl(c, label, font=ctk.CTkFont("Segoe UI", 8, "bold"),
                 fg=C.TEXT_MUTED, anchor="center").pack(pady=(0, 12))
            setattr(self, f"_stat_{attr}", num)

    def _build_prio_table(self, parent):
        self._prio_frame = ResizableQueueFrame(
            parent,
            label="Priority / Urgent Queue",
            icon="🚨",
            sublabel="served before normal patients",
            accent=C.ACCENT_RED,
            columns=C.PRIORITY_COLUMNS,
            row_tags={"urgent": {"background": C.ROW_URGENT, "foreground": "#C0392B"}},
            initial_height=C.QUEUE_DEF_H,
            min_h=C.QUEUE_MIN_H,
            max_h=C.QUEUE_MAX_H)
        self._prio_frame.pack(fill="x", pady=(0, C.PAD_SMALL))
        self._prio_tree = self._prio_frame.tree

    def _build_norm_table(self, parent):
        self._norm_frame = ResizableQueueFrame(
            parent,
            label="Normal Queue",
            icon="📋",
            sublabel="first in, first out (FIFO)",
            accent=C.ACCENT_TEAL,
            columns=C.NORMAL_COLUMNS,
            row_tags={
                "normal": {"background": C.ROW_NORMAL,  "foreground": C.TEXT_PRIMARY},
                "alt":    {"background": "#F0F7FF",      "foreground": C.TEXT_PRIMARY},
            },
            initial_height=C.QUEUE_DEF_H,
            min_h=C.QUEUE_MIN_H,
            max_h=C.QUEUE_MAX_H)
        self._norm_frame.pack(fill="both", expand=True)
        self._norm_tree = self._norm_frame.tree
        self._norm_tree.bind("<<TreeviewSelect>>", self._on_norm_select)

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        f = ctk.CTkFrame(self, fg_color=C.BG_HEADER, corner_radius=0, height=28)
        f.pack(fill="x", side="bottom")
        f.pack_propagate(False)
        _lbl(f,
             f"🏥  School Clinic Queue  ·  QR Check-in: http://localhost:{C.FLASK_PORT}"
             "  ·  Status: http://localhost:{C.FLASK_PORT}/status/STUDENT-NO",
             font=ctk.CTkFont("Segoe UI", 8),
             fg="#6FAFAB", anchor="center").pack(expand=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _div(self, p):
        ctk.CTkFrame(p, fg_color=C.BORDER_COLOR,
                     height=1, corner_radius=0).pack(fill="x", pady=10)

    # =========================================================================
    #  Handlers
    # =========================================================================

    def _add_patient(self):
        sid    = self._entry_id.get().strip()
        reason = self._entry_reason.get().strip()
        urgent = self._urgent_var.get()
        if not sid:
            messagebox.showwarning("Missing", "Please enter the student number.")
            return
        if not reason:
            messagebox.showwarning("Missing", "Please enter the reason for visit.")
            return
        p = Patient(sid, sid, reason, urgent)
        self.qm.enqueue(p)
        persistence.save(self.qm)
        self._status(
            f"✅  Added: {p.student_id}  [{'URGENT 🚨' if urgent else 'Normal'}]"
            f"  @  {p.time_str()}", C.ACCENT_GREEN)
        self._entry_id.delete(0, "end")
        self._entry_reason.delete(0, "end")
        self._urgent_var.set(False)
        self._refresh()

    def _serve_patient(self):
        p = self.qm.dequeue()
        if p is None:
            messagebox.showinfo("Empty", "No patients waiting.")
            return
        self._now_serving = p
        persistence.save(self.qm)
        self._status(f"▶  Now serving: {p.student_id}", C.ACCENT_TEAL)
        self._now_widget.update_patient(p)
        self._refresh()

    def _prioritize(self):
        if self._selected_uid is None:
            messagebox.showinfo("No Selection",
                                "Select a patient in Normal Queue first.")
            return
        if self.qm.prioritize(self._selected_uid):
            persistence.save(self.qm)
            self._status("⬆  Patient moved to Priority Queue.", C.ACCENT_GOLD)
            self._selected_uid = None
        else:
            messagebox.showinfo("Not Found", "Patient not found in Normal Queue.")
        self._refresh()

    def _undo(self):
        msg = self.qm.undo()
        if msg:
            persistence.save(self.qm)
            self._status(f"↩  {msg}", C.TEXT_MUTED)
            self._refresh()
        else:
            messagebox.showinfo("Nothing to Undo", "Undo history is empty.")

    def _clear_all(self):
        if not messagebox.askyesno("Clear All",
                                   "Clear ALL queues? This cannot be undone."):
            return
        self.qm.clear()
        self._now_serving = self._selected_uid = None
        persistence.save(self.qm)
        self._status("🗑  All queues cleared.", C.TEXT_MUTED)
        self._now_widget.update_patient(None)
        self._refresh()

    # =========================================================================
    #  Refresh
    # =========================================================================

    def _refresh(self):
        prio = self.qm.priority_patients()
        norm = self.qm.normal_patients()

        self._prio_tree.delete(*self._prio_tree.get_children())
        if prio:
            for i, p in enumerate(prio, 1):
                self._prio_tree.insert("", "end",
                    values=(f"#{i}", p.student_id, p.reason, p.time_str()),
                    tags=("urgent",))
        else:
            self._prio_tree.insert("", "end",
                values=("", "— No urgent patients —", "", ""),
                tags=("urgent",))

        self._norm_tree.delete(*self._norm_tree.get_children())
        self._norm_uids = []
        if norm:
            for i, p in enumerate(norm, 1):
                iid = self._norm_tree.insert("", "end",
                    values=(f"#{i}", p.student_id, p.reason, p.time_str()),
                    tags=("normal" if i % 2 else "alt",))
                self._norm_uids.append((iid, p.uid))
        else:
            self._norm_tree.insert("", "end",
                values=("", "— No patients in normal queue —", "", ""),
                tags=("normal",))

        self._stat_urgent.configure(text=str(len(prio)))
        self._stat_normal.configure(text=str(len(norm)))
        self._stat_total.configure(text=str(self.qm.total_count()))

    def _on_norm_select(self, _=None):
        sel = self._norm_tree.selection()
        if not sel:
            return
        iid = sel[0]
        for tid, uid in self._norm_uids:
            if tid == iid:
                self._selected_uid = uid
                norm = self.qm.normal_patients()
                idx  = next((i for i, (t, _) in enumerate(self._norm_uids)
                             if t == iid), None)
                if idx is not None and idx < len(norm):
                    self._status(
                        f"👆  Selected: {norm[idx].student_id} — click ⬆ Prioritize to escalate",
                        C.ACCENT_GOLD)
                return

    def _status(self, text: str, color: str = C.ACCENT_TEAL):
        self._status_lbl.configure(text=text, text_color=color)
        self._status_accent.configure(fg_color=color)

    def _tick_clock(self):
        self._clock_lbl.configure(
            text=datetime.datetime.now().strftime("%A, %d %B %Y   %H:%M:%S"))
        self.after(1000, self._tick_clock)
