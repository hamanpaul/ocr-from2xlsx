"""Crop the layout's section bands from an upright form image (Pillow).

Produces one crop per section for the VLM. Generous proportional bands — not 6px
geometry — so this tolerates the fixed-camera framing.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from ocr_from2xlsx.recognition.layout import Section, band_pixels


def crop_sections(
    image_path: str | os.PathLike[str],
    layout: tuple[Section, ...],
    out_dir: str | os.PathLike[str],
    rotate: int = 0,
) -> dict[str, str]:
    """Crop each section band; return ``{section_key: crop_path}``."""
    image = Image.open(image_path).convert("RGB")
    if rotate:
        image = image.rotate(-rotate, expand=True)  # PIL rotates CCW; negate for clockwise
    width, height = image.size
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    crops: dict[str, str] = {}
    for section in layout:
        crop_path = out / f"{section.key}.png"
        image.crop(band_pixels(section.band, width, height)).save(crop_path)
        crops[section.key] = str(crop_path)
    return crops
