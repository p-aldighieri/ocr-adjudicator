#!/usr/bin/env python3
"""Draw the app icon locally with PIL (no network) and emit all PWA/Android sizes.
Theme: scanned document + a teal bounding-box highlight on one line + green check badge,
on the app's navy background. Outputs into ../public.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "public"
S = 1024

NAVY_TOP = (13, 18, 26)
NAVY_BOT = (7, 11, 16)
PAPER = (233, 238, 243)
LINE = (148, 163, 184)
TEAL = (52, 211, 153)
AMBER = (251, 191, 36)
GREEN = (34, 197, 94)


def vgrad(size, top, bot):
    g = Image.new("RGB", (1, size), 0)
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return g.resize((size, size))


def rounded(draw, box, r, **kw):
    draw.rounded_rectangle(box, radius=r, **kw)


def build():
    img = vgrad(S, NAVY_TOP, NAVY_BOT).convert("RGBA")

    # soft teal glow behind the document
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([S * 0.18, S * 0.18, S * 0.82, S * 0.82], fill=(52, 211, 153, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    img = Image.alpha_composite(img, glow)

    # document layer (drawn upright, then rotated)
    doc = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(doc)
    dx0, dy0, dx1, dy1 = 300, 210, 724, 814
    # drop shadow
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([dx0 + 14, dy0 + 20, dx1 + 14, dy1 + 20], radius=34, fill=(0, 0, 0, 150))
    doc = Image.alpha_composite(doc, sh.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(doc)
    rounded(d, [dx0, dy0, dx1, dy1], 34, fill=PAPER)

    # text lines
    pad = 54
    lx0, lx1 = dx0 + pad, dx1 - pad
    ys = [dy0 + 90 + i * 78 for i in range(7)]
    widths = [1.0, 0.82, 0.62, 0.9, 0.7, 0.86, 0.5]
    for y, w in zip(ys, widths):
        rounded(d, [lx0, y, lx0 + (lx1 - lx0) * w, y + 26], 13, fill=LINE)

    # highlight: the "value" line (index 2) — amber bar + teal bounding box
    hy = ys[2]
    rounded(d, [lx0, hy, lx0 + (lx1 - lx0) * 0.62, hy + 26], 13, fill=AMBER)
    d.rounded_rectangle([lx0 - 22, hy - 26, lx1 + 6, hy + 52], radius=22, outline=TEAL, width=14)

    doc = doc.rotate(-7, resample=Image.BICUBIC, center=(512, 512))
    img = Image.alpha_composite(img, doc)

    # green check badge (upright, bottom-right of document)
    badge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    b = ImageDraw.Draw(badge)
    cx, cy, r = 712, 768, 116
    b.ellipse([cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10], fill=(7, 11, 16, 255))  # ring gap
    b.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GREEN)
    b.line([(cx - 52, cy + 4), (cx - 14, cy + 44), (cx + 58, cy - 46)], fill=(255, 255, 255, 255), width=26, joint="curve")
    img = Image.alpha_composite(img, badge)

    return img.convert("RGBA")


def emit(im):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon-raw.png").write_bytes(b"")  # placeholder cleared below
    im.save(OUT / "icon-raw.png")
    im.resize((512, 512), Image.LANCZOS).save(OUT / "pwa-512.png")
    im.resize((192, 192), Image.LANCZOS).save(OUT / "pwa-192.png")
    im.resize((180, 180), Image.LANCZOS).save(OUT / "apple-touch-icon.png")
    im.resize((512, 512), Image.LANCZOS).save(OUT / "pwa-maskable-512.png")  # already full-bleed navy
    # favicon
    im.resize((48, 48), Image.LANCZOS).save(OUT / "favicon.png")
    print("wrote icons to", OUT)


if __name__ == "__main__":
    emit(build())
