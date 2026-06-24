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


def test_frame_field_region_only_for_known_field():
    from ocr_from2xlsx.app import ReviewApp

    calls = []

    class _StubViewer:
        mode = "static"

        def frame_region(self, band):
            calls.append(band)

    app = ReviewApp.__new__(ReviewApp)
    app.preview = _StubViewer()

    app._frame_field_region("identity")
    assert len(calls) == 1
    app._frame_field_region("definitely_not_a_field")
    assert len(calls) == 1  # unknown region: no framing call


def test_confirm_form_field_focus_frames_region():
    root, _ = _viewer()
    try:
        from ocr_from2xlsx.form_layout import service_record_layout

        framed = []
        form = app_module.ConfirmForm(
            root,
            service_record_layout(),
            on_field_region=lambda record_path: framed.append(record_path),
        )
        form.set_flagged_fields({"name": "unconfirmed"})
        form.focus_first_flagged()
        assert framed == ["name"]
    finally:
        root.destroy()
