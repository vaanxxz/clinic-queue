# clinic_queue.spec
# -----------------
# PyInstaller spec file for ClinicQueue.exe (Windows, one-folder bundle)
#
# Usage (from project root on Windows):
#   pip install pyinstaller
#   pyinstaller clinic_queue.spec --noconfirm
#
# Output:  dist/ClinicQueue/ClinicQueue.exe  (+ supporting files in same folder)

import os, sys
from pathlib import Path

ROOT = Path(SPECPATH)   # directory containing this .spec file
block_cipher = None

# ── Locate customtkinter data dir ─────────────────────────────────────────────
import importlib.util
_ctk_spec = importlib.util.find_spec("customtkinter")
CTK_DIR = str(Path(_ctk_spec.origin).parent) if _ctk_spec else "customtkinter"

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # App assets (QR image, icon, etc.)
        (str(ROOT / "assets"), "assets"),
        # CustomTkinter themes & images (required at runtime)
        (CTK_DIR, "customtkinter"),
    ],
    hiddenimports=[
        "customtkinter",
        "PIL._tkinter_finder",
        "flask",
        "werkzeug",
        "werkzeug.serving",
        "werkzeug.debug",
        "jinja2",
        "click",
        "itsdangerous",
        "markupsafe",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy",
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "IPython", "notebook", "sphinx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClinicQueue",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                   # no console window behind the GUI
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Remove the icon= line below if you don't have clinic_icon.ico yet:
    icon=str(ROOT / "assets" / "clinic_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ClinicQueue",
)
