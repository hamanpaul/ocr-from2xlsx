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
