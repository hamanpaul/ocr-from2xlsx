from __future__ import annotations

from ocr_from2xlsx.autocapture import AutoCaptureConfig
from ocr_from2xlsx.autocapture import (
    CAPTURE,
    DISARMED,
    NONE,
    REARMED,
    STALLED,
    AutoCaptureDetector,
    FrameMetrics,
)


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


def _settled(sharpness: float = 100.0, change: float = 50.0) -> FrameMetrics:
    # still (motion 0), in focus, not rising (caller repeats same sharpness), new page
    return FrameMetrics(motion=0.0, change_from_ref=change, sharpness=sharpness)


def _feed(detector, metrics, times):
    actions = [detector.observe(metrics) for _ in range(times)]
    return actions


def test_captures_after_stable_in_focus_converged_new_frames():
    d = AutoCaptureDetector()  # stable_frames=6
    # First observe sets the sharpness baseline; convergence needs a prior frame.
    actions = _feed(d, _settled(), 7)
    assert actions.count(CAPTURE) == 1
    assert actions[-1] == CAPTURE  # 1 baseline + 6 qualifying


def test_does_not_capture_while_focus_is_still_rising():
    d = AutoCaptureDetector()
    actions = [d.observe(FrameMetrics(0.0, 50.0, s)) for s in (40, 60, 80, 100, 120, 140, 160)]
    # sharpness keeps rising > tol each frame → never "converged" → never captures
    assert CAPTURE not in actions


def test_does_not_capture_while_moving():
    d = AutoCaptureDetector()
    actions = _feed(d, FrameMetrics(motion=20.0, change_from_ref=50.0, sharpness=100.0), 8)
    assert CAPTURE not in actions


def test_mark_captured_disarms_then_rearms_on_scene_clear():
    d = AutoCaptureDetector()
    _feed(d, _settled(), 7)            # capture
    d.mark_captured()
    assert d.state == DISARMED
    # cooldown frames are ignored first
    cooldown = [d.observe(FrameMetrics(0.0, 0.0, 100.0)) for _ in range(d.config.cooldown_frames)]
    assert all(a == NONE for a in cooldown)
    # small change (form still there) → stays disarmed
    assert d.observe(FrameMetrics(0.0, 1.0, 100.0)) == NONE
    # big sustained change (form removed) → re-arm
    clears = [d.observe(FrameMetrics(0.0, 99.0, 30.0)) for _ in range(d.config.clear_frames)]
    assert clears[-1] == REARMED


def test_failed_capture_retries_then_stalls():
    d = AutoCaptureDetector()
    assert d.note_failed_capture() == NONE
    assert d.note_failed_capture() == NONE
    assert d.note_failed_capture() == STALLED  # retry_limit=3
