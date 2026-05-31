from __future__ import annotations

from math import ceil, floor
from pathlib import Path
from random import Random
from typing import Optional, Union


def list_handwriting_fonts(fonts_dir: Union[str, Path]) -> list[Path]:
    root = Path(fonts_dir)
    if not root.is_dir():
        return []
    return sorted(
        [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in {".ttf", ".ttc"}],
        key=lambda path: path.name.lower(),
    )


def _normalize_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    left = floor(x0)
    top = floor(y0)
    right = max(left + 1, ceil(x1))
    bottom = max(top + 1, ceil(y1))
    return left, top, right, bottom


def draw_text(
    image,
    box: tuple[float, float, float, float],
    text: str,
    font_path: Union[str, Path],
    rng: Random,
) -> None:
    if not text:
        return

    from PIL import ImageDraw, ImageFont

    left, top, right, bottom = _normalize_box(box)
    width = max(1, right - left)
    height = max(1, bottom - top)

    draw = ImageDraw.Draw(image)
    min_size = max(8, int(height * 0.55))
    max_size = max(min_size, min(48, int(height * 0.95)))
    size = rng.randint(min_size, max_size)

    while True:
        font = ImageFont.truetype(str(font_path), size=size)
        text_box = draw.textbbox((0, 0), text, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        if text_width <= max(1, width - 2) or size <= 8:
            break
        size -= 1

    max_x = max(left, right - text_width - 1)
    max_y = max(top, bottom - text_height - 1)
    base_y = top + max(0, (height - text_height) // 2)
    x_jitter = rng.randint(-max(1, width // 10), max(1, width // 10))
    y_jitter = rng.randint(-max(1, height // 10), max(1, height // 10))
    text_x = min(max(left, left + 1 + x_jitter), max_x)
    text_y = min(max(top, base_y + y_jitter), max_y)
    draw.text((text_x, text_y), text, fill=0, font=font)


def draw_mark(
    image,
    box: tuple[float, float, float, float],
    rng: Random,
    style: Optional[str] = None,
) -> str:
    from PIL import ImageDraw

    left, top, right, bottom = _normalize_box(box)
    width = max(1, right - left)
    height = max(1, bottom - top)
    mark_style = style or rng.choice(("tick", "dash", "blackout"))
    stroke = max(1, int(round(min(width, height) * 0.16)))
    inset = max(1, int(round(min(width, height) * 0.18)))
    draw = ImageDraw.Draw(image)

    if mark_style == "tick":
        start = (
            left + inset + rng.randint(0, max(1, width // 8)),
            top + height // 2 + rng.randint(0, max(1, height // 6)),
        )
        mid = (
            left + width // 2 + rng.randint(-max(1, width // 12), max(1, width // 12)),
            bottom - inset - rng.randint(0, max(1, height // 8)),
        )
        end = (
            right - inset - rng.randint(0, max(1, width // 10)),
            top + inset + rng.randint(0, max(1, height // 8)),
        )
        draw.line((start, mid, end), fill=0, width=stroke)
    elif mark_style == "dash":
        y = top + height // 2 + rng.randint(-max(1, height // 8), max(1, height // 8))
        draw.line(
            (
                (left + inset, y),
                (right - inset, y),
            ),
            fill=0,
            width=stroke,
        )
    elif mark_style == "blackout":
        draw.rectangle((left + inset, top + inset, right - inset, bottom - inset), fill=0)
    else:
        raise ValueError(f"unsupported mark style: {mark_style!r}")

    return mark_style
