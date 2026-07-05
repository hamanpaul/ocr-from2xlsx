"""Generate the review-app toolbar icons as PNGs (offline, reproducible).

Simple monochrome line glyphs drawn with Pillow — no network, no icon-font
dependency, no emoji. White glyphs read on the teal toolbar band; the confirm
glyph is drawn dark so it reads on the amber primary button. Rendered at a large
size and downscaled by `theme.load_icon` at display time.

Run: python build/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "ocr_from2xlsx" / "assets" / "icons"
S = 96  # master canvas size
W = 7   # stroke width
WHITE = (255, 255, 255, 255)
DARK = (61, 44, 0, 255)  # matches theme on_accent (#3D2C00) for the amber button


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _line(d, pts, color, width=W):
    d.line(pts, fill=color, width=width, joint="curve")
    r = width // 2
    for x, y in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def open_report(color=WHITE):
    img, d = _canvas()
    # document with a folded corner
    d.line([(26, 18), (26, 78), (70, 78), (70, 34)], fill=color, width=W, joint="curve")
    d.line([(26, 18), (58, 18), (70, 34)], fill=color, width=W, joint="curve")
    d.line([(58, 18), (58, 34), (70, 34)], fill=color, width=W)
    for y in (44, 56, 68):
        d.line([(36, y), (60, y)], fill=color, width=max(3, W - 2))
    return img


def import_folder(color=WHITE):
    img, d = _canvas()
    # folder
    d.line([(20, 40), (20, 76), (78, 76), (78, 34), (46, 34), (40, 26), (20, 26), (20, 40)],
           fill=color, width=W, joint="curve")
    # down arrow into it
    d.line([(49, 40), (49, 62)], fill=color, width=W)
    d.line([(39, 52), (49, 63), (59, 52)], fill=color, width=W, joint="curve")
    return img


def prev(color=WHITE):
    img, d = _canvas()
    _line(d, [(58, 22), (36, 48), (58, 74)], color)
    return img


def nxt(color=WHITE):
    img, d = _canvas()
    _line(d, [(40, 22), (62, 48), (40, 74)], color)
    return img


def confirm(color=DARK):
    img, d = _canvas()
    _line(d, [(26, 50), (44, 68), (74, 30)], color, width=W + 1)
    return img


def moon(color=WHITE):
    img, d = _canvas()
    # crescent = big disc minus an offset disc
    big = Image.new("L", (S, S), 0)
    ImageDraw.Draw(big).ellipse([22, 18, 78, 74], fill=255)
    cut = Image.new("L", (S, S), 0)
    ImageDraw.Draw(cut).ellipse([40, 12, 96, 68], fill=255)
    from PIL import ImageChops

    mask = ImageChops.subtract(big, cut)
    solid = Image.new("RGBA", (S, S), color)
    img.paste(solid, (0, 0), mask)
    return img


ICONS = {
    "open": open_report,
    "import": import_folder,
    "prev": prev,
    "next": nxt,
    "confirm": confirm,
    "moon": moon,
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in ICONS.items():
        fn().save(OUT / f"{name}.png")
    print(f"wrote {len(ICONS)} icons to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
