"""Config persistence must be read-modify-write so `theme_mode` and
`preview_rotation` coexist instead of clobbering each other."""

from __future__ import annotations

from ocr_from2xlsx.app import ReviewApp


def test_config_merge_preserves_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    ReviewApp._update_config(preview_rotation=90)
    ReviewApp._update_config(theme_mode="dark")
    data = ReviewApp._load_config()
    assert data["preview_rotation"] == 90
    assert data["theme_mode"] == "dark"


def test_load_config_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    assert ReviewApp._load_config() == {}


def test_load_theme_mode_defaults_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    assert ReviewApp._load_theme_mode() == "light"
    ReviewApp._update_config(theme_mode="dark")
    assert ReviewApp._load_theme_mode() == "dark"
    ReviewApp._update_config(theme_mode="bogus")
    assert ReviewApp._load_theme_mode() == "light"


def test_preview_rotation_survives_theme_write(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    ReviewApp._update_config(preview_rotation=180)
    ReviewApp._update_config(theme_mode="dark")
    assert ReviewApp._load_preview_rotation() == 180


def test_corrupt_nondict_config_does_not_crash_persistence(tmp_path, monkeypatch):
    # A hand-edited / corrupted config.json holding a *non-dict* JSON value (list, string,
    # number) must not crash config persistence: _load_config normalises to {}, and the
    # read-modify-write path (_update_config) and _load_theme_mode survive without an
    # AttributeError from calling .update()/.get() on a non-dict.
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    (tmp_path / "config.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert ReviewApp._load_config() == {}
    assert ReviewApp._load_theme_mode() == "light"
    ReviewApp._update_config(theme_mode="dark")  # must not raise
    assert ReviewApp._load_theme_mode() == "dark"
