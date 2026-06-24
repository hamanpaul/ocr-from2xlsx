from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AutoCaptureConfig:
    """Auto-capture thresholds. Defaults are a starting point; calibrate on-device
    via the AUTOCAPTURE_* env vars (metrics depend on camera/lighting/background)."""

    roi_fraction: float = 0.65          # central fraction of the frame used for detection
    motion_thresh: float = 2.0          # mean abs gray diff vs previous frame to count as "still"
    stable_frames: int = 6              # consecutive qualifying frames before capturing
    present_thresh: float = 25.0        # diff vs empty-desk baseline to count as "form present"
    clear_thresh: float = 12.0          # diff vs baseline to count as "desk cleared" (< present_thresh)
    clear_frames: int = 4               # consecutive cleared frames before re-arming
    preview_min_sharpness: float = 60.0  # preview focus pre-gate (separate from DEFAULT_MIN_SHARPNESS)
    settle_tol: float = 5.0             # abs frame-to-frame sharpness change <= this == focus settled
    cooldown_frames: int = 8            # frames to ignore right after a capture / failed capture
    retry_limit: int = 3                # consecutive blurry/failed captures before PAUSED

    @classmethod
    def from_env(cls) -> "AutoCaptureConfig":
        return cls(
            roi_fraction=_env_float("AUTOCAPTURE_ROI_FRACTION", cls.roi_fraction),
            motion_thresh=_env_float("AUTOCAPTURE_MOTION_THRESH", cls.motion_thresh),
            stable_frames=_env_int("AUTOCAPTURE_STABLE_FRAMES", cls.stable_frames),
            present_thresh=_env_float("AUTOCAPTURE_PRESENT_THRESH", cls.present_thresh),
            clear_thresh=_env_float("AUTOCAPTURE_CLEAR_THRESH", cls.clear_thresh),
            clear_frames=_env_int("AUTOCAPTURE_CLEAR_FRAMES", cls.clear_frames),
            preview_min_sharpness=_env_float(
                "AUTOCAPTURE_PREVIEW_MIN_SHARPNESS", cls.preview_min_sharpness
            ),
            settle_tol=_env_float("AUTOCAPTURE_SETTLE_TOL", cls.settle_tol),
            cooldown_frames=_env_int("AUTOCAPTURE_COOLDOWN_FRAMES", cls.cooldown_frames),
            retry_limit=_env_int("AUTOCAPTURE_RETRY_LIMIT", cls.retry_limit),
        )


NEED_BASELINE = "need_baseline"
ARMED = "armed"
DISARMED = "disarmed"
PAUSED = "paused"

NONE = "none"
CAPTURE = "capture"
REARMED = "rearmed"
STALLED = "stalled"


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    motion: float              # mean abs gray diff vs the previous preview frame
    diff_from_baseline: float  # mean abs gray diff vs the empty-desk baseline (inf when none)
    sharpness: float           # variance-of-Laplacian of the preview frame


class AutoCaptureDetector:
    """Hands-free auto-capture state machine keyed on the empty-desk baseline. Fed scalar
    FrameMetrics per preview frame; returns an action. The app sets the baseline, performs the
    real capture on CAPTURE, and reports the outcome via mark_captured()/note_failed_capture().
    No OpenCV here."""

    def __init__(self, config: AutoCaptureConfig | None = None) -> None:
        self.config = config or AutoCaptureConfig()
        self._state = NEED_BASELINE
        self._stable_count = 0
        self._clear_count = 0
        self._cooldown = 0
        self._failed = 0
        self._last_sharpness: float | None = None

    @property
    def state(self) -> str:
        return self._state

    def set_baseline(self) -> None:
        """App reports the empty-desk baseline is established → start detecting (also
        resumes from PAUSED)."""
        self._state = ARMED
        self._stable_count = 0
        self._clear_count = 0
        self._cooldown = 0
        self._failed = 0
        self._last_sharpness = None

    def observe(self, metrics: FrameMetrics) -> str:
        cfg = self.config
        if self._state in (NEED_BASELINE, PAUSED):
            return NONE
        if self._cooldown > 0:
            self._cooldown -= 1
            self._last_sharpness = metrics.sharpness
            return NONE

        if self._state == DISARMED:
            if metrics.diff_from_baseline <= cfg.clear_thresh:
                self._clear_count += 1
            else:
                self._clear_count = 0
            self._last_sharpness = metrics.sharpness
            if self._clear_count >= cfg.clear_frames:
                self._state = ARMED
                self._stable_count = 0
                self._clear_count = 0
                return REARMED
            return NONE

        # ARMED: wait for a present (vs baseline), stationary, in-focus, settled frame.
        present = metrics.diff_from_baseline >= cfg.present_thresh
        stationary = metrics.motion < cfg.motion_thresh
        in_focus = metrics.sharpness >= cfg.preview_min_sharpness
        settled = (
            self._last_sharpness is not None
            and abs(metrics.sharpness - self._last_sharpness) <= cfg.settle_tol
        )
        self._last_sharpness = metrics.sharpness

        if present and stationary and in_focus and settled:
            self._stable_count += 1
        else:
            self._stable_count = 0

        if self._stable_count >= cfg.stable_frames:
            self._stable_count = 0
            return CAPTURE
        return NONE

    def mark_captured(self) -> None:
        """App reports a successful capture → disarm until the desk clears."""
        self._state = DISARMED
        self._stable_count = 0
        self._clear_count = 0
        self._cooldown = self.config.cooldown_frames
        self._failed = 0

    def note_failed_capture(self) -> str:
        """App reports a blurry/failed capture. Returns STALLED and pauses when retries
        are exhausted (resume via set_baseline)."""
        self._failed += 1
        self._stable_count = 0
        self._cooldown = self.config.cooldown_frames
        if self._failed >= self.config.retry_limit:
            self._failed = 0
            self._state = PAUSED
            return STALLED
        return NONE


def to_metric_gray(frame: object, *, target_width: int = 320, roi_fraction: float = 1.0):
    """Central-ROI + downscale + grayscale a BGR/gray frame to a small float array for cheap
    diffing. Uses cv2 for color conversion when available; falls back to a NumPy channel mean."""
    import numpy as np

    arr = np.asarray(frame)
    if arr.ndim == 3:
        try:
            import cv2

            arr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        except Exception:
            arr = arr.mean(axis=2)
    arr = np.asarray(arr, dtype="float64")
    if arr.ndim >= 2 and 0.0 < roi_fraction < 1.0:
        h, w = arr.shape[:2]
        ch, cw = max(1, int(h * roi_fraction)), max(1, int(w * roi_fraction))
        y0, x0 = (h - ch) // 2, (w - cw) // 2
        arr = arr[y0:y0 + ch, x0:x0 + cw]
    width = arr.shape[1] if arr.ndim >= 2 else 0
    if width > target_width:
        step = max(1, width // target_width)
        arr = arr[::step, ::step]
    return arr


def mean_abs_diff(a: object, b: object) -> float:
    """Mean absolute difference of two equal-shaped arrays. Returns +inf when either
    is None (no reference yet) or shapes differ (treated as 'maximally different')."""
    import numpy as np

    if a is None or b is None:
        return float("inf")
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    if a.shape != b.shape:
        return float("inf")
    return float(np.abs(a - b).mean())
