# 🏥 School Clinic — Patient Queue Management System

A friendly, professional desktop app for managing patient queues in a school clinic.
Built with **Python + CustomTkinter** (light/teal theme), supports web self-check-in via QR code.

---

## ✨ What's New (Redesign)

- **Soft Medical theme** — clean white panels, calming teal accents, warm amber CTAs
- **Bigger "Now Serving" hero card** — 44pt bold name, visible across the room
- **Friendlier UI** — rounded cards, colour-coded stat tiles, alternating table rows
- **Teal header + status stripe** — instantly communicates clinic branding
- **Better buttons** — icons, consistent sizing, clear hierarchy

---

## 🚀 Running the App

```bash
# 1. Install dependencies
pip install customtkinter Pillow Flask qrcode[pil]

# 2. Run
python main.py
```

---

## 📦 Building the Windows EXE

```bash
# 1. Install PyInstaller (Windows only)
pip install pyinstaller

# 2. Build
pyinstaller clinic_queue.spec --noconfirm

# Output: dist/ClinicQueue/ClinicQueue.exe
```

> **Tip:** If you don't have `assets/clinic_icon.ico` yet, remove the `icon=` line
> from `clinic_queue.spec` before building.

---

## 📁 Project Structure

```
clinic_queue_app/
├── main.py            # Entry point (logging + Flask thread + GUI launch)
├── app.py             # All CustomTkinter UI code
├── config.py          # Theme colours, fonts, sizes — edit here to retheme
├── queue_manager.py   # Priority + normal queue logic
├── models.py          # Patient data class
├── persistence.py     # JSON save/load
├── web_server.py      # Flask web check-in server
├── clinic_queue.spec  # PyInstaller EXE build spec
├── assets/
│   ├── clinic_qr.png  # QR code image (optional)
│   └── clinic_icon.ico# App icon for EXE (optional)
└── data/
    └── queue_state.json  # Auto-created; persists queue across sessions
```

---

## 🌐 Web Check-in

Once running, patients can self-register at **http://localhost:5000** — 
place a QR code pointing to that URL at `assets/clinic_qr.png`.
"# clinic-queue" 
