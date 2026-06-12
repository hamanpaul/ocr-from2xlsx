from __future__ import annotations

from pathlib import Path


def test_spec_is_windowed_and_bundles_cv2() -> None:
    spec_text = (Path(__file__).resolve().parents[1] / "build" / "ocr-from2xlsx.spec").read_text(
        encoding="utf-8"
    )

    assert "console=False" in spec_text
    assert "console=True" not in spec_text
    assert "cv2" in spec_text  # opencv bundled so the shipped exe can use the webcam
