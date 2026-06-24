from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx.app import ReviewApp
from ocr_from2xlsx.review_workflow import correction_mode_controls, scan_mode_controls


def _app_or_skip() -> ReviewApp:
    try:
        app = ReviewApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    app.withdraw()
    return app


def test_correction_mode_shows_only_correction_controls() -> None:
    app = _app_or_skip()
    try:
        app._set_review_mode("correction")
        for control in correction_mode_controls():
            if control == "progress":
                continue
            assert app._mode_buttons[control].winfo_manager(), f"{control} should be visible"
        for control in scan_mode_controls():
            assert not app._mode_buttons[control].winfo_manager(), f"{control} should be hidden"
    finally:
        app.destroy()


def test_scan_mode_shows_scan_controls() -> None:
    app = _app_or_skip()
    try:
        app._set_review_mode("scan")
        for control in scan_mode_controls():
            assert app._mode_buttons[control].winfo_manager(), f"{control} should be visible"
        assert not app._mode_buttons["confirm"].winfo_manager()
    finally:
        app.destroy()


def test_toggle_review_mode_flips_between_modes() -> None:
    app = _app_or_skip()
    try:
        app._set_review_mode("correction")
        app._toggle_review_mode()
        assert app._review_mode == "scan"
        app._toggle_review_mode()
        assert app._review_mode == "correction"
    finally:
        app.destroy()
