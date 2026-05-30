"""
generate_qr.py
==============
Run this ONCE after your Railway app is deployed to generate the permanent QR code.

Usage:
    python generate_qr.py https://your-app.up.railway.app

The QR image is saved to assets/clinic_qr.png and also printed to the terminal.
"""

import sys
from pathlib import Path

try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Install dependencies first:  pip install qrcode[pil] Pillow")
    sys.exit(1)

URL = sys.argv[1] if len(sys.argv) > 1 else input("Enter your Railway URL: ").strip()

if not URL.startswith("http"):
    URL = "https://" + URL

OUT = Path(__file__).parent / "assets" / "clinic_qr.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

qr = qrcode.QRCode(
    version=None,            # auto-size
    error_correction=qrcode.constants.ERROR_CORRECT_H,  # 30 % recovery
    box_size=10,
    border=4,
)
qr.add_data(URL)
qr.make(fit=True)

img = qr.make_image(fill_color="#0C7472", back_color="white").convert("RGB")

# Add a small label below the QR
W, H = img.size
LABEL_H = 40
canvas = Image.new("RGB", (W, H + LABEL_H), "white")
canvas.paste(img, (0, 0))

draw = ImageDraw.Draw(canvas)
try:
    font = ImageFont.truetype("arial.ttf", 18)
except IOError:
    font = ImageFont.load_default()

text = "Clinic Self Check-In"
bbox = draw.textbbox((0, 0), text, font=font)
tw = bbox[2] - bbox[0]
draw.text(((W - tw) // 2, H + 6), text, fill="#0C7472", font=font)

canvas.save(OUT)
print(f"\n✅  QR code saved to: {OUT}")
print(f"    Points to: {URL}")
print("\nCommit assets/clinic_qr.png to your repo — this QR never changes.")
