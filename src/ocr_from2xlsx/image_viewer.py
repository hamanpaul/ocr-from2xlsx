"""Pure pan/zoom transform + field->region resolution for the review image viewer.

No Tk/cv2 — geometry only, unit-testable; the Canvas viewer in app.py applies these,
mirroring the repo's pure-logic helpers (review_nav / band_pixels)."""
from __future__ import annotations

from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT

MIN_ZOOM = 1.0
MAX_ZOOM = 8.0


def clamp_zoom(zoom: float, min_zoom: float = MIN_ZOOM, max_zoom: float = MAX_ZOOM) -> float:
    return max(min_zoom, min(max_zoom, zoom))


def anchored_origin(origin: float, cursor: float, old_zoom: float, new_zoom: float) -> float:
    """New image-space origin (left/top edge) after zooming from ``old_zoom`` to
    ``new_zoom`` so the content under ``cursor`` (canvas px from the edge) stays put."""
    if old_zoom <= 0 or new_zoom <= 0:
        return origin
    return origin + cursor * (1.0 / old_zoom - 1.0 / new_zoom)


def clamp_origin(origin: float, image_size: int, view_size: int, zoom: float) -> float:
    """Keep the visible window (``view_size / zoom`` image px) inside the image."""
    if zoom <= 0:
        return 0.0
    window = view_size / zoom
    max_origin = max(0.0, image_size - window)
    return max(0.0, min(origin, max_origin))


def field_region(record_path: str) -> tuple[float, float, float, float] | None:
    """The 0..1 section band (x0, y0, x1, y1) of the section that recognizes ``record_path``,
    or ``None`` when no section covers it (the viewer then leaves its view unchanged)."""
    for section in SERVICE_RECORD_V1_LAYOUT:
        fields = {option.field for option in section.options}
        fields |= {value.field for value in section.values}
        if record_path in fields:
            return section.band
    return None
