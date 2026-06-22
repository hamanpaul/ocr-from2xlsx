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
