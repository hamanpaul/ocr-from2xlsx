"""Optional OpenCV enhancement for captured document images."""
from __future__ import annotations

MIN_LONG_EDGE = 2000


def enhance(image):
    """Return a denoised grayscale capture, upscaling small inputs when helpful."""
    import cv2

    gray = image
    if getattr(image, "ndim", 0) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    long_edge = max(height, width)
    if long_edge < MIN_LONG_EDGE:
        scale = MIN_LONG_EDGE / float(long_edge)
        gray = cv2.resize(
            gray,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC,
        )
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.fastNlMeansDenoising(gray, h=7)
