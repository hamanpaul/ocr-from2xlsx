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
    via the AUTOCAPTURE_* env vars (preview metrics depend on camera/lighting)."""

    motion_thresh: float = 2.0          # mean abs gray diff vs previous frame to count as "still"
    stable_frames: int = 6              # consecutive qualifying frames before capturing
    newpage_thresh: float = 12.0        # change vs last captured to count as a new page
    clear_thresh: float = 18.0          # change vs last captured to count as "scene cleared"
    clear_frames: int = 4               # consecutive cleared frames before re-arming
    preview_min_sharpness: float = 60.0  # preview-side focus pre-gate (separate from DEFAULT_MIN_SHARPNESS)
    sharpness_rise_tol: float = 5.0     # frame-to-frame sharpness rise <= this == focus converged
    cooldown_frames: int = 8            # frames to ignore right after a capture / failed capture
    retry_limit: int = 3                # consecutive blurry captures before STALLED

    @classmethod
    def from_env(cls) -> "AutoCaptureConfig":
        return cls(
            motion_thresh=_env_float("AUTOCAPTURE_MOTION_THRESH", cls.motion_thresh),
            stable_frames=_env_int("AUTOCAPTURE_STABLE_FRAMES", cls.stable_frames),
            newpage_thresh=_env_float("AUTOCAPTURE_NEWPAGE_THRESH", cls.newpage_thresh),
            clear_thresh=_env_float("AUTOCAPTURE_CLEAR_THRESH", cls.clear_thresh),
            clear_frames=_env_int("AUTOCAPTURE_CLEAR_FRAMES", cls.clear_frames),
            preview_min_sharpness=_env_float(
                "AUTOCAPTURE_PREVIEW_MIN_SHARPNESS", cls.preview_min_sharpness
            ),
            sharpness_rise_tol=_env_float(
                "AUTOCAPTURE_SHARPNESS_RISE_TOL", cls.sharpness_rise_tol
            ),
            cooldown_frames=_env_int("AUTOCAPTURE_COOLDOWN_FRAMES", cls.cooldown_frames),
            retry_limit=_env_int("AUTOCAPTURE_RETRY_LIMIT", cls.retry_limit),
        )


ARMED = "armed"
DISARMED = "disarmed"

NONE = "none"
CAPTURE = "capture"
REARMED = "rearmed"
STALLED = "stalled"


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    motion: float            # mean abs gray diff vs the previous preview frame
    change_from_ref: float   # mean abs gray diff vs the last captured frame (inf when no ref)
    sharpness: float         # variance-of-Laplacian of the preview frame


class AutoCaptureDetector:
    """Hands-free auto-capture state machine. Fed scalar FrameMetrics per preview
    frame; returns an action string. The app performs the real capture on CAPTURE and
    reports the outcome via mark_captured() / note_failed_capture(). No OpenCV here."""

    def __init__(self, config: AutoCaptureConfig | None = None) -> None:
        self.config = config or AutoCaptureConfig()
        self._state = ARMED
        self._stable_count = 0
        self._clear_count = 0
        self._cooldown = 0
        self._failed = 0
        self._last_sharpness: float | None = None
        self._has_ref = False  # no capture yet → first page is always "new"

    @property
    def state(self) -> str:
        return self._state

    def observe(self, metrics: FrameMetrics) -> str:
        cfg = self.config
        if self._cooldown > 0:
            self._cooldown -= 1
            self._last_sharpness = metrics.sharpness
            return NONE

        if self._state == DISARMED:
            if metrics.change_from_ref >= cfg.clear_thresh:
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

        # ARMED: wait for a stationary, in-focus, converged, new page.
        stationary = metrics.motion < cfg.motion_thresh
        in_focus = metrics.sharpness >= cfg.preview_min_sharpness
        converged = (
            self._last_sharpness is not None
            and (metrics.sharpness - self._last_sharpness) <= cfg.sharpness_rise_tol
        )
        is_new = (not self._has_ref) or metrics.change_from_ref >= cfg.newpage_thresh
        self._last_sharpness = metrics.sharpness

        if stationary and in_focus and converged and is_new:
            self._stable_count += 1
        else:
            self._stable_count = 0

        if self._stable_count >= cfg.stable_frames:
            self._stable_count = 0
            return CAPTURE
        return NONE

    def mark_captured(self) -> None:
        """App reports a successful capture → disarm until the scene clears."""
        self._has_ref = True
        self._state = DISARMED
        self._stable_count = 0
        self._clear_count = 0
        self._cooldown = self.config.cooldown_frames
        self._failed = 0

    def note_failed_capture(self) -> str:
        """App reports a blurry/failed capture. Returns STALLED when retries exhausted."""
        self._failed += 1
        self._stable_count = 0
        self._cooldown = self.config.cooldown_frames
        if self._failed >= self.config.retry_limit:
            self._failed = 0
            return STALLED
        return NONE


def to_metric_gray(frame: object, *, target_width: int = 320):
    """Downscale + grayscale a BGR/gray frame to a small float array for cheap diffing.
    Uses cv2 for color conversion when available; falls back to a NumPy channel mean."""
    import numpy as np

    arr = np.asarray(frame)
    if arr.ndim == 3:
        try:
            import cv2

            arr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        except Exception:
            arr = arr.mean(axis=2)
    arr = np.asarray(arr, dtype="float64")
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
