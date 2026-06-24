from __future__ import annotations

import numpy as np
import pytest

from ocr_from2xlsx.autocapture import (
    ARMED,
    CAPTURE,
    DISARMED,
    NEED_BASELINE,
    NONE,
    PAUSED,
    REARMED,
    STALLED,
    AutoCaptureConfig,
    AutoCaptureDetector,
    FrameMetrics,
    mean_abs_diff,
    mean_normalized_diff,
    to_metric_gray,
)


def test_config_defaults():
    cfg = AutoCaptureConfig()
    assert cfg.roi_fraction == 0.65
    assert cfg.motion_thresh == 2.0
    assert cfg.stable_frames == 6
    assert cfg.present_thresh == 25.0
    assert cfg.clear_thresh == 12.0
    assert cfg.clear_frames == 4
    assert cfg.preview_min_sharpness == 60.0
    assert cfg.settle_tol == 5.0
    assert cfg.cooldown_frames == 8
    assert cfg.retry_limit == 3
    assert cfg.baseline_stable_frames == 3


def test_config_from_env_overrides_and_ignores_garbage(monkeypatch):
    monkeypatch.setenv("AUTOCAPTURE_PRESENT_THRESH", "40")
    monkeypatch.setenv("AUTOCAPTURE_ROI_FRACTION", "0.5")
    monkeypatch.setenv("AUTOCAPTURE_RETRY_LIMIT", "not-an-int")  # ignored → default
    cfg = AutoCaptureConfig.from_env()
    assert cfg.present_thresh == 40.0
    assert cfg.roi_fraction == 0.5
    assert cfg.retry_limit == 3


def _present(sharpness=100.0, diff=80.0):
    # present (far from baseline), still, in focus
    return FrameMetrics(motion=0.0, diff_from_baseline=diff, sharpness=sharpness)


def _feed(d, metrics, times):
    return [d.observe(metrics) for _ in range(times)]


def test_no_capture_before_baseline_set():
    d = AutoCaptureDetector()
    assert d.state == NEED_BASELINE
    assert all(a == NONE for a in _feed(d, _present(), 10))


def test_captures_present_still_settled_after_baseline():
    d = AutoCaptureDetector()
    d.set_baseline()
    assert d.state == ARMED
    actions = _feed(d, _present(), 7)  # 1 baseline frame + 6 qualifying
    assert actions.count(CAPTURE) == 1
    assert actions[-1] == CAPTURE


def test_second_identical_template_form_is_captured():
    # Regression for the original Critical: two forms ~identical to EACH OTHER but both
    # far from the empty-desk baseline must both capture, separated by a clear-cycle.
    d = AutoCaptureDetector()
    d.set_baseline()
    assert _feed(d, _present(diff=80.0), 7).count(CAPTURE) == 1  # form A
    d.mark_captured()
    # cooldown
    _feed(d, FrameMetrics(0.0, 80.0, 100.0), d.config.cooldown_frames)
    # desk cleared (back near baseline) → re-arm
    clears = _feed(d, FrameMetrics(0.0, 2.0, 30.0), d.config.clear_frames)
    assert clears[-1] == REARMED
    # form B: nearly identical to A, but still far from EMPTY baseline → must capture
    actions = _feed(d, _present(diff=78.0), 7)
    assert CAPTURE in actions


def test_same_form_left_in_place_not_recaptured():
    d = AutoCaptureDetector()
    d.set_baseline()
    _feed(d, _present(), 7)
    d.mark_captured()
    _feed(d, FrameMetrics(0.0, 80.0, 100.0), d.config.cooldown_frames)
    # form stays (diff stays high, never clears) → never re-arms → no capture
    actions = _feed(d, _present(), 20)
    assert CAPTURE not in actions


def test_not_captured_while_moving_or_out_of_focus_or_unsettled():
    d = AutoCaptureDetector(); d.set_baseline()
    assert CAPTURE not in _feed(d, FrameMetrics(20.0, 80.0, 100.0), 8)      # moving
    d = AutoCaptureDetector(); d.set_baseline()
    assert CAPTURE not in _feed(d, FrameMetrics(0.0, 80.0, 30.0), 8)        # below preview_min_sharpness
    d = AutoCaptureDetector(); d.set_baseline()
    rising = [d.observe(FrameMetrics(0.0, 80.0, s)) for s in (60, 70, 80, 90, 100, 110, 120)]
    assert CAPTURE not in rising                                            # sharpness rising > settle_tol


def test_absent_form_does_not_capture():
    d = AutoCaptureDetector(); d.set_baseline()
    # near baseline (no form) but otherwise still/in-focus → not present → no capture
    assert CAPTURE not in _feed(d, FrameMetrics(0.0, 3.0, 100.0), 8)


def test_settle_is_two_sided_falling_sharpness_not_settled():
    d = AutoCaptureDetector(); d.set_baseline()
    falling = [d.observe(FrameMetrics(0.0, 80.0, s)) for s in (200, 190, 180, 170, 160, 150, 140)]
    assert CAPTURE not in falling


def test_repeated_failed_capture_pauses():
    d = AutoCaptureDetector(); d.set_baseline()
    assert d.note_failed_capture() == NONE
    assert d.note_failed_capture() == NONE
    assert d.note_failed_capture() == STALLED
    assert d.state == PAUSED
    # PAUSED: observe never captures until baseline re-set
    assert all(a == NONE for a in _feed(d, _present(), 10))
    d.set_baseline()
    assert d.state == ARMED


def test_to_metric_gray_central_roi_and_downscale():
    frame = np.zeros((480, 1280, 3), dtype="uint8")
    gray = to_metric_gray(frame, target_width=320, roi_fraction=0.5)
    assert gray.ndim == 2
    assert gray.shape[1] <= 320
    # central ROI used: only the centre region contributes
    f2 = np.zeros((100, 100), dtype="float64")
    f2[40:60, 40:60] = 255.0  # central block
    base = np.zeros((100, 100), dtype="float64")
    assert mean_abs_diff(to_metric_gray(f2, roi_fraction=0.5), to_metric_gray(base, roi_fraction=0.5)) > 0


def test_mean_abs_diff_values_and_guards():
    a = np.zeros((4, 4), dtype="float64")
    b = np.full((4, 4), 10.0)
    assert mean_abs_diff(a, b) == 10.0
    assert mean_abs_diff(a, None) == float("inf")
    assert mean_abs_diff(a, np.zeros((2, 2))) == float("inf")


def test_mean_normalized_diff_ignores_uniform_shift():
    a = np.array([[10.0, 20.0], [30.0, 40.0]])
    # uniform brightness shift → zero AC difference
    assert mean_normalized_diff(a, a + 50) == pytest.approx(0, abs=1e-9)
    # content change → non-zero
    b = np.array([[10.0, 20.0], [30.0, 90.0]])
    assert mean_normalized_diff(a, b) > 0
    # None guard
    assert mean_normalized_diff(None, a) == float("inf")
    assert mean_normalized_diff(a, None) == float("inf")
    # shape mismatch guard
    assert mean_normalized_diff(a, np.zeros((3, 3))) == float("inf")
