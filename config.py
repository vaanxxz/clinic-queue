"""
config.py  —  Clinic Queue v6  (Soft Medical theme, teal + warm white)
"""

from __future__ import annotations
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
ASSET_DIR = BASE_DIR / "assets"
DATA_DIR  = BASE_DIR / "data"

QR_IMAGE_PATH = ASSET_DIR / "clinic_qr.png"
ICON_PATH     = ASSET_DIR / "clinic_icon.ico"
STATE_PATH    = DATA_DIR  / "queue_state.json"

# ── Flask ─────────────────────────────────────────────────────────────────────
FLASK_PORT = 5000
FLASK_HOST = "0.0.0.0"

# Railway polling: set RAILWAY_URL env var on the clinic PC to sync the GUI
# e.g. export RAILWAY_URL=https://your-clinic-app.up.railway.app
import os
RAILWAY_URL: str = os.environ.get("RAILWAY_URL", "")

# ── Timing ────────────────────────────────────────────────────────────────────
REFRESH_MS = 3000

# ── Window ────────────────────────────────────────────────────────────────────
APP_TITLE      = "School Clinic — Patient Queue"
MIN_WIDTH      = 1280
MIN_HEIGHT     = 860
DEFAULT_WIDTH  = 1500
DEFAULT_HEIGHT = 960

# ── NOW SERVING card (drag-resizable) ─────────────────────────────────────────
NOW_SERVING_MIN_H = 140
NOW_SERVING_MAX_H = 560
NOW_SERVING_DEF_H = 290

# ── Queue table heights (drag-resizable) ──────────────────────────────────────
QUEUE_MIN_H = 80
QUEUE_MAX_H = 600
QUEUE_DEF_H = 210

# ── Colour palette — Soft Medical (Teal + Warm White) ─────────────────────────
BG_APP    = "#EEF2F6"
BG_PANEL  = "#FFFFFF"
BG_CARD   = "#FFFFFF"
BG_INPUT  = "#F7FAFC"
BG_HEADER = "#0C7472"

ACCENT_TEAL   = "#0E7C7B"
ACCENT_TEAL_L = "#14A5A3"
ACCENT_GOLD   = "#F5A623"
ACCENT_AMBER  = "#E8850B"
ACCENT_LIGHT  = "#FFD84D"
ACCENT_GREEN  = "#2ECC71"
ACCENT_RED    = "#E74C3C"
ACCENT_BLUE   = "#3498DB"
ACCENT_PURPLE = "#9B59B6"

NOW_SERVING_BG    = "#0C7472"
NOW_SERVING_LIGHT = "#E8FAF9"

TEXT_PRIMARY  = "#1A2B3C"
TEXT_MUTED    = "#5A7184"
TEXT_DISABLED = "#A8BFCC"
TEXT_ON_DARK  = "#FFFFFF"
TEXT_ON_TEAL  = "#FFFFFF"

BORDER_COLOR  = "#D4E2EC"
BORDER_FOCUS  = "#0E7C7B"

ROW_URGENT = "#FFF2EE"
ROW_NORMAL = "#F7FAFC"
ROW_SELECT = "#C8EDEB"

SHADOW_COLOR = "#D9E6EE"

# ── CustomTkinter ─────────────────────────────────────────────────────────────
CTK_APPEARANCE  = "light"
CTK_COLOR_THEME = "green"

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT_TITLE    = ("Segoe UI", 20, "bold")
FONT_SUBTITLE = ("Segoe UI", 11, "normal")
FONT_SECTION  = ("Segoe UI", 12, "bold")
FONT_BODY     = ("Segoe UI", 10, "normal")
FONT_SMALL    = ("Segoe UI",  9, "normal")
FONT_MONO     = ("Consolas", 10, "normal")
FONT_LABEL    = ("Segoe UI",  9, "normal")

FONT_SERVING_NAME  = ("Segoe UI", 42, "bold")
FONT_SERVING_ID    = ("Segoe UI", 15, "normal")
FONT_SERVING_LABEL = ("Segoe UI", 11, "normal")
FONT_SERVING_TYPE  = ("Segoe UI", 16, "bold")

FONT_COUNTER_NUM   = ("Segoe UI", 34, "bold")
FONT_COUNTER_LABEL = ("Segoe UI",  8, "bold")

# ── Spacing ───────────────────────────────────────────────────────────────────
PAD_OUTER  = 18
PAD_INNER  = 14
PAD_SMALL  = 8
CORNER_R   = 12
BTN_HEIGHT = 42

# ── Treeview columns ──────────────────────────────────────────────────────────
PRIORITY_COLUMNS = ("#", "Student No.", "Reason", "Time")
NORMAL_COLUMNS   = ("#", "Student No.", "Reason", "Time")

COL_WIDTHS = {
    "#":           44,
    "Student No.": 170,
    "Reason":      300,
    "Time":         80,
}
