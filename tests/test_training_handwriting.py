from __future__ import annotations

from pathlib import Path
from random import Random

import pytest

pytest.importorskip("PIL")
from PIL import Image

from training.handwriting import draw_text


def _windows_font() -> Path:
    fonts_dir = Path(r"C:\Windows\Fonts")
    for name in ("arial.ttf", "segoeui.ttf", "tahoma.ttf"):
        path = fonts_dir / name
        if path.exists():
            return path
    pytest.skip("requires one of arial.ttf, segoeui.ttf, or tahoma.ttf")


def _ink_pixels(image: Image.Image) -> list[tuple[int, int]]:
    pixels = image.load()
    return [(x, y) for y in range(image.height) for x in range(image.width) if pixels[x, y] < 255]


def test_draw_text_keeps_ink_inside_target_box() -> None:
    image = Image.new("L", (64, 64), color=255)

    draw_text(image, (10.0, 10.0, 40.0, 22.0), "TEST", _windows_font(), Random(11))

    ink_pixels = _ink_pixels(image)
    assert ink_pixels
    assert all(10 <= x < 40 and 10 <= y < 22 for x, y in ink_pixels), ink_pixels
