"""Tests for the appearance/theming core (`ocr_from2xlsx.theme`).

The palette/contrast/manager logic is Tk-free (fakes); `apply_theme` and
`load_icon` need a real Tk root and skip cleanly when no display is available.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from ocr_from2xlsx import theme
from ocr_from2xlsx.theme import DARK, LIGHT, contrast_ratio

REQUIRED_TOKENS = [
    "brand", "on_brand", "accent", "on_accent", "bg", "surface",
    "border", "text", "text_muted",
    "success_bg", "success_fg", "warning_bg", "warning_fg",
    "danger_bg", "danger_fg",
]


# --- palette / contrast (no Tk) --------------------------------------------

@pytest.mark.parametrize("pal", [LIGHT, DARK])
def test_palette_exposes_required_tokens(pal):
    for tok in REQUIRED_TOKENS:
        value = getattr(pal, tok)
        assert isinstance(value, str) and value.startswith("#")


@pytest.mark.parametrize("pal", [LIGHT, DARK])
def test_body_text_pairs_meet_aa(pal):
    assert contrast_ratio(pal.text, pal.surface) >= 4.5
    assert contrast_ratio(pal.text, pal.bg) >= 4.5
    assert contrast_ratio(pal.text_muted, pal.surface) >= 4.5
    assert contrast_ratio(pal.on_brand, pal.brand) >= 4.5
    assert contrast_ratio(pal.on_accent, pal.accent) >= 4.5


def test_type_and_spacing_scales():
    assert theme.FONT_BODY == 14
    assert theme.SPACE == 8


# --- apply_theme (real Tk) --------------------------------------------------

def _root_or_skip():
    try:
        r = tk.Tk()
        r.withdraw()
        return r
    except tk.TclError:
        pytest.skip("no display")


def test_apply_theme_sets_clam_and_named_styles():
    r = _root_or_skip()
    try:
        style = ttk.Style()
        theme.apply_theme(r, style, LIGHT)
        assert style.theme_use() == "clam"
        assert style.lookup("Primary.TButton", "background") == LIGHT.accent
        assert style.lookup("Toolbar.TFrame", "background") == LIGHT.brand
        assert style.lookup("Toolbar.TButton", "background") == LIGHT.brand
        assert style.lookup("Toolbar.TButton", "foreground") == LIGHT.on_brand
        assert style.lookup("Section.TLabelframe.Label", "foreground") == LIGHT.text
        assert str(theme.FONT_INPUT) in str(style.lookup("TEntry", "font"))
        theme.apply_theme(r, style, DARK)
        assert style.lookup("Primary.TButton", "background") == DARK.accent
    finally:
        r.destroy()


# --- ThemeManager (no Tk, via fakes) ---------------------------------------

class _FakeStyle:
    def __init__(self):
        self.calls = []

    def theme_use(self, *a):
        self.calls.append(("theme_use", a))
        return a[0] if a else "clam"

    def configure(self, *a, **k):
        self.calls.append(("configure", a, k))

    def map(self, *a, **k):
        self.calls.append(("map", a, k))

    def lookup(self, *a, **k):
        return ""


class _FakeWidget:
    def __init__(self):
        self.cfg = {}

    def configure(self, **k):
        self.cfg.update(k)


class _FakeRoot(_FakeWidget):
    pass


def test_manager_toggle_and_recolor_and_callback():
    seen = []
    mgr = theme.ThemeManager(_FakeRoot(), _FakeStyle(), mode="light",
                             on_change=seen.append)
    w = _FakeWidget()
    mgr.register(w, role="canvas")
    assert w.cfg["background"] == LIGHT.bg
    mgr.toggle()
    assert mgr.mode == "dark"
    assert w.cfg["background"] == DARK.bg
    assert seen == ["dark"]


def test_manager_defaults_invalid_mode_to_light():
    mgr = theme.ThemeManager(_FakeRoot(), _FakeStyle(), mode="bogus")
    assert mgr.mode == "light"


# --- load_icon (real Tk) ----------------------------------------------------

def test_load_icon_missing_returns_none():
    r = _root_or_skip()
    try:
        assert theme.load_icon("does-not-exist-xyz", 24) is None
    finally:
        r.destroy()


def test_load_icon_returns_fresh_photoimage_and_caches_pil():
    r = _root_or_skip()
    try:
        img1 = theme.load_icon("confirm", 24)
        assert img1 is not None
        # The interpreter-independent PIL image is cached; the PhotoImage is created
        # fresh each call (a PhotoImage is bound to its root, so it must not be reused
        # across roots — that would raise TclError with a recycled root id).
        assert ("confirm", 24) in theme._PIL_CACHE
        img2 = theme.load_icon("confirm", 24)
        assert img2 is not None
    finally:
        theme._PIL_CACHE.clear()
        r.destroy()
