# Continuous hands-free webcam auto-capture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hands-free "連續拍照" session to the desktop app that auto-detects each form placed under the webcam, captures it (focus-confirmed) without a button press, accumulates a stack, and on completion batch-recognizes all stills into the existing per-record review.

**Architecture:** One new pure module `autocapture.py` (a scalar-fed state machine + cv2-guarded frame-metric helpers) drives the existing live-preview loop. On a CAPTURE action the app reuses the proven `capture_still` path (reopen + autofocus warm-up + sharpness gate) so focus is confirmed before the saved shot; re-arming requires the scene to clear (lift-then-place). Completion reuses `prepare_records_from_images` → existing review. Everything is testable with no camera, no display, and (for the state machine) no OpenCV.

**Tech Stack:** Python 3.12, Tkinter, OpenCV (`cv2`, optional/guarded), NumPy, pytest. Repo conventions: pure decision logic split from cv2 wrappers; app-level tests build `ReviewApp.__new__(ReviewApp)` and monkeypatch `capture_still` / `cv2` / `filedialog`.

---

## File Structure

- **Create** `src/ocr_from2xlsx/autocapture.py` — pure `AutoCaptureDetector` state machine, `AutoCaptureConfig` (defaults + `AUTOCAPTURE_*` env overrides), `FrameMetrics`, action constants, and cv2-guarded frame-metric helpers (`to_metric_gray`, `mean_abs_diff`). Single responsibility: decide when to capture / re-arm from per-frame scalars.
- **Create** `tests/test_autocapture.py` — model-free, cv2-free unit tests for the detector, config, and metric helpers.
- **Create** `build/make_shutter_wav.py` — deterministic stdlib synth that writes the shutter asset (run once, output committed).
- **Create** `src/ocr_from2xlsx/assets/shutter.wav` — bundled shutter ("咔嚓") sound (generated, committed).
- **Modify** `src/ocr_from2xlsx/scan.py` — add optional `on_progress(done, total, name)` to `prepare_records_from_images` (mirrors `prepare_records_from_folder`).
- **Modify** `src/ocr_from2xlsx/app.py` — session state + "連續拍照"/"完成辨識"/"取消連拍"/"復原上一張" buttons; `_start/_finish/_cancel/_undo_continuous_capture`, `_observe_autocapture_frame`, `_perform_autocapture`, `_play_shutter`, `_shutter_sound_path`, `_flash_preview`; one hook line in `_poll_camera_frame`.
- **Create** `tests/test_app_continuous_capture.py` — app-level session tests with injected fakes.
- **Modify** `build/ocr-from2xlsx.spec` — add the shutter wav to PyInstaller `datas`.
- **Modify** `pyproject.toml` — add `[tool.setuptools.package-data]` for `assets/*.wav`.
- **Modify** `README.md`, `CHANGELOG.md` — document the feature.

---

## Task 1: AutoCaptureConfig (defaults + env overrides)

**Files:**
- Create: `src/ocr_from2xlsx/autocapture.py`
- Test: `tests/test_autocapture.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_autocapture.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_autocapture.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_from2xlsx.autocapture'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ocr_from2xlsx/autocapture.py
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
```

> Note: `AutoCaptureConfig` is a non-slots frozen dataclass on purpose — `from_env` reads each default via `cls.<field>`, which only works when field defaults exist as class attributes (slots removes them).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_autocapture.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/autocapture.py tests/test_autocapture.py
git commit -m "feat: add AutoCaptureConfig with env-overridable thresholds"
```

---

## Task 2: AutoCaptureDetector state machine

**Files:**
- Modify: `src/ocr_from2xlsx/autocapture.py`
- Test: `tests/test_autocapture.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_autocapture.py
from ocr_from2xlsx.autocapture import (
    CAPTURE,
    DISARMED,
    NONE,
    REARMED,
    STALLED,
    AutoCaptureDetector,
    FrameMetrics,
)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_autocapture.py -q`
Expected: FAIL with `ImportError: cannot import name 'AutoCaptureDetector'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/ocr_from2xlsx/autocapture.py

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_autocapture.py -q`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/autocapture.py tests/test_autocapture.py
git commit -m "feat: add AutoCaptureDetector state machine (arm/capture/re-arm/retry)"
```

---

## Task 3: Frame-metric helpers (cv2-guarded, NumPy-testable)

**Files:**
- Modify: `src/ocr_from2xlsx/autocapture.py`
- Test: `tests/test_autocapture.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_autocapture.py
import numpy as np

from ocr_from2xlsx.autocapture import mean_abs_diff, to_metric_gray


def test_to_metric_gray_downscales_wide_frames():
    frame = np.zeros((480, 1280, 3), dtype="uint8")
    gray = to_metric_gray(frame, target_width=320)
    assert gray.ndim == 2
    assert gray.shape[1] <= 320


def test_mean_abs_diff_values_and_guards():
    a = np.zeros((4, 4), dtype="float64")
    b = np.full((4, 4), 10.0)
    assert mean_abs_diff(a, b) == 10.0
    assert mean_abs_diff(a, a) == 0.0
    assert mean_abs_diff(a, None) == float("inf")        # no reference yet
    assert mean_abs_diff(a, np.zeros((2, 2))) == float("inf")  # shape mismatch
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_autocapture.py -q`
Expected: FAIL with `ImportError: cannot import name 'to_metric_gray'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/ocr_from2xlsx/autocapture.py


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_autocapture.py -q`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/autocapture.py tests/test_autocapture.py
git commit -m "feat: add cv2-guarded frame-metric helpers for auto-capture"
```

---

## Task 4: `prepare_records_from_images` progress callback

**Files:**
- Modify: `src/ocr_from2xlsx/scan.py:76-134`
- Test: `tests/test_scan_folder.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_scan_folder.py
def test_prepare_records_from_images_reports_progress(tmp_path, monkeypatch):
    from ocr_from2xlsx.domain import SourceInfo

    class _Backend:
        def extract(self, prepared):
            return {"ocr": {"backend": "fake", "raw_text": "", "warnings": []}}

    # avoid PNG preview conversion: pre-create .png inputs
    images = []
    for name in ("p1.png", "p2.png"):
        path = tmp_path / name
        path.write_bytes(b"\x89PNG\r\n")
        images.append(path)

    monkeypatch.setattr(
        scan, "normalize_raw_record", lambda raw: SimpleNamespace(
            record_id=raw.get("record_id"), name="", ocr=SimpleNamespace(warnings=[]),
        )
    )

    progress: list[tuple[int, int, str]] = []
    template = SimpleNamespace(template_id="service_record.v1")
    scan.prepare_records_from_images(
        images, tmp_path / "out", template, backend=_Backend(),
        on_progress=lambda done, total, name: progress.append((done, total, name)),
    )
    assert progress == [(1, 2, "p1.png"), (2, 2, "p2.png")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scan_folder.py::test_prepare_records_from_images_reports_progress -q`
Expected: FAIL with `TypeError: prepare_records_from_images() got an unexpected keyword argument 'on_progress'`

- [ ] **Step 3: Write minimal implementation**

In `src/ocr_from2xlsx/scan.py`, change the signature and loop of `prepare_records_from_images`:

```python
def prepare_records_from_images(
    image_paths: list[Path | str],
    output_dir: Path | str,
    template: FormTemplate,
    backend: OcrBackend,
    created_at: str | None = None,
    on_progress: "Callable[[int, int, str], None] | None" = None,
) -> Batch:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    records = []

    paths = [Path(path) for path in image_paths]
    total = len(paths)
    for sequence, image_path in enumerate(paths, start=1):
        if on_progress is not None:
            on_progress(sequence, total, image_path.name)
        local_image = _copy_image_to_output(image_path, output_dir)
        # ... rest of the existing loop body unchanged ...
```

Also add `Callable` to the imports at the top of `scan.py`:

```python
from typing import Callable
```

- [ ] **Step 4: Run the test and the full scan suite to verify pass + no regressions**

Run: `python -m pytest tests/test_scan_folder.py tests/test_cli_scan.py -q`
Expected: PASS (existing tests still green; new test passes)

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/scan.py tests/test_scan_folder.py
git commit -m "feat: add optional on_progress to prepare_records_from_images"
```

---

## Task 5: Shutter sound asset + `_play_shutter`

**Files:**
- Create: `build/make_shutter_wav.py`
- Create: `src/ocr_from2xlsx/assets/shutter.wav` (generated)
- Modify: `src/ocr_from2xlsx/app.py` (add `_play_shutter`, `_shutter_sound_path`)
- Modify: `pyproject.toml` (package-data)
- Modify: `build/ocr-from2xlsx.spec` (PyInstaller datas)
- Test: `tests/test_app_continuous_capture.py`

- [ ] **Step 1: Create the asset generator**

```python
# build/make_shutter_wav.py
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parents[1] / "src" / "ocr_from2xlsx" / "assets" / "shutter.wav"


def _click(samples: list[float], start_s: float, dur_s: float, amp: float, seed: int) -> None:
    rng = random.Random(seed)  # seeded → reproducible committed asset
    start = int(start_s * RATE)
    n = int(dur_s * RATE)
    for i in range(n):
        idx = start + i
        if idx >= len(samples):
            break
        env = math.exp(-i / (n * 0.25))  # fast mechanical decay
        noise = rng.random() * 2.0 - 1.0
        tone = math.sin(2 * math.pi * 2200 * i / RATE)
        samples[idx] += amp * env * (0.7 * noise + 0.3 * tone)


def main() -> int:
    total = int(0.22 * RATE)
    samples = [0.0] * total
    _click(samples, 0.00, 0.045, 0.9, seed=1)  # mirror-up click
    _click(samples, 0.11, 0.060, 1.0, seed=2)  # shutter click ("ka-chak")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        frames = bytearray()
        for value in samples:
            clamped = max(-1.0, min(1.0, value))
            frames += struct.pack("<h", int(clamped * 32767))
        handle.writeframes(bytes(frames))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Generate the asset**

Run: `python build/make_shutter_wav.py`
Expected: prints `wrote .../src/ocr_from2xlsx/assets/shutter.wav (...)` and the file exists.

- [ ] **Step 3: Write the failing test**

```python
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: FAIL with `AttributeError: type object 'ReviewApp' has no attribute '_shutter_sound_path'`

- [ ] **Step 5: Implement `_play_shutter` and `_shutter_sound_path` in `app.py`**

Add these methods to `ReviewApp` (e.g. just after `_zoom_preview`):

```python
    @staticmethod
    def _shutter_sound_path() -> Path | None:
        # app.py lives in src/ocr_from2xlsx/, and the PyInstaller spec bundles the wav
        # under ocr_from2xlsx/assets/, so this resolves for both source runs and the exe.
        path = Path(__file__).resolve().parent / "assets" / "shutter.wav"
        return path if path.is_file() else None

    def _play_shutter(self) -> None:
        try:
            import winsound
        except Exception:
            return  # non-Windows / no audio module: silent no-op
        path = self._shutter_sound_path()
        try:
            if path is not None and path.is_file():
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: PASS (2 passed)

- [ ] **Step 7: Make the asset shippable**

In `pyproject.toml`, add after the `[tool.setuptools.dynamic]` block:

```toml
[tool.setuptools.package-data]
ocr_from2xlsx = ["assets/*.wav"]
```

In `build/ocr-from2xlsx.spec`, change the `datas` line:

```python
    datas=[
        (str(PROJECT_ROOT / "VERSION"), "."),
        (str(PROJECT_ROOT / "src/ocr_from2xlsx/assets/shutter.wav"), "ocr_from2xlsx/assets"),
    ],
```

- [ ] **Step 8: Commit**

```bash
git add build/make_shutter_wav.py src/ocr_from2xlsx/assets/shutter.wav src/ocr_from2xlsx/app.py pyproject.toml build/ocr-from2xlsx.spec tests/test_app_continuous_capture.py
git commit -m "feat: add bundled shutter sound and _play_shutter (safe-degrade)"
```

---

## Task 6: Session state, buttons, start/cancel/undo

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (class attrs, `__init__`, `_build_ui`, new methods)
- Test: `tests/test_app_continuous_capture.py`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_app_continuous_capture.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: FAIL with `AttributeError: ... has no attribute '_start_continuous_capture'`

- [ ] **Step 3: Add class-level defaults + `__init__` state**

In `ReviewApp`'s class-attribute block (near `_preview_zoom`), add:

```python
    _autocapture_active: bool = False
    _autocapture_detector: object | None = None
    _autocapture_output_dir: object | None = None
    _autocapture_prev_gray: object | None = None
    _autocapture_ref_gray: object | None = None
```

In `__init__` (near `self._preview_zoom = 1.0`), add:

```python
        self._autocapture_active = False
        self._autocapture_detector = None
        self._autocapture_output_dir = None
        self._autocapture_prev_gray = None
        self._autocapture_ref_gray = None
        self._autocapture_stills: list[Path] = []
```

- [ ] **Step 4: Add the toolbar buttons**

In `_build_ui`, after the "匯入資料夾批次" button block, add:

```python
        ttk.Button(toolbar, text="連續拍照", command=self._start_continuous_capture).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="完成辨識", command=self._finish_continuous_capture).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="復原上一張", command=self._undo_last_continuous_capture).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="取消連拍", command=self._cancel_continuous_capture).pack(
            side=tk.LEFT, padx=4
        )
```

- [ ] **Step 5: Implement start / cancel / undo / flash**

Add these methods to `ReviewApp`:

```python
    def _start_continuous_capture(self) -> None:
        from ocr_from2xlsx.autocapture import AutoCaptureConfig, AutoCaptureDetector
        from ocr_from2xlsx.capture import CameraDependencyError, require_camera_support

        if self._autocapture_active:
            return
        if self.editing:
            messagebox.showerror(
                "尚未保存", "目前資料已修改，請先使用「確認並寫入」或「強制寫入」。"
            )
            return
        if self._camera_index is None:
            try:
                require_camera_support()
            except CameraDependencyError as exc:
                self._clear_inactive_camera_selection()
                messagebox.showerror("連續拍照", str(exc))
                return
            self._clear_inactive_camera_selection()
            messagebox.showwarning("連續拍照", "請先選擇可用的攝影機。")
            return
        selected_dir = filedialog.askdirectory(title="選擇辨識輸出資料夾")
        if not selected_dir:
            return
        output_dir = Path(selected_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._autocapture_output_dir = output_dir
        self._autocapture_stills = []
        self._autocapture_prev_gray = None
        self._autocapture_ref_gray = None
        self._autocapture_detector = AutoCaptureDetector(AutoCaptureConfig.from_env())
        self._autocapture_active = True
        self._push_status("連續拍照中｜已擷取 0 張｜請放上表單…")
        if not self._has_live_camera_preview():
            self._start_camera(self._camera_index)

    def _cancel_continuous_capture(self) -> None:
        if not self._autocapture_active:
            return
        self._stop_camera()
        self._autocapture_active = False
        count = len(self._autocapture_stills)
        self._push_status(f"已取消連續拍照（保留 {count} 張於輸出資料夾，未辨識）。")

    def _undo_last_continuous_capture(self) -> None:
        if not self._autocapture_active or not self._autocapture_stills:
            self._push_status("沒有可復原的擷取。")
            return
        last = self._autocapture_stills.pop()
        try:
            Path(last).unlink()
        except OSError:
            pass
        self._push_status(f"已復原上一張｜已擷取 {len(self._autocapture_stills)} 張")

    def _flash_preview(self) -> None:
        try:
            self.preview.configure(background="#d0ffd0")
            self.preview.after(120, lambda: self.preview.configure(background="white"))
        except Exception:
            pass
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_continuous_capture.py
git commit -m "feat: add continuous-capture session start/cancel/undo + buttons"
```

---

## Task 7: Auto-capture observe + perform (camera wiring)

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (`_observe_autocapture_frame`, `_perform_autocapture`, hook in `_poll_camera_frame`)
- Test: `tests/test_app_continuous_capture.py`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_app_continuous_capture.py
import sys

from ocr_from2xlsx.autocapture import CAPTURE, DISARMED, AutoCaptureDetector


def test_observe_delegates_to_perform_on_capture(monkeypatch):
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_detector = SimpleNamespace(observe=lambda m: CAPTURE)
    monkeypatch.setattr("ocr_from2xlsx.capture.measure_sharpness", lambda f: 100.0)
    called = []
    monkeypatch.setattr(app, "_perform_autocapture", lambda: called.append(True) or True)
    import numpy as np
    took_over = ReviewApp._observe_autocapture_frame(app, np.zeros((48, 64), dtype="uint8"))
    assert took_over is True
    assert called == [True]


def test_perform_autocapture_saves_still_and_marks_captured(monkeypatch, tmp_path):
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.capture import CaptureResult

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    app._autocapture_prev_gray = None
    shutters = []
    monkeypatch.setattr(
        capture_module, "capture_still",
        lambda *a, **k: CaptureResult(frame="frame", resolution=(1920, 1080), sharpness=180.0, brightness=128.0, passed=True),
    )
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=lambda p, f: Path(p).write_bytes(b"\x89PNG") or True))
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_start_camera", lambda i: None)
    monkeypatch.setattr(app, "_play_shutter", lambda: shutters.append(True))
    monkeypatch.setattr(app, "_flash_preview", lambda: None)

    took_over = ReviewApp._perform_autocapture(app)

    assert took_over is True
    assert len(app._autocapture_stills) == 1
    assert app._autocapture_stills[0].is_file()
    assert app._autocapture_detector.state == DISARMED
    assert shutters == [True]


def test_perform_autocapture_skips_blurry(monkeypatch, tmp_path):
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.capture import CaptureResult

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    monkeypatch.setattr(
        capture_module, "capture_still",
        lambda *a, **k: CaptureResult(frame="frame", resolution=(1920, 1080), sharpness=12.0, brightness=128.0, passed=False),
    )
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_start_camera", lambda i: None)

    ReviewApp._perform_autocapture(app)

    assert app._autocapture_stills == []


def test_perform_autocapture_stops_session_when_no_camera(monkeypatch, tmp_path):
    import ocr_from2xlsx.capture as capture_module

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    monkeypatch.setattr(capture_module, "capture_still", lambda *a, **k: None)
    monkeypatch.setattr(app, "_stop_camera", lambda: None)

    ReviewApp._perform_autocapture(app)

    assert app._autocapture_active is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: FAIL with `AttributeError: ... has no attribute '_observe_autocapture_frame'`

- [ ] **Step 3: Implement observe + perform**

Add these methods to `ReviewApp`:

```python
    def _observe_autocapture_frame(self, frame: object) -> bool:
        """Feed one preview frame to the detector. Returns True when it took over the
        camera (a capture/restart happened) so the poll loop should stop for this tick."""
        from ocr_from2xlsx.autocapture import (
            CAPTURE,
            REARMED,
            FrameMetrics,
            mean_abs_diff,
            to_metric_gray,
        )
        from ocr_from2xlsx.capture import measure_sharpness

        gray = to_metric_gray(frame)
        motion = mean_abs_diff(gray, self._autocapture_prev_gray)
        change = mean_abs_diff(gray, self._autocapture_ref_gray)
        self._autocapture_prev_gray = gray
        try:
            sharpness = measure_sharpness(frame)
        except Exception:
            sharpness = 0.0
        action = self._autocapture_detector.observe(
            FrameMetrics(motion=motion, change_from_ref=change, sharpness=sharpness)
        )
        if action == CAPTURE:
            return self._perform_autocapture()
        if action == REARMED:
            self._push_status(
                f"連續拍照中｜已擷取 {len(self._autocapture_stills)} 張｜請放上下一張…"
            )
        return False

    def _perform_autocapture(self) -> bool:
        from ocr_from2xlsx.autocapture import STALLED
        from ocr_from2xlsx.capture import DEFAULT_MIN_SHARPNESS, capture_still, rotate_frame
        from ocr_from2xlsx.scan import next_output_artifact_path

        index = self._camera_index
        self._stop_camera()
        result = None
        try:
            result = capture_still(index, min_sharpness=DEFAULT_MIN_SHARPNESS)
        except Exception as exc:  # noqa: BLE001 - surface and keep the session recoverable
            self._push_status(f"連續拍照擷取失敗：{exc}")
        if result is None:
            self._push_status("連續拍照：找不到可用的攝影機，已停止。")
            self._autocapture_active = False
            return True
        if not result.passed:
            outcome = self._autocapture_detector.note_failed_capture()
            if outcome == STALLED:
                self._push_status(
                    f"連續拍照：連續多張太模糊（清晰度 {result.sharpness:.0f}），"
                    "請調整對焦/光線後再放紙。"
                )
            else:
                self._push_status(
                    f"連續拍照：太模糊（清晰度 {result.sharpness:.0f}），自動重試…"
                )
            self._start_camera(index)
            return True

        import cv2

        frame = result.frame
        if self._preview_rotation:
            frame = rotate_frame(frame, self._preview_rotation)
        output_dir = self._autocapture_output_dir
        image_path = next_output_artifact_path(output_dir, "scan-capture.png")
        if not cv2.imwrite(str(image_path), frame):
            self._push_status(f"連續拍照：無法寫入擷取影像 {image_path}")
            self._start_camera(index)
            return True
        self._autocapture_stills.append(image_path)
        # Reference for "scene cleared" detection is the triggering PREVIEW frame's gray
        # (same resolution as later preview frames), not the full-res capture_still frame.
        self._autocapture_ref_gray = self._autocapture_prev_gray
        self._autocapture_prev_gray = None
        self._autocapture_detector.mark_captured()
        self._play_shutter()
        self._flash_preview()
        self._push_status(
            f"連續拍照中｜已擷取 {len(self._autocapture_stills)} 張｜請拿開換下一張…"
        )
        self._start_camera(index)
        return True
```

- [ ] **Step 4: Hook the detector into the preview loop**

In `_poll_camera_frame`, immediately after the read + None-check (after line `return` of the `not ok` branch, before the rotation block), insert:

```python
            if self._autocapture_active and self._observe_autocapture_frame(frame):
                return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_continuous_capture.py
git commit -m "feat: wire auto-capture detection into the preview loop"
```

---

## Task 8: Finish session → batch recognize → review

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (`_finish_continuous_capture`)
- Test: `tests/test_app_continuous_capture.py`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_app_continuous_capture.py
def test_finish_routes_stills_to_batch_and_loads_review(monkeypatch, tmp_path):
    import ocr_from2xlsx.scan as scan
    from ocr_from2xlsx.domain import Batch, SourceBatch

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    s1 = tmp_path / "scan-capture.png"
    s2 = tmp_path / "scan-capture-2.png"
    s1.write_bytes(b"x"); s2.write_bytes(b"y")
    app._autocapture_stills = [s1, s2]

    seen = {}
    def fake_prepare(stills, out, template, backend, on_progress=None):
        seen["stills"] = list(stills)
        if on_progress:
            on_progress(2, 2, "scan-capture-2.png")
        return Batch(source_batch=SourceBatch(created_at="t", source_type="scan_records", template_name="service_record.v1"), records=[])
    monkeypatch.setattr(scan, "prepare_records_from_images", fake_prepare)
    monkeypatch.setattr("ocr_from2xlsx.cli._resolve_template", lambda name: SimpleNamespace(template_id=name))
    monkeypatch.setattr(app, "_resolve_recognition_backend", lambda *a, **k: object())
    monkeypatch.setattr(app, "_open_processing_modal", lambda msg: None)
    monkeypatch.setattr(app, "_set_modal_message", lambda m, msg: None)
    monkeypatch.setattr(app, "_close_processing_modal", lambda m: None)
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.app.dump_batch", lambda batch, path: Path(path).write_text("{}"), raising=False)
    loaded = {}
    monkeypatch.setattr(app, "_set_loaded_records", lambda records, path: loaded.update(path=path))
    monkeypatch.setattr("ocr_from2xlsx.app.JsonRecordSource", lambda path: SimpleNamespace(records=lambda: iter([SimpleNamespace(record_id="batch-0001")])))

    ReviewApp._finish_continuous_capture(app)

    assert seen["stills"] == [s1, s2]
    assert app._autocapture_active is False
    assert loaded.get("path") == tmp_path / "scan-prepared.json"


def test_finish_with_no_captures_warns_and_skips(monkeypatch, tmp_path):
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_stills = []
    warnings = []
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showwarning", lambda t, m: warnings.append((t, m)))
    monkeypatch.setattr(
        "ocr_from2xlsx.scan.prepare_records_from_images",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not recognize")),
    )
    ReviewApp._finish_continuous_capture(app)
    assert app._autocapture_active is False
    assert warnings and "沒有可辨識" in warnings[0][1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: FAIL with `AttributeError: ... has no attribute '_finish_continuous_capture'`

- [ ] **Step 3: Implement finish**

Add to `ReviewApp` (note: `dump_batch` and `JsonRecordSource` are already imported in `app.py`; if `dump_batch` is only imported locally elsewhere, import it locally here too):

```python
    def _finish_continuous_capture(self) -> None:
        from ocr_from2xlsx.cli import _resolve_template
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.plugin_backend import scan_doc_preprocess_env_overrides
        from ocr_from2xlsx.scan import next_output_artifact_path, prepare_records_from_images

        if not self._autocapture_active:
            return
        self._stop_camera()
        self._autocapture_active = False
        stills = list(self._autocapture_stills)
        output_dir = self._autocapture_output_dir
        if not stills:
            messagebox.showwarning("連續拍照", "尚未擷取任何影像，沒有可辨識的內容。")
            return
        json_path = next_output_artifact_path(output_dir, "scan-prepared.json")
        modal = self._open_processing_modal("批次辨識中…")
        try:
            backend = self._resolve_recognition_backend(
                json_path, scan_doc_preprocess_env_overrides()
            )
            template = _resolve_template("service_record.v1")

            def _progress(done: int, total: int, name: str) -> None:
                self._set_modal_message(modal, f"批次辨識中… {done}/{total}\n{name}")

            batch = prepare_records_from_images(
                stills, output_dir, template, backend, on_progress=_progress
            )
            dump_batch(batch, json_path)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the user
            self._close_processing_modal(modal)
            messagebox.showerror("批次辨識失敗", str(exc))
            return
        else:
            self._close_processing_modal(modal)
        records = list(JsonRecordSource(json_path).records())
        if not records:
            messagebox.showwarning("沒有可辨識的影像", "辨識結果沒有任何紀錄。")
            return
        self._set_loaded_records(records, json_path)
        self._push_status(f"連續拍照完成：{len(records)} 筆，請逐筆確認後寫入。")
```

> The first test monkeypatches `ocr_from2xlsx.app.dump_batch`; the local `from ocr_from2xlsx.json_io import dump_batch` import shadows that, so the test patches `json_io.dump_batch` instead if needed. To keep the test simple, change the test's patch target to `ocr_from2xlsx.json_io.dump_batch` if `app.dump_batch` does not exist — run the test and follow the actual error.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_app_continuous_capture.py -q`
Expected: PASS (all tests). If the first test errors on the `dump_batch` patch target, change it to `monkeypatch.setattr("ocr_from2xlsx.json_io.dump_batch", lambda batch, path: Path(path).write_text("{}"))`.

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_continuous_capture.py
git commit -m "feat: finish continuous session into existing batch review"
```

---

## Task 9: Integration — docs, packaging check, full suite, manual verify

**Files:**
- Modify: `README.md`, `CHANGELOG.md`

- [ ] **Step 1: README — document the feature**

Add to `README.md` near the webcam section:

```markdown
### 連續拍照（hands-free 自動掃描）

App 工具列「連續拍照」可現場連續掃一疊紙本：把表單一張張放到鏡頭下，系統偵測到畫面**穩定且合焦**後自動拍照（會發出快門聲），請拿開換下一張即可再拍。按「完成辨識」一次批次辨識全部、進逐筆審核；「復原上一張」可丟掉誤拍，「取消連拍」放棄整批。偵測門檻可用 `AUTOCAPTURE_*` 環境變數對相機/光線微調。
```

- [ ] **Step 2: CHANGELOG — add the Unreleased entry**

Add under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- 連續拍照（hands-free 自動掃描）：app 新增「連續拍照」，相機偵測到畫面穩定且合焦即自動拍照（快門聲＋計數回授）、
  「拿開再放」換頁不重複拍同一張；累積整疊後「完成辨識」走既有批次辨識＋逐筆審核，另含「復原上一張」/「取消連拍」。
  新增純狀態機 `autocapture`（可單元測試）、`prepare_records_from_images` 進度回呼、bundled 快門音。偵測門檻
  以 `AUTOCAPTURE_*` 環境變數調校。
```

- [ ] **Step 3: Run the full suite (warnings-as-errors) and policy check**

Run: `python -W error -m pytest -q`
Expected: PASS (all tests, including new `test_autocapture.py` and `test_app_continuous_capture.py`).

Run: `python -m policy_check --repo .`
Expected: no failures.

- [ ] **Step 4: Manual verification (real camera)**

With a webcam connected and the app running (`python -m ocr_from2xlsx app`):
1. Select a camera, click "連續拍照", pick an output folder.
2. Place a form → confirm it auto-captures only after it is still and in focus (shutter sound, count → 1).
3. Lift it → place the next → confirm it captures the next (count → 2), and that holding the same form in place does NOT recapture.
4. Click "復原上一張" → count decrements, the last `scan-capture*.png` is gone.
5. Click "完成辨識" → batch recognizes all stills with `done/total` progress and loads the per-record review with each original image on the left.
Record the camera/lighting and any `AUTOCAPTURE_*` overrides used in the PR description.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: document continuous-capture mode and changelog entry"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** auto-capture + focus confirmation (Tasks 2, 7) · lift-then-place re-arm / no double-capture (Tasks 2, 7) · too-blurry retry→stall (Tasks 2, 7) · per-capture shutter + count + flash (Tasks 5, 6, 7) · undo last (Task 6) · batch-recognize on complete with progress, zero-capture skip, cancel (Tasks 4, 8) · no-camera/degrade (Tasks 6, 7) · packaging the asset (Task 5) · docs/CHANGELOG/policy (Task 9). All delta requirements map to a task.
- **Type consistency:** action constants `CAPTURE/REARMED/STALLED/NONE`, states `ARMED/DISARMED`, `FrameMetrics(motion, change_from_ref, sharpness)`, `AutoCaptureDetector.observe/mark_captured/note_failed_capture`, helpers `to_metric_gray/mean_abs_diff`, and app methods `_start/_finish/_cancel/_undo_continuous_capture`, `_observe_autocapture_frame`, `_perform_autocapture`, `_play_shutter`, `_shutter_sound_path` are used identically across tasks.
- **Placeholder scan:** every code step shows full code; commands have expected output. The only conditional is the `dump_batch` patch target in Task 8, which is resolved by following the actual error (both alternatives spelled out).
```
