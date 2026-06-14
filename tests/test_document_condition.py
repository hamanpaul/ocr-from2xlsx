from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from ocr_from2xlsx.document_condition import enhance


def test_enhance_returns_gray_uint8_same_or_larger() -> None:
    src = np.random.default_rng(0).integers(0, 256, size=(100, 150, 3), dtype=np.uint8)

    out = enhance(src)

    assert out.dtype == np.uint8
    assert out.ndim == 2
    assert out.shape[0] >= 100
    assert out.shape[1] >= 150
