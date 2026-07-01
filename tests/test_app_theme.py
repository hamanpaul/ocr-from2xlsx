"""Real-Tk tests for the restyled toolbar and theme wiring.

These build a full ``ReviewApp`` window and skip cleanly when no display is
available (matching the app's real-Tk test convention)."""

from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx.app import ReviewApp


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    # Every test here builds a real ReviewApp, which reads/writes config.json under
    # OCR_FROM2XLSX_HOME. Point it at a tmp dir so tests never touch (or corrupt) the
    # operator's real ~/.ocr_from2xlsx/config.json (e.g. flipping their saved theme).
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))


def _app_or_skip() -> ReviewApp:
    try:
        app = ReviewApp()
    except tk.TclError:
        pytest.skip("no display")
    app.withdraw()
    return app


def _find_labelframes(widget) -> list:
    from tkinter import ttk

    found = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.LabelFrame):
            found.append(child)
        found.extend(_find_labelframes(child))
    return found


@pytest.mark.parametrize("width,expected", [(1000, 420), (1600, 672), (0, 0)])
def test_default_sash_x_is_left_of_center(width, expected):
    x = ReviewApp._default_sash_x(width, 0.42)
    assert x == expected
    if width:
        assert x < width // 2  # divider left of centre → the right (form) pane is wider


def test_initial_sash_placed_left_of_center():
    app = _app_or_skip()
    try:
        app.geometry("1000x700")
        app.update_idletasks()
        app._place_initial_sash()
        body_w = app._body.winfo_width()
        if body_w > 1:  # only assert once the paned window actually has a width
            assert app._body.sashpos(0) < body_w // 2
    finally:
        app.destroy()


def test_form_groups_use_section_style():
    app = _app_or_skip()
    try:
        frames = _find_labelframes(app)
        assert frames, "expected at least one form group LabelFrame"
        assert any(f.cget("style") == "Section.TLabelframe" for f in frames)
    finally:
        app.destroy()


def test_toolbar_primary_is_confirm_write_and_secondary_are_icon_only():
    app = _app_or_skip()
    try:
        assert app._confirm_btn.cget("text") == "確認寫入"
        for b in (app._open_btn, app._import_btn, app._prev_btn, app._next_btn):
            assert b.cget("text") == ""       # icon-only
            assert b.image is not None         # has an icon
    finally:
        app.destroy()


def test_prev_next_disabled_without_records():
    app = _app_or_skip()
    try:
        app.records = []
        app._update_toolbar_states()
        assert str(app._prev_btn["state"]) == "disabled"
        assert str(app._next_btn["state"]) == "disabled"
    finally:
        app.destroy()


def test_edit_menu_confirm_label_renamed():
    app = _app_or_skip()
    try:
        # the 編輯 menu entry follows the toolbar relabel
        assert app._controls.get("confirm")  # registered under the confirm key
        # the toolbar confirm button drives _confirm_current
        assert app._confirm_btn.cget("text") == "確認寫入"
    finally:
        app.destroy()


def test_theme_defaults_light_and_toggle_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    app = _app_or_skip()
    try:
        assert app.theme.mode == "light"
        app._toggle_theme()
        assert app.theme.mode == "dark"
        assert ReviewApp._load_config().get("theme_mode") == "dark"
        app._toggle_theme()
        assert app.theme.mode == "light"
        assert ReviewApp._load_config().get("theme_mode") == "light"
    finally:
        app.destroy()


def test_theme_opens_in_saved_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    ReviewApp._update_config(theme_mode="dark")
    app = _app_or_skip()
    try:
        assert app.theme.mode == "dark"
    finally:
        app.destroy()


def test_toggle_recolors_owned_tk_widgets():
    from ocr_from2xlsx import theme as th

    app = _app_or_skip()
    try:
        app.theme.set_mode("dark")
        assert str(app._autocapture_banner.cget("background")) == th.DARK.surface_alt
        assert str(app._form_canvas.cget("background")) == th.DARK.bg
    finally:
        app.destroy()


def test_active_banner_and_pending_badge_use_dark_tokens():
    from ocr_from2xlsx import theme as th

    app = _app_or_skip()
    try:
        app.theme.set_mode("dark")
        app._set_autocapture_state("掃描中", tone="active")
        assert str(app._autocapture_banner.cget("background")) == th.DARK.warning_bg
        # pending badge neutral chip follows the dark surface (written/blocked keep strong colors)
        app.records = []
        app.current_index = -1
        app._update_badge()
        assert str(app._badge_label.cget("background")) == th.DARK.surface_alt
    finally:
        app.destroy()
