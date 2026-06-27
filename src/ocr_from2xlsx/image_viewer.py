"""Pure pan/zoom transform + field->region resolution for the review image viewer.

No Tk/cv2 — geometry only, unit-testable; the Canvas viewer in app.py applies these,
mirroring the repo's pure-logic helpers (review_nav / band_pixels)."""
from __future__ import annotations

MIN_ZOOM = 1.0
MAX_ZOOM = 8.0

# Per-field vertical bands over the FLATTENED 服務紀錄表 form, derived from that sheet's
# actual row geometry (cumulative row heights of rows 1..48; full width per field). These
# replace the prior hand-guessed recognition bands for the review-image framing so focusing
# a field frames the matching form row instead of an eyeballed region (#review-field-align).
# The frame is the field area row1-top..row48-bottom; map these to the real (skewed) photo
# with ``map_band_to_raw`` + the operator's 4-corner calibration.
_FIELD_ROW_BANDS: dict[str, tuple[float, float]] = {
    "service_date": (0.0478, 0.0800),
    "services.consultation.health_medical": (0.1009, 0.1400),
    "services.consultation.symptom_side_effect": (0.1400, 0.1783),
    "services.consultation.nutrition_diet": (0.1783, 0.2165),
    "services.consultation.psychosocial_emotion": (0.2165, 0.2548),
    "services.consultation.financial_social": (0.2548, 0.2930),
    "services.consultation.care_support": (0.2930, 0.3313),
    "services.supplies": (0.3313, 0.3504),
    "services.internal_referrals": (0.3504, 0.3887),
    "services.external_referrals": (0.3887, 0.4270),
    "services.referral_outcomes": (0.4270, 0.4591),
    "identity": (0.4800, 0.5174),
    "name": (0.4800, 0.5174),
    "medical_record_no": (0.4800, 0.5174),
    "gender": (0.5365, 0.5939),
    "patient_fields.nationality": (0.5939, 0.6322),
    "patient_fields.age_group": (0.6322, 0.7670),
    "patient_fields.channel": (0.7878, 0.8270),
    "patient_fields.disease_status": (0.8270, 0.8652),
    "patient_fields.source": (0.8652, 0.8843),
    "patient_fields.cancers": (0.8843, 0.9800),
    "patient_fields.newly_diagnosed_within_year": (0.9800, 1.0000),
}


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
    """The 0..1 band (x0, y0, x1, y1) over the FLATTENED form covering ``record_path``'s row,
    or ``None`` when the field has no mapped row (the viewer then leaves its view unchanged).
    Full width per field — focusing a field frames its whole form row (label + every option).
    Vertical extents come from the 服務紀錄表 sheet's real row geometry, not eyeballed guesses
    (#review-field-align). To frame the actual (skewed) photo, pass this through
    ``map_band_to_raw`` with the operator's corner calibration."""
    band = _FIELD_ROW_BANDS.get(record_path)
    if band is None:
        return None
    y0, y1 = band
    return (0.0, y0, 1.0, y1)


def _order_quad(corners: list) -> list:
    """Order 4 (x, y) corners as TL, TR, BR, BL (mirrors document_detect.order_quad), so a
    calibration saved in any click order still maps consistently."""
    pts = [(float(x), float(y)) for x, y in corners]
    by_sum = sorted(pts, key=lambda p: p[0] + p[1])
    tl, br = by_sum[0], by_sum[-1]
    by_diff = sorted(pts, key=lambda p: p[0] - p[1])
    bl, tr = by_diff[0], by_diff[-1]
    return [tl, tr, br, bl]


def map_band_to_raw(
    band: tuple[float, float, float, float], calibration: list
) -> tuple[float, float, float, float]:
    """Map a flattened-form band (0..1) onto the raw photo via the 4-corner calibration,
    returning the axis-aligned 0..1 bounding band to frame. ``calibration`` is the form's
    corners in raw-image 0..1 (any click order). The flattened unit square's corners map to
    TL/TR/BR/BL; each band corner is bilinearly interpolated across that quad and the result
    is the bounding box (a rectangle warps to a quad on the skewed photo; we frame its bbox)."""
    tl, tr, br, bl = _order_quad(calibration)

    def at(u: float, v: float) -> tuple[float, float]:
        top_x = tl[0] + u * (tr[0] - tl[0])
        top_y = tl[1] + u * (tr[1] - tl[1])
        bot_x = bl[0] + u * (br[0] - bl[0])
        bot_y = bl[1] + u * (br[1] - bl[1])
        return (top_x + v * (bot_x - top_x), top_y + v * (bot_y - top_y))

    x0, y0, x1, y1 = band
    pts = [at(x0, y0), at(x1, y0), at(x1, y1), at(x0, y1)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))
