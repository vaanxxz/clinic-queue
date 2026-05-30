# 🚂 Railway Deployment Guide — Clinic Queue v6

## Overview

This guide deploys the **web check-in server only** to Railway.
The QR code is generated once from your permanent Railway URL and committed
to the repo — it never needs to change.

The desktop GUI (`app.py`) still runs locally on the clinic PC as before.

---

## Step 1 — Push your code to GitHub

1. Create a new GitHub repo (e.g. `clinic-queue`).
2. Copy the updated project files into it.
3. Make sure `.gitignore` excludes `data/` (queue state is ephemeral on Railway):

```
# .gitignore
data/
__pycache__/
*.pyc
dist/
build/
```

4. **Do commit** `assets/clinic_qr.png` once you generate it (Step 3).

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/clinic-queue.git
git push -u origin main
```

---

## Step 2 — Deploy on Railway

1. Go to **[railway.app](https://railway.app)** → **New Project → Deploy from GitHub repo**.
2. Select your `clinic-queue` repo.
3. Railway auto-detects Python and reads `Procfile`:
   ```
   web: python railway_server.py
   ```
4. Click **Deploy**. Wait ~60 seconds for the build to finish.
5. Go to **Settings → Networking → Generate Domain**.
   You'll get a permanent URL like:
   ```
   https://clinic-queue-production.up.railway.app
   ```
   > ⚠️ **Copy this URL — it never changes as long as the project exists.**

---

## Step 3 — Generate the QR code (once)

On your local machine (with the project folder open):

```bash
pip install qrcode[pil] Pillow   # if not already installed
python generate_qr.py https://clinic-queue-production.up.railway.app
```

This saves `assets/clinic_qr.png` — a teal QR code pointing to your Railway URL.

Then commit it:
```bash
git add assets/clinic_qr.png
git commit -m "Add permanent QR code"
git push
```

Railway redeploys automatically. The QR code is now baked into the container.

---

## Step 4 — Display the QR in the desktop app

The desktop `app.py` reads `assets/clinic_qr.png` and shows it in the sidebar.
No code change needed — it already loads whatever image is at that path.

**Print the QR** and stick it at the reception desk. Students scan it →
they land on your Railway URL → they fill in their student number.

---

## Environment variables (optional)

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Set automatically by Railway — do not set manually |
| `SECRET_KEY` | — | Add in Railway Settings → Variables if you add sessions later |

---

## How the permanent URL works

Railway gives each **project** a stable domain. As long as you don't:
- Delete the project, or
- Remove the custom domain

…the URL stays the same forever. Redeployments, code pushes, and restarts
do **not** change the URL. This is why the QR code only needs to be generated once.

---

## Local vs Railway — what runs where

| Component | Local (clinic PC) | Railway |
|---|---|---|
| Desktop GUI (`app.py`) | ✅ runs | ❌ not needed |
| Flask web check-in | optional (port 5000) | ✅ always on |
| Queue state | `data/queue_state.json` | in-memory (resets on redeploy) |
| QR code image | `assets/clinic_qr.png` | served as static asset |

> **Note on queue state:** Railway's filesystem is ephemeral — the JSON
> queue state resets on each redeploy. The web check-in form still works;
> patients join the queue and get their position. If you need the queue
> to survive redeploys, add a free PostgreSQL or Redis add-on in Railway
> and update `persistence.py` accordingly.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Build fails with `customtkinter` error | ✅ Already fixed — `requirements.txt` no longer includes GUI packages |
| `PORT` not found | Railway sets `$PORT` automatically; `railway_server.py` reads it |
| QR scan goes to wrong URL | Re-run `generate_qr.py` with the correct Railway URL |
| App crashes on start | Check Railway Logs tab for the Python traceback |
