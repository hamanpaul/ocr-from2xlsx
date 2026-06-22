# tests/test_app_continuous_capture.py
from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx.app import ReviewApp


def test_shutter_sound_path_points_at_bundled_asset():
    path = ReviewApp._shutter_sound_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "shutter.wav"


def test_play_shutter_never_raises_without_asset(monkeypatch):
    monkeypatch.setattr(ReviewApp, "_shutter_sound_path", staticmethod(lambda: None))
    app = ReviewApp.__new__(ReviewApp)
    # Must be a silent no-op when there is no asset / no audio backend.
    ReviewApp._play_shutter(app)


# ---------------------------------------------------------------------------
# Task 6: Session state, buttons, start/cancel/undo
# ---------------------------------------------------------------------------
from types import SimpleNamespace


def _bare_app():
    app = ReviewApp.__new__(ReviewApp)
    app.editing = False
    app._camera_index = 4
    app._camera_capture = None
    app._camera_after_id = None
    app._preview_rotation = 0
    app._status_log = []
    app._status_var = None
    app._status_log_path = None
    app._autocapture_active = False
    app._autocapture_detector = None
    app._autocapture_output_dir = None
    app._autocapture_prev_gray = None
    app._autocapture_ref_gray = None
    app._autocapture_stills = []
    return app


def test_start_continuous_capture_opens_session(monkeypatch, tmp_path):
    app = _bare_app()
    monkeypatch.setattr("ocr_from2xlsx.app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr("ocr_from2xlsx.capture.require_camera_support", lambda: None)
    monkeypatch.setattr(app, "_has_live_camera_preview", lambda: True)  # don't start a real camera
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is True
    assert app._autocapture_output_dir == tmp_path
    assert app._autocapture_detector is not None


def test_start_blocked_when_editing(monkeypatch):
    app = _bare_app()
    app.editing = True
    errors = []
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showerror", lambda t, m: errors.append((t, m)))
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is False
    assert errors and errors[0][0] == "尚未保存"


def test_start_warns_without_selected_camera(monkeypatch):
    app = _bare_app()
    app._camera_index = None
    warnings = []
    monkeypatch.setattr("ocr_from2xlsx.capture.require_camera_support", lambda: None)
    monkeypatch.setattr(app, "_clear_inactive_camera_selection", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showwarning", lambda t, m: warnings.append((t, m)))
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is False
    assert warnings == [("連續拍照", "請先選擇可用的攝影機。")]


def test_cancel_continuous_capture(monkeypatch):
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_stills = [Path("a.png")]
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    ReviewApp._cancel_continuous_capture(app)
    assert app._autocapture_active is False


def test_undo_last_capture_deletes_and_decrements(tmp_path):
    app = _bare_app()
    app._autocapture_active = True
    f1 = tmp_path / "scan-capture.png"
    f2 = tmp_path / "scan-capture-2.png"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    app._autocapture_stills = [f1, f2]
    ReviewApp._undo_last_continuous_capture(app)
    assert app._autocapture_stills == [f1]
    assert not f2.exists()
    assert f1.exists()
