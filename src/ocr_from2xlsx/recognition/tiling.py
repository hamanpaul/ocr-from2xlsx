"""Crop the layout's section bands from an upright form image (Pillow).

Produces one crop per section for the VLM. Generous proportional bands — not 6px
geometry — so this tolerates the fixed-camera framing.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageOps

from ocr_from2xlsx.recognition.layout import Section, band_pixels


def crop_sections(
    image_path: str | os.PathLike[str],
    layout: tuple[Section, ...],
    out_dir: str | os.PathLike[str],
    rotate: int = 0,
    enhance: bool = True,
    correct_perspective: bool = False,
) -> dict[str, str]:
    """Crop each section band; return ``{section_key: crop_path}``.

    With ``enhance`` (default), each crop is converted to greyscale and
    auto-contrasted — Phase 0 showed this gives the small VLM cleaner, more
    consistently-structured output on checkbox sections.

    With ``correct_perspective`` (#59), the form is detected and perspective-warped
    flat *before* the normalized bands are cropped, so the crops line up with the real
    fields on a skewed / margined photo. Falls back to the un-warped image when no
    confident document quad is found, so it never regresses framing.
    """
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source.convert("RGB"))  # honor camera orientation tag
    if rotate:
        image = image.rotate(-rotate, expand=True)  # PIL rotates CCW; negate for clockwise
    if correct_perspective:
        from ocr_from2xlsx.recognition.document_detect import deskew_pil, load_calibration

        # Prefer the operator's fixed-camera corner calibration; auto-detect otherwise.
        image = deskew_pil(image, calibration=load_calibration())
    width, height = image.size
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    crops: dict[str, str] = {}
    for section in layout:
        crop_path = out / f"{section.key}.png"
        crop = image.crop(band_pixels(section.band, width, height))
        if enhance:
            crop = ImageOps.autocontrast(ImageOps.grayscale(crop), cutoff=2)
        crop.save(crop_path)
        crops[section.key] = str(crop_path)
    return crops
