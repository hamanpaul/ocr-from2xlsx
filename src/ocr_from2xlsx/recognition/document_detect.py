"""Detect the form's quadrilateral in a field photo and perspective-warp it flat,
so the layout's *normalized* section bands (tiling.py) line up with the real form
regions instead of assuming the photo is framed exactly to the paper.

Real photos have margins, skew and perspective; the current normalized crop then
lands off the actual fields. This deskews first. The detector is deliberately
conservative — it accepts a quad only when it plausibly bounds the **page** (reaches
the frame edges, sane corner angles, A4-portrait output aspect) — and otherwise
returns the input UNCHANGED, so an enabled-but-unsure run never warps to a wrong
region (e.g. an inner ruled table) and is never worse than the no-correction path
(#59). Every path is wrapped so a cv2/Pillow error falls back to the input too.

cv2/numpy are imported lazily (matching capture.py) so importing this module does
not require OpenCV at collection time.
"""
from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    """Parse a float env override, falling back to the default on a bad value
    (mirrors factory.vision_config_from_env so a typo never crashes the run)."""
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


# A quad must cover a meaningful fraction of the frame AND reach the edges to be the
# page (not an inner table/logo/print border). The warped OUTPUT aspect must be ~A4
# portrait, else we'd be transposing the portrait layout onto a sideways/landscape
# detection — reject and fall back instead of guessing a 90deg rotation.
_MIN_AREA_FRAC = _env_float("SCAN_DEWARP_MIN_AREA", 0.35)
_ASPECT_MIN = _env_float("SCAN_DEWARP_ASPECT_MIN", 0.55)   # output width / height
_ASPECT_MAX = _env_float("SCAN_DEWARP_ASPECT_MAX", 0.95)   # A4 portrait is ~0.707
_EDGE_MARGIN = _env_float("SCAN_DEWARP_EDGE_MARGIN", 0.12)  # quad must reach within this of >=3 edges
_MIN_CORNER_DEG = _env_float("SCAN_DEWARP_MIN_ANGLE", 50.0)
_MIN_OUT_PX = 200          # reject postage-stamp warps that would feed near-empty crops
_DETECT_LONG_EDGE = 1200   # detect on a downscaled copy; warp the full-res image


def order_quad(pts):
    """Order four points as [top-left, top-right, bottom-right, bottom-left] using a
    tie-robust top-two / bottom-two split (the x+y / y-x trick collapses corners on
    axis-aligned and ~45deg-diamond quads)."""
    import numpy as np

    pts = np.asarray(pts, dtype="float32").reshape(4, 2)
    by_y = pts[np.argsort(pts[:, 1], kind="stable")]
    top, bottom = by_y[:2], by_y[2:]
    tl, tr = top[np.argsort(top[:, 0], kind="stable")]
    bl, br = bottom[np.argsort(bottom[:, 0], kind="stable")]
    return np.array([tl, tr, br, bl], dtype="float32")


def _corners_distinct(quad, min_sep: float = 5.0) -> bool:
    import numpy as np

    q = np.asarray(quad, dtype="float64")
    for i in range(4):
        for j in range(i + 1, 4):
            if np.linalg.norm(q[i] - q[j]) < min_sep:
                return False
    return True


def _corner_angles_ok(quad) -> bool:
    import numpy as np

    q = np.asarray(quad, dtype="float64")
    for i in range(4):
        a = q[(i - 1) % 4] - q[i]
        b = q[(i + 1) % 4] - q[i]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-3 or nb < 1e-3:
            return False
        cos = float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))
        angle = np.degrees(np.arccos(cos))
        if angle < _MIN_CORNER_DEG or angle > (180.0 - _MIN_CORNER_DEG):
            return False
    return True


def _bounds_page(quad, width: int, height: int) -> bool:
    """The quad must reach near the frame edge on >=3 sides — a centered inner table
    (margins on all sides) is rejected, a roughly full-framed page is accepted."""
    import numpy as np

    q = np.asarray(quad, dtype="float64")
    xs, ys = q[:, 0], q[:, 1]
    reached = 0
    reached += xs.min() <= _EDGE_MARGIN * width
    reached += xs.max() >= (1.0 - _EDGE_MARGIN) * width
    reached += ys.min() <= _EDGE_MARGIN * height
    reached += ys.max() >= (1.0 - _EDGE_MARGIN) * height
    return reached >= 3


def find_document_quad(image):
    """Return the page's 4 corners ordered TL,TR,BR,BL as a (4,2) float32 array, or
    ``None`` when no quad confidently bounds the page. ``image`` is BGR or grayscale."""
    import cv2
    import numpy as np

    gray = image if getattr(image, "ndim", 0) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    if frame_area <= 0:
        return None

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_area = 0.0
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        area = cv2.contourArea(approx)
        if area < _MIN_AREA_FRAC * frame_area or area <= best_area:
            continue
        quad = order_quad(approx.reshape(4, 2))
        if not (_corners_distinct(quad) and _corner_angles_ok(quad) and _bounds_page(quad, width, height)):
            continue
        best = quad
        best_area = area
    return best


def warp_document(image, quad):
    """Perspective-warp ``quad`` to a flat full-frame image. Output size = the quad's
    max edge lengths (no resolution thrown away). Returns ``None`` when the result is
    too small or not plausibly A4-portrait (so the caller falls back to the input)."""
    import cv2
    import numpy as np

    quad = np.asarray(quad, dtype="float32").reshape(4, 2)
    tl, tr, br, bl = quad
    out_w = int(round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    out_h = int(round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    if out_w < _MIN_OUT_PX or out_h < _MIN_OUT_PX:
        return None
    ratio = out_w / out_h
    if not (_ASPECT_MIN <= ratio <= _ASPECT_MAX):
        return None  # landscape / near-square -> would transpose the portrait bands
    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype="float32"
    )
    matrix = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(image, matrix, (out_w, out_h))


def _is_full_frame(quad, width: int, height: int, tol: float = 0.02) -> bool:
    """The quad already coincides with the frame corners (a flat scan / pre-cropped
    photo) — warping would be a pointless, slightly-lossy resample, so skip it."""
    import numpy as np

    frame = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype="float64")
    q = np.asarray(quad, dtype="float64")
    return float(np.linalg.norm(q - frame, axis=1).max()) <= tol * max(width, height)


def deskew_pil(pil_image):
    """PIL in -> PIL out: detect the page quad and warp it flat. Returns the input
    UNCHANGED when no confident page quad is found, when the page already fills the
    frame, or on any cv2/Pillow error — so callers can apply it unconditionally and it
    never regresses the no-correction path."""
    try:
        import cv2
        import numpy as np
        from PIL import Image

        full = np.asarray(pil_image.convert("RGB"))[:, :, ::-1]  # RGB -> BGR
        height, width = full.shape[:2]
        if height < 80 or width < 80:
            return pil_image

        # Detect on a downscaled copy (contours are scale-robust); warp at full res.
        scale = min(1.0, _DETECT_LONG_EDGE / float(max(height, width)))
        small = (
            cv2.resize(full, (max(1, round(width * scale)), max(1, round(height * scale))),
                       interpolation=cv2.INTER_AREA)
            if scale < 1.0
            else full
        )
        quad_small = find_document_quad(small)
        if quad_small is None:
            return pil_image
        quad = quad_small / scale  # back to full-res coordinates
        if _is_full_frame(quad, width, height):
            return pil_image
        warped = warp_document(full, quad)
        if warped is None:
            return pil_image
        return Image.fromarray(warped[:, :, ::-1])  # BGR -> RGB
    except Exception:
        return pil_image
