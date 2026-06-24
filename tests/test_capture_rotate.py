from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from ocr_from2xlsx.capture import rotate_frame


def test_rotate_frame_0_is_unchanged() -> None:
    frame = np.zeros((100, 50, 3), dtype="uint8")
    assert rotate_frame(frame, 0).shape == (100, 50, 3)


def test_rotate_frame_90_swaps_dimensions() -> None:
    frame = np.zeros((100, 50, 3), dtype="uint8")
    assert rotate_frame(frame, 90).shape[:2] == (50, 100)


def test_rotate_frame_180_keeps_dimensions() -> None:
    frame = np.zeros((100, 50, 3), dtype="uint8")
    assert rotate_frame(frame, 180).shape[:2] == (100, 50)


def test_rotate_frame_270_swaps_dimensions() -> None:
    frame = np.zeros((100, 50, 3), dtype="uint8")
    assert rotate_frame(frame, 270).shape[:2] == (50, 100)


def test_rotate_frame_normalizes_degrees() -> None:
    frame = np.zeros((100, 50, 3), dtype="uint8")
    # 450 % 360 == 90
    assert rotate_frame(frame, 450).shape[:2] == (50, 100)
