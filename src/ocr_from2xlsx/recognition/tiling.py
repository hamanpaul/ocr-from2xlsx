"""Crop the layout's section bands from an upright form image (Pillow).

Produces one crop per section for the VLM. Generous proportional bands — not 6px
geometry — so this tolerates the fixed-camera framing.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageOps

from ocr_from2xlsx.recognition.layout import Section, band_pixels

# #60: per-crop preprocessing modes, A/B-selectable via OCR_VLM_PREPROCESS. "autocontrast"
# is the existing default (no behaviour change). The others are evaluated on real photos.
_PREPROCESS_MODES = {"autocontrast", "clahe", "binarize", "none", "raw"}


def resolve_preprocess_mode(explicit: str | None = None) -> str:
    if explicit:
        mode = explicit.strip().lower()
    else:
        mode = (os.environ.get("OCR_VLM_PREPROCESS") or "autocontrast").strip().lower()
    return mode if mode in _PREPROCESS_MODES else "autocontrast"


def enhance_crop(crop: "Image.Image", mode: str) -> "Image.Image":
    """Apply the selected per-crop enhancement (#60). 'autocontrast' = the prior default."""
    if mode == "raw":
        return crop
    gray = ImageOps.grayscale(crop)
    if mode == "none":
        return gray
    if mode == "autocontrast":
        return ImageOps.autocontrast(gray, cutoff=2)
    import cv2
    import numpy as np

    arr = np.asarray(gray)
    if mode == "clahe":
        arr = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(arr)
    elif mode == "binarize":
        arr = cv2.adaptiveThreshold(
            arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
        )
    return Image.fromarray(arr)


def crop_sections(
    image_path: str | os.PathLike[str],
    layout: tuple[Section, ...],
    out_dir: str | os.PathLike[str],
    rotate: int = 0,
    enhance: bool = True,
    correct_perspective: bool = False,
    preprocess_mode: str | None = None,
) -> dict[str, str]:
    """Crop each section band; return ``{section_key: crop_path}``.

    With ``enhance`` (default), each crop is enhanced for the small VLM. The enhancement
    is selectable via ``preprocess_mode`` / ``OCR_VLM_PREPROCESS`` (#60): ``autocontrast``
    (default; greyscale + autocontrast, the prior behaviour), ``clahe``, ``binarize`` or
    ``none``. ``enhance=False`` keeps the raw colour crop.

    With ``correct_perspective`` (#59), the form is detected and perspective-warped
    flat *before* the normalized bands are cropped, so the crops line up with the real
    fields on a skewed / margined photo. Falls back to the un-warped image when no
    confident document quad is found, so it never regresses framing.
    """
    mode = resolve_preprocess_mode(preprocess_mode) if enhance else "raw"
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
        crop = enhance_crop(crop, mode)
        crop.save(crop_path)
        crops[section.key] = str(crop_path)
    return crops
