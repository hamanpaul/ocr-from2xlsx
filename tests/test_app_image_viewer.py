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


def test_frame_region_snaps_zoom_to_integer():
    # frame_region must store an integer zoom so it equals the integer render factor
    # (_redraw uses int(round(zoom))); a fractional zoom would mis-clamp the pan and
    # show a dark gap past the image edge.
    from PIL import Image

    root, viewer = _viewer()
    try:
        viewer._refresh_view_size = lambda: None  # keep our deterministic view size
        viewer.mode = "static"
        viewer._pil_image = Image.new("RGB", (10, 10))  # static path renders from the PIL image (#57)
        viewer._image_size = (10, 10)
        viewer._view_size = (40, 40)
        viewer.frame_region((0.0, 0.0, 0.7, 0.7))  # ratio 40/7 ≈ 5.71 -> floor 5
        assert viewer.zoom == float(int(viewer.zoom))
        assert viewer.zoom == 5.0
    finally:
        root.destroy()


def test_redraw_renders_bounded_display_image_at_max_zoom():
    # #57: the static path renders the visible window with a LANCZOS crop-resize, so the
    # rendered ImageTk is always ~pane-sized regardless of zoom (bounded memory), never the
    # full-resolution image scaled up. Guards against a render blow-up at high zoom.
    from PIL import Image

    root, viewer = _viewer()
    try:
        viewer._refresh_view_size = lambda: None  # deterministic sizes
        viewer.mode = "static"
        viewer._pil_image = Image.new("RGB", (3000, 4000))  # large source
        viewer._fit_scale = 0.1  # 3000 -> 300 fit-base width
        viewer._image_size = (300, 400)
        viewer._view_size = (300, 400)
        viewer.set_zoom(8.0)  # max zoom
        viewer.pan_to(100.0, 100.0)  # triggers _redraw
        assert viewer._display_image is not None
        assert viewer._display_image.width() <= 300 + 8
        assert viewer._display_image.height() <= 400 + 8
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
