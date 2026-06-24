from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx import app as app_module


def _viewer():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    root.withdraw()
    return root, app_module.ImageViewer(root)


def test_zoom_is_clamped_and_remembered():
    root, viewer = _viewer()
    try:
        viewer.set_zoom(3.0)
        assert viewer.zoom == 3.0
        viewer.set_zoom(100.0)
        assert viewer.zoom == 8.0
        viewer.set_zoom(0.1)
        assert viewer.zoom == 1.0
    finally:
        root.destroy()


def test_show_placeholder_sets_text_mode():
    root, viewer = _viewer()
    try:
        viewer.show_placeholder("預覽區")
        assert viewer.mode == "placeholder"
    finally:
        root.destroy()


def test_pan_is_clamped_within_bounds():
    root, viewer = _viewer()
    try:
        viewer._image_size = (1000, 1000)
        viewer._view_size = (400, 400)
        viewer.set_zoom(1.0)
        viewer.pan_to(-50.0, 5000.0)
        assert viewer.origin[0] == 0.0
        assert viewer.origin[1] == 600.0
    finally:
        root.destroy()
