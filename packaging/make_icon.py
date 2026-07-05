"""Generate the RESOPT app icon (.icns for macOS, .ico for Windows, .png).

Design: "Editor's Mark" (Paper Studio brand) — a warm paper rounded square with
a vermilion stamp circle and a serif "R" in paper white. Matches the in-app
palette: paper #F6F1E7, ink #16181D, vermilion #E4572E.
Run:  python packaging/make_icon.py
"""
from __future__ import annotations

import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "assets")
os.makedirs(OUT, exist_ok=True)

S = 1024
PAPER = (246, 241, 231, 255)      # #F6F1E7
VERMILION = (228, 87, 46, 255)    # #E4572E
LINE = (227, 218, 202, 255)       # #E3DACA — hairline keyline so the icon reads on white


def _round_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    return m


def _serif_bold(size: int) -> ImageFont.FreeTypeFont:
    """Best available bold serif. Georgia ships on macOS and Windows (incl. the CI
    runners); Times/DejaVu are fallbacks so the build never hard-fails on fonts."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "C:/Windows/Fonts/timesbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    print("WARNING: no serif font found — falling back to PIL default")
    return ImageFont.load_default(size)


def build_master() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Paper rounded square with a hairline keyline (visible on white docks/folders).
    radius = int(S * 0.225)
    paper = Image.new("RGBA", (S, S), PAPER)
    img.paste(paper, (0, 0), _round_mask(S, radius))
    d.rounded_rectangle([3, 3, S - 4, S - 4], radius=radius, outline=LINE, width=6)

    # The vermilion stamp.
    cx = cy = S // 2
    r = int(S * 0.3125)  # 320px at 1024 — same proportion as the approved mockup
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=VERMILION)

    # Serif "R" in paper white, sized to ~62% of the stamp's diameter, optically
    # centered (bbox-centering, then a hair down so the cap sits balanced).
    target_h = int(2 * r * 0.62)
    size = target_h
    font = _serif_bold(size)
    for _ in range(6):  # converge glyph height onto the target
        box = d.textbbox((0, 0), "R", font=font)
        h = box[3] - box[1]
        if abs(h - target_h) <= 4:
            break
        size = max(8, int(size * target_h / max(h, 1)))
        font = _serif_bold(size)
    d.text((cx, cy + int(S * 0.004)), "R", font=font, fill=PAPER, anchor="mm")
    return img


def main():
    master = build_master()
    png = os.path.join(OUT, "icon.png")
    master.save(png)

    # .ico (Windows)
    master.save(os.path.join(OUT, "icon.ico"),
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # .icns (macOS) via iconutil
    iconset = os.path.join(OUT, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for sz in (16, 32, 64, 128, 256, 512, 1024):
        master.resize((sz, sz), Image.LANCZOS).save(os.path.join(iconset, f"icon_{sz}x{sz}.png"))
        if sz <= 512:
            master.resize((sz * 2, sz * 2), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{sz}x{sz}@2x.png"))
    try:
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(OUT, "icon.icns")],
                       check=True)
        print("wrote icon.icns")
    except Exception as e:  # noqa: BLE001
        print("iconutil failed (mac only):", e)
    print("Icons written to", OUT)


if __name__ == "__main__":
    main()
