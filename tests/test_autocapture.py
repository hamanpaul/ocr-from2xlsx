from __future__ import annotations

from ocr_from2xlsx.autocapture import AutoCaptureConfig


def test_config_defaults():
    cfg = AutoCaptureConfig()
    assert cfg.motion_thresh == 2.0
    assert cfg.stable_frames == 6
    assert cfg.newpage_thresh == 12.0
    assert cfg.clear_thresh == 18.0
    assert cfg.clear_frames == 4
    assert cfg.preview_min_sharpness == 60.0
    assert cfg.cooldown_frames == 8
    assert cfg.retry_limit == 3


def test_config_from_env_overrides_and_ignores_garbage(monkeypatch):
    monkeypatch.setenv("AUTOCAPTURE_MOTION_THRESH", "3.5")
    monkeypatch.setenv("AUTOCAPTURE_STABLE_FRAMES", "10")
    monkeypatch.setenv("AUTOCAPTURE_RETRY_LIMIT", "not-an-int")  # ignored → default
    cfg = AutoCaptureConfig.from_env()
    assert cfg.motion_thresh == 3.5
    assert cfg.stable_frames == 10
    assert cfg.retry_limit == 3
