from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from ocr_from2xlsx.capture import measure_sharpness


def test_sharp_image_scores_higher_than_blurred() -> None:
    rng = np.random.default_rng(0)
    sharp = rng.integers(0, 256, size=(200, 200), dtype="uint8")
    blurred = cv2.GaussianBlur(sharp, (0, 0), sigmaX=4)

    assert measure_sharpness(sharp) > measure_sharpness(blurred)


def test_measure_accepts_color_or_gray() -> None:
    color = np.zeros((50, 50, 3), dtype="uint8")
    gray = np.zeros((50, 50), dtype="uint8")

    assert measure_sharpness(color) >= 0.0
    assert measure_sharpness(gray) >= 0.0
