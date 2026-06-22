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
