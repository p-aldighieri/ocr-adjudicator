#!/usr/bin/env python3
"""Generate the app icon with OpenAI gpt-image-1 and emit all PWA/Android sizes.
Outputs into ../public:  pwa-512.png, pwa-192.png, pwa-maskable-512.png, apple-touch-icon.png, favicon.svg(kept)
Usage: python gen_icon.py
"""
import base64, json, os, sys, urllib.request
from pathlib import Path
from PIL import Image
import io

OUT = Path(__file__).resolve().parent.parent / "public"
KEY = os.environ.get("OPENAI_API_KEY")

PROMPT = (
    "A modern minimalist mobile app icon for an OCR verification tool. "
    "Centerpiece: a stylized scanned document page with faint text lines, "
    "overlaid by a glowing rounded highlight box around one line (like a bounding box) "
    "and a small green check-mark badge in the lower right. "
    "Flat vector style, deep navy background (#0b0f14), teal/emerald (#34d399) and amber (#fbbf24) accents, "
    "soft glow, high contrast, crisp geometry, centered composition, generous padding, no text, "
    "no words, app-icon aesthetic, square."
)

def generate(path: Path):
    if not KEY:
        print("no OPENAI_API_KEY"); sys.exit(1)
    body = json.dumps({
        "model": "gpt-image-1", "prompt": PROMPT, "size": "1024x1024", "quality": "high", "n": 1,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    b64 = data["data"][0]["b64_json"]
    path.write_bytes(base64.b64decode(b64))
    print("saved raw icon ->", path)

def emit_sizes(src: Path):
    im = Image.open(src).convert("RGBA")
    im.resize((512, 512), Image.LANCZOS).save(OUT / "pwa-512.png")
    im.resize((192, 192), Image.LANCZOS).save(OUT / "pwa-192.png")
    im.resize((180, 180), Image.LANCZOS).save(OUT / "apple-touch-icon.png")
    # maskable: pad to ~80% safe zone on navy
    canvas = Image.new("RGBA", (512, 512), (11, 15, 20, 255))
    inner = im.resize((410, 410), Image.LANCZOS)
    canvas.paste(inner, (51, 51), inner)
    canvas.save(OUT / "pwa-maskable-512.png")
    print("emitted pwa-512, pwa-192, apple-touch-icon, pwa-maskable-512")

if __name__ == "__main__":
    raw = OUT / "icon-raw.png"
    generate(raw)
    emit_sizes(raw)
