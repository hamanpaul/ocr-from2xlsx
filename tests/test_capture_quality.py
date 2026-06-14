from __future__ import annotations

from ocr_from2xlsx.capture import DEFAULT_MIN_SHARPNESS, passes_sharpness_gate


def test_passes_sharpness_gate_boundary() -> None:
    assert passes_sharpness_gate(187.6, min_sharpness=100.0) is True
    assert passes_sharpness_gate(18.5, min_sharpness=100.0) is False
    assert passes_sharpness_gate(100.0, min_sharpness=100.0) is True


def test_default_min_sharpness_is_reasonable() -> None:
    assert 50.0 <= DEFAULT_MIN_SHARPNESS <= 150.0
