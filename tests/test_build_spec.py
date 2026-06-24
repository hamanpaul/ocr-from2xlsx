from __future__ import annotations

from pathlib import Path


def test_spec_is_windowed_and_bundles_cv2() -> None:
    spec_path = Path(__file__).resolve().parents[1] / "build" / "ocr-from2xlsx.spec"
    spec_text = spec_path.read_text(encoding="utf-8")

    # ensure the helper is imported and called for opencv
    assert 'from PyInstaller.utils.hooks import collect_dynamic_libs' in spec_text
    assert 'collect_dynamic_libs("cv2")' in spec_text

    # ensure the collected binaries are assigned and passed into Analysis
    assert 'cv2_binaries' in spec_text
    assert 'binaries=cv2_binaries' in spec_text

    # ensure the exact hiddenimports list is present
    assert 'hiddenimports=["tkinter", "cv2"]' in spec_text

    # ensure windowed exe (console disabled) and no accidental console=True
    assert "console=False" in spec_text
    assert "console=True" not in spec_text


def test_spec_shows_boot_splash() -> None:
    spec_path = Path(__file__).resolve().parents[1] / "build" / "ocr-from2xlsx.spec"
    spec_text = spec_path.read_text(encoding="utf-8")

    # a native splash is configured from build/splash.png and wired into the EXE
    assert "Splash(" in spec_text
    assert "splash.png" in spec_text
    assert "splash.binaries" in spec_text

    splash_image = spec_path.parent / "splash.png"
    assert splash_image.is_file()
