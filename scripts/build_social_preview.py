#!/usr/bin/env python3
"""Generate a stable 1200x630 PNG social preview for X/Open Graph crawlers.

The public website is JS-driven, so social bots need a static, publicly
retrievable image. No fake games, odds or win records appear in the graphic.
"""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "social-preview.png"
PAGE = ROOT / "docs" / "index.html"
W, H = 1200, 630

DARK = "#090f18"
HEADER = "#0c1420"
PANEL = "#131f2d"
PANEL_2 = "#182635"
LINE = "#304255"
WHITE = "#f1f6fa"
FAINT = "#92a7b6"
LIME = "#c9f582"
CYAN = "#7edacf"

def font(size: int, heavy: bool = False):
    basename = "DejaVuSans-Bold.ttf" if heavy else "DejaVuSans.ttf"
    paths = [
        Path("/usr/share/fonts/truetype/dejavu") / basename,
        Path("/usr/local/share/fonts") / basename,
    ]
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw():
    im = Image.new("RGB", (W, H), DARK)
    pen = ImageDraw.Draw(im)

    # Static dark-mode styling consistent with the actual Tedgy Trends site.
    pen.rectangle((0, 0, W, 91), fill=HEADER)
    pen.rectangle((0, 89, W, 92), fill=LINE)
    pen.rectangle((0, 89, 450, 92), fill=LIME)
    for inset in range(0, 125, 4):
        # Restrained neon accent on the right, not a fabricated dashboard value.
        pen.arc((930 + inset // 5, 145 + inset // 2, 1375 - inset, 590 - inset // 2),
                190, 320, fill="#173b41", width=2)

    # Website brand logo is embedded in the actual site's HTML. Reuse it if
    # present, otherwise render a simple neutral mark.
    logo_ok = False
    try:
        html = PAGE.read_text(encoding="utf-8")
        m = re.search(r"data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", html)
        if m:
            logo = Image.open(BytesIO(base64.b64decode(m.group(1)))).convert("RGBA")
            logo.thumbnail((61, 61), Image.Resampling.LANCZOS)
            im.paste(logo, (36 + (61 - logo.width)//2, 15 + (61 - logo.height)//2), logo)
            logo_ok = True
    except Exception:
        pass
    if not logo_ok:
        pen.rounded_rectangle((36, 15, 97, 76), radius=13, outline=LIME, width=3)
        pen.text((46, 26), "TT", font=font(23, True), fill=LIME)

    pen.text((115, 21), "TEDGY TRENDS", font=font(25, True), fill=WHITE)
    pen.text((117, 55), "NFL MODEL & ANALYTICS", font=font(11, True), fill=FAINT)
    pen.rounded_rectangle((961, 25, 1156, 65), radius=19, outline=LINE, width=2)
    pen.text((987, 35), "NFL PROJECTIONS", font=font(15, True), fill=CYAN)

    pen.text((47, 142), "2026 NFL  /  MODEL PROJECTIONS", font=font(18, True), fill=LIME)
    pen.text((42, 184), "THE BOARD.", font=font(76, True), fill=WHITE)
    pen.text((47, 286), "Projections, market comparisons, and model results.", font=font(24), fill=FAINT)

    # Stylized website cards — labels only, no invented scores or bet records.
    cards = [
        (46, "BASELINE", "Historical team performance"),
        (613, "INJURY-ADJUSTED", "Player availability & quarterback EPA"),
    ]
    for left, heading, description in cards:
        right = left + 539
        pen.rounded_rectangle((left, 366, right, 532), radius=19, fill=PANEL, outline=LINE, width=2)
        pen.rectangle((left + 22, 390, left + 29, 423), fill=LIME if left == 46 else CYAN)
        pen.text((left + 44, 384), heading, font=font(23, True), fill=WHITE)
        pen.text((left + 25, 447), description, font=font(17), fill=FAINT)
        pen.line((left + 25, 491, right - 25, 491), fill=LINE, width=2)
        pen.text((left + 25, 505), "ATS   •   TOTALS   •   PROJECTED SCORES",
                 font=font(12, True), fill=CYAN)

    pen.line((46, 575, 1154, 575), fill=LINE, width=2)
    pen.text((47, 589), "PUBLIC NFL MODEL RESEARCH", font=font(13, True), fill=FAINT)
    pen.text((940, 589), "TEDGY TRENDS", font=font(13, True), fill=LIME)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    im.save(OUTPUT, format="PNG", optimize=True)
    image_check = Image.open(OUTPUT)
    if image_check.size != (W, H) or image_check.format != "PNG":
        raise RuntimeError("Unexpected social preview image output")
    if OUTPUT.stat().st_size > 4_000_000:
        raise RuntimeError("Social preview image too large")
    print(f"Created {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, {W}x{H})")

if __name__ == "__main__":
    draw()
