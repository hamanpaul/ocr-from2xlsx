# Continuous-capture detection redesign (baseline-diff) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the auto-capture detection signal — from "diff vs the previously captured form" (which fails for stacks of identical templates) to "diff vs a per-session empty-desk baseline over a central ROI" — and fold in the adversarial-review fixes (CJK-safe write, STALLED→pause, `abs()` convergence, camera-loss/recognition-error data recovery, a "辨識完成" dialog).

**Architecture:** The pure `AutoCaptureDetector` keys on `diff_from_baseline` (current central-ROI gray vs the empty-desk baseline); dedup is the clear-cycle (return near baseline before re-arming). The app captures the baseline on session start (clear-desk prompt) with a manual "重設空桌基準" reset, computes metrics on the central ROI, writes stills CJK-safely, and keeps captured stills recoverable.

**Tech Stack:** Python 3.12, Tkinter, OpenCV (`cv2`, guarded), NumPy, pytest. Run tests with the repo venv: `C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe`. Worktree: `C:\Users\haman\auto-xlsx-tranlator\.worktrees\continuous-capture`. If git reports "dubious ownership", prefix with `-c safe.directory='*'`. Append to every commit body: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

- **Modify** `src/ocr_from2xlsx/autocapture.py` — `AutoCaptureConfig` (new fields `roi_fraction`/`present_thresh`/`settle_tol`; drop `newpage_thresh`/`sharpness_rise_tol`), `FrameMetrics` (`change_from_ref`→`diff_from_baseline`), states (`NEED_BASELINE`/`PAUSED`), `set_baseline`, baseline-diff `observe`, `note_failed_capture`→PAUSED, `to_metric_gray` ROI.
- **Rewrite** `tests/test_autocapture.py` — to the new API, incl. the same-template-stack regression.
- **Modify** `src/ocr_from2xlsx/app.py` — baseline capture/reset, `_observe`/`_perform` rework, `_imwrite_unicode`, `_finish` data recovery + "辨識完成" dialog, "重設空桌基準" button, state vars.
- **Modify** `tests/test_app_continuous_capture.py` — `_bare_app` state vars; update observe/perform/finish tests; add baseline, reset, CJK-write, camera-loss-finishable, recognition-error-retry tests.
- **Modify** `README.md`, `CHANGELOG.md`.

---

## Task 1: Detector rework — empty-desk baseline + central ROI

**Files:**
- Modify: `src/ocr_from2xlsx/autocapture.py`
- Rewrite: `tests/test_autocapture.py`

- [ ] **Step 1: Replace `tests/test_autocapture.py` with the new-API tests (write them first; they will fail)**

```python
from __future__ import annotations

import numpy as np

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
```

- [ ] **Step 2: Run to verify failure**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_autocapture.py -q`
Expected: FAIL (ImportError on `NEED_BASELINE`/`PAUSED`, missing `present_thresh`, etc.)

- [ ] **Step 3: Rework `AutoCaptureConfig` (replace the dataclass body + `from_env`)**

Replace the `AutoCaptureConfig` class (lines ~27-58) with:

```python
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
```

- [ ] **Step 4: Replace states/constants, `FrameMetrics`, and the detector (lines ~61-153)**

```python
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
```

- [ ] **Step 5: Add ROI to `to_metric_gray` (replace the function, lines ~156-174)**

```python
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
```

- [ ] **Step 6: Run tests to verify pass**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_autocapture.py -q`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git -c safe.directory='*' add src/ocr_from2xlsx/autocapture.py tests/test_autocapture.py
git -c safe.directory='*' commit -m "feat: rework auto-capture detector to empty-desk baseline + central ROI"
```

---

## Task 2: App baseline capture, reset, and `_observe` rework

**Files:**
- Modify: `src/ocr_from2xlsx/app.py`
- Modify: `tests/test_app_continuous_capture.py`

- [ ] **Step 1: Update `_bare_app()` state vars and add failing tests**

In `tests/test_app_continuous_capture.py`, in `_bare_app()` replace the line
`app._autocapture_ref_gray = None` with:

```python
    app._autocapture_baseline_gray = None
    app._autocapture_need_baseline = False
```

Add these tests:

```python
def test_start_prompts_clear_desk_and_enters_need_baseline(monkeypatch, tmp_path):
    app = _bare_app()
    monkeypatch.setattr("ocr_from2xlsx.app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askokcancel", lambda *a, **k: True)
    monkeypatch.setattr(app, "_has_live_camera_preview", lambda: True)
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is True
    assert app._autocapture_need_baseline is True
    assert app._autocapture_detector.state == "need_baseline"


def test_observe_grabs_baseline_then_arms(monkeypatch):
    import numpy as np
    from ocr_from2xlsx.autocapture import AutoCaptureDetector
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_need_baseline = True
    app._autocapture_detector = AutoCaptureDetector()
    took = ReviewApp._observe_autocapture_frame(app, np.zeros((48, 64), dtype="uint8"))
    assert took is False
    assert app._autocapture_need_baseline is False
    assert app._autocapture_baseline_gray is not None
    assert app._autocapture_detector.state == "armed"


def test_reset_baseline_requests_regrab(monkeypatch):
    app = _bare_app()
    app._autocapture_active = True
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askokcancel", lambda *a, **k: True)
    ReviewApp._reset_baseline(app)
    assert app._autocapture_need_baseline is True
```

- [ ] **Step 2: Run to verify failure**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_app_continuous_capture.py -q`
Expected: FAIL (`_reset_baseline` missing; `_observe` still references `_autocapture_ref_gray`/old metric).

- [ ] **Step 3: Update class attrs + `__init__` state vars**

In `ReviewApp` class-attr block, replace `_autocapture_ref_gray: object | None = None` with:

```python
    _autocapture_baseline_gray: object | None = None
    _autocapture_need_baseline: bool = False
```

In `__init__`, replace `self._autocapture_ref_gray = None` with:

```python
        self._autocapture_baseline_gray = None
        self._autocapture_need_baseline = False
```

- [ ] **Step 4: Rework `_start_continuous_capture` (baseline flow)**

Replace the body from `selected_dir = filedialog.askdirectory(...)` onward (lines ~1078-1091) with:

```python
        selected_dir = filedialog.askdirectory(title="選擇辨識輸出資料夾")
        if not selected_dir:
            return
        if not messagebox.askokcancel("連續拍照", "請清空桌面，確定後擷取『空桌基準』。"):
            return
        output_dir = Path(selected_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._autocapture_output_dir = output_dir
        self._autocapture_stills = []
        self._autocapture_prev_gray = None
        self._autocapture_baseline_gray = None
        self._autocapture_need_baseline = True
        self._autocapture_detector = AutoCaptureDetector(AutoCaptureConfig.from_env())
        self._autocapture_active = True
        self._push_status("連續拍照：擷取空桌基準中…請保持桌面淨空。")
        if not self._has_live_camera_preview():
            self._start_camera(self._camera_index)
```

- [ ] **Step 5: Rework `_observe_autocapture_frame` (baseline grab + diff)**

Replace `_observe_autocapture_frame` (lines ~1115-1144) with:

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

        roi = self._autocapture_detector.config.roi_fraction
        gray = to_metric_gray(frame, roi_fraction=roi)
        if self._autocapture_need_baseline:
            self._autocapture_baseline_gray = gray
            self._autocapture_prev_gray = gray
            self._autocapture_need_baseline = False
            self._autocapture_detector.set_baseline()
            self._push_status("連續拍照：已設定空桌基準｜請放上表單…")
            return False
        motion = mean_abs_diff(gray, self._autocapture_prev_gray)
        diff_from_baseline = mean_abs_diff(gray, self._autocapture_baseline_gray)
        self._autocapture_prev_gray = gray
        try:
            sharpness = measure_sharpness(frame)
        except Exception:
            sharpness = 0.0
        action = self._autocapture_detector.observe(
            FrameMetrics(
                motion=motion, diff_from_baseline=diff_from_baseline, sharpness=sharpness
            )
        )
        if action == CAPTURE:
            return self._perform_autocapture()
        if action == REARMED:
            self._push_status(
                f"連續拍照中｜已擷取 {len(self._autocapture_stills)} 張｜請放上下一張…"
            )
        return False
```

- [ ] **Step 6: Add `_reset_baseline` (place after `_undo_last_continuous_capture`)**

```python
    def _reset_baseline(self) -> None:
        if not self._autocapture_active:
            self._push_status("尚未開始連續拍照。")
            return
        if not messagebox.askokcancel("重設空桌基準", "請清空桌面，確定後重抓『空桌基準』。"):
            return
        self._autocapture_need_baseline = True
        self._autocapture_prev_gray = None
        self._push_status("連續拍照：重新擷取空桌基準中…請保持桌面淨空。")
```

- [ ] **Step 7: Add the "重設空桌基準" toolbar button**

In `_build_ui`, immediately after the `text="取消連拍"` button block, add:

```python
        ttk.Button(toolbar, text="重設空桌基準", command=self._reset_baseline).pack(
            side=tk.LEFT, padx=4
        )
```

- [ ] **Step 8: Run tests to verify pass**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_app_continuous_capture.py -q`
Expected: the new baseline tests PASS. (Some Task-7-era `_perform` tests may still pass; the imwrite-based ones are updated in Task 3.)

- [ ] **Step 9: Commit**

```bash
git -c safe.directory='*' add src/ocr_from2xlsx/app.py tests/test_app_continuous_capture.py
git -c safe.directory='*' commit -m "feat: capture empty-desk baseline (ROI) for continuous-capture detection"
```

---

## Task 3: App `_perform` rework — CJK-safe write, write-fail cooldown, STALLED pause

**Files:**
- Modify: `src/ocr_from2xlsx/app.py`
- Modify: `tests/test_app_continuous_capture.py`

- [ ] **Step 1: Update the `_perform` tests to the new cv2 (imencode) + add a CJK + pause test**

In `tests/test_app_continuous_capture.py`:

(1) In `test_perform_autocapture_saves_still_and_marks_captured`, replace the cv2 monkeypatch line with an `imencode` fake:

```python
    import numpy as np
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(
        imencode=lambda ext, f: (True, np.frombuffer(b"\x89PNG\r\n", dtype="uint8")),
    ))
```

(2) In `test_perform_autocapture_imwrite_failure_restarts_camera`, replace the cv2 monkeypatch with a failing `imencode`:

```python
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imencode=lambda ext, f: (False, None)))
```

(3) Update `test_perform_autocapture_stalled_after_retry_limit`: after the loop, also assert the detector paused:

```python
    from ocr_from2xlsx.autocapture import PAUSED
    assert app._autocapture_detector.state == PAUSED
```

(4) Add a CJK-path write test:

```python
def test_perform_autocapture_writes_to_cjk_output_dir(monkeypatch, tmp_path):
    import numpy as np
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.autocapture import AutoCaptureDetector
    from ocr_from2xlsx.capture import CaptureResult

    cjk_dir = tmp_path / "表單辨識"
    cjk_dir.mkdir()
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = cjk_dir
    app._autocapture_detector = AutoCaptureDetector()
    app._autocapture_prev_gray = None
    monkeypatch.setattr(
        capture_module, "capture_still",
        lambda *a, **k: CaptureResult(frame="frame", resolution=(1920, 1080), sharpness=180.0, brightness=128.0, passed=True),
    )
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(
        imencode=lambda ext, f: (True, np.frombuffer(b"\x89PNG\r\n", dtype="uint8")),
    ))
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_start_camera", lambda i: None)
    monkeypatch.setattr(app, "_play_shutter", lambda: None)
    monkeypatch.setattr(app, "_flash_preview", lambda: None)

    ReviewApp._perform_autocapture(app)

    assert len(app._autocapture_stills) == 1
    assert app._autocapture_stills[0].is_file()
    assert "表單辨識" in str(app._autocapture_stills[0])
```

- [ ] **Step 2: Run to verify failure**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_app_continuous_capture.py -k perform -q`
Expected: FAIL (`_imwrite_unicode` not defined; old `_perform` still calls `cv2.imwrite`; STALLED test lacks PAUSED).

- [ ] **Step 3: Add `_imwrite_unicode` (place after `_shutter_sound_path`)**

```python
    @staticmethod
    def _imwrite_unicode(path: Path, frame: object) -> bool:
        """Write an image to a possibly non-ASCII path. cv2.imwrite silently fails on
        non-ASCII (e.g. CJK) paths on Windows; imencode + write_bytes does not."""
        import cv2

        try:
            ok, buf = cv2.imencode(".png", frame)
            if not ok:
                return False
            Path(path).write_bytes(buf.tobytes())
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Rework `_perform_autocapture` (replace lines ~1146-1199)**

```python
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
            self._autocapture_active = False
            self._push_status(
                f"連續拍照：相機中斷，已擷取 {len(self._autocapture_stills)} 張；"
                "可按『完成辨識』辨識，或『取消連拍』放棄。"
            )
            return True
        if not result.passed:
            outcome = self._autocapture_detector.note_failed_capture()
            if outcome == STALLED:
                self._push_status(
                    f"連續拍照：連續多張太模糊（清晰度 {result.sharpness:.0f}），已暫停；"
                    "請調整對焦/光線後按『重設空桌基準』。"
                )
            else:
                self._push_status(
                    f"連續拍照：太模糊（清晰度 {result.sharpness:.0f}），自動重試…"
                )
            self._start_camera(index)
            return True

        frame = result.frame
        if self._preview_rotation:
            frame = rotate_frame(frame, self._preview_rotation)
        output_dir = self._autocapture_output_dir
        image_path = next_output_artifact_path(output_dir, "scan-capture.png")
        if not self._imwrite_unicode(image_path, frame):
            outcome = self._autocapture_detector.note_failed_capture()
            if outcome == STALLED:
                self._push_status(
                    f"連續拍照：連續無法寫入影像（{image_path}），已暫停；"
                    "請檢查輸出資料夾後按『重設空桌基準』。"
                )
            else:
                self._push_status(
                    f"連續拍照：無法寫入擷取影像 {image_path}，自動重試…"
                )
            self._start_camera(index)
            return True
        self._autocapture_stills.append(image_path)
        # Baseline stays the empty desk; reset only the motion reference after the reopen.
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

- [ ] **Step 5: Run tests to verify pass**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_app_continuous_capture.py -q`
Expected: PASS (all perform tests incl. CJK + STALLED→PAUSED).

- [ ] **Step 6: Commit**

```bash
git -c safe.directory='*' add src/ocr_from2xlsx/app.py tests/test_app_continuous_capture.py
git -c safe.directory='*' commit -m "fix: CJK-safe still write, write-fail cooldown, STALLED pauses session"
```

---

## Task 4: App `_finish` data recovery + "辨識完成" dialog

**Files:**
- Modify: `src/ocr_from2xlsx/app.py`
- Modify: `tests/test_app_continuous_capture.py`

- [ ] **Step 1: Add failing tests (camera-loss finishable, recognition-error retry, completion dialog)**

In `tests/test_app_continuous_capture.py`:

(1) In `test_finish_routes_stills_to_batch_and_loads_review`, add an `showinfo` capture and assert the dialog:

```python
    infos = []
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda t, m: infos.append((t, m)))
```
then after the call:
```python
    assert any(t == "辨識完成" for t, _ in infos)
    assert app._autocapture_stills == []  # consumed on success
```

(2) Add:

```python
def test_finish_works_after_camera_loss_when_stills_exist(monkeypatch, tmp_path):
    import ocr_from2xlsx.scan as scan
    from ocr_from2xlsx.domain import Batch, SourceBatch

    app = _bare_app()
    app._autocapture_active = False  # camera-loss set this False, but stills remain
    app._autocapture_output_dir = tmp_path
    s1 = tmp_path / "scan-capture.png"; s1.write_bytes(b"x")
    app._autocapture_stills = [s1]
    monkeypatch.setattr(scan, "prepare_records_from_images",
                        lambda *a, **k: Batch(source_batch=SourceBatch(created_at="t", source_type="scan_records", template_name="service_record.v1"), records=[]))
    monkeypatch.setattr("ocr_from2xlsx.cli._resolve_template", lambda name: SimpleNamespace(template_id=name))
    monkeypatch.setattr(app, "_resolve_recognition_backend", lambda *a, **k: object())
    monkeypatch.setattr(app, "_open_processing_modal", lambda msg: None)
    monkeypatch.setattr(app, "_set_modal_message", lambda m, msg: None)
    monkeypatch.setattr(app, "_close_processing_modal", lambda m: None)
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.json_io.dump_batch", lambda batch, path: Path(path).write_text("{}"))
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda *a, **k: None)
    loaded = {}
    monkeypatch.setattr(app, "_set_loaded_records", lambda records, path: loaded.update(path=path))
    monkeypatch.setattr("ocr_from2xlsx.app.JsonRecordSource",
                        lambda path: SimpleNamespace(records=lambda: iter([SimpleNamespace(record_id="batch-0001")])))

    ReviewApp._finish_continuous_capture(app)
    assert loaded.get("path") == tmp_path / "scan-prepared.json"


def test_finish_recognition_error_preserves_stills_for_retry(monkeypatch, tmp_path):
    import ocr_from2xlsx.scan as scan
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    s1 = tmp_path / "scan-capture.png"; s1.write_bytes(b"x")
    app._autocapture_stills = [s1]
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_resolve_recognition_backend", lambda *a, **k: object())
    monkeypatch.setattr("ocr_from2xlsx.cli._resolve_template", lambda name: SimpleNamespace(template_id=name))
    monkeypatch.setattr(app, "_open_processing_modal", lambda msg: None)
    monkeypatch.setattr(app, "_close_processing_modal", lambda m: None)
    errors = []
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showerror", lambda t, m: errors.append((t, m)))
    monkeypatch.setattr(scan, "prepare_records_from_images",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("backend down")))
    ReviewApp._finish_continuous_capture(app)
    assert app._autocapture_stills == [s1]  # preserved → retryable
    assert errors and errors[0][0] == "批次辨識失敗"
```

- [ ] **Step 2: Run to verify failure**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_app_continuous_capture.py -k finish -q`
Expected: FAIL (no "辨識完成" dialog; finish guarded on `_autocapture_active`; stills cleared semantics differ).

- [ ] **Step 3: Rework `_finish_continuous_capture` (replace lines ~1201-1242)**

```python
    def _finish_continuous_capture(self) -> None:
        from ocr_from2xlsx.cli import _resolve_template
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.plugin_backend import scan_doc_preprocess_env_overrides
        from ocr_from2xlsx.scan import next_output_artifact_path, prepare_records_from_images

        stills = list(self._autocapture_stills)
        if not self._autocapture_active and not stills:
            return
        self._stop_camera()
        self._autocapture_active = False
        if not stills:
            messagebox.showwarning("連續拍照", "尚未擷取任何影像，沒有可辨識的內容。")
            return
        json_path = next_output_artifact_path(self._autocapture_output_dir, "scan-prepared.json")
        modal = self._open_processing_modal("批次辨識中…")
        try:
            backend = self._resolve_recognition_backend(
                json_path, scan_doc_preprocess_env_overrides()
            )
            template = _resolve_template("service_record.v1")

            def _progress(done: int, total: int, name: str) -> None:
                self._set_modal_message(modal, f"批次辨識中… {done}/{total}\n{name}")

            batch = prepare_records_from_images(
                stills, self._autocapture_output_dir, template, backend, on_progress=_progress
            )
            dump_batch(batch, json_path)
        except Exception as exc:  # noqa: BLE001 - keep the stills for a retry
            self._close_processing_modal(modal)
            messagebox.showerror(
                "批次辨識失敗", f"{exc}\n（已擷取的影像保留，可再次按『完成辨識』重試。）"
            )
            return
        else:
            self._close_processing_modal(modal)
        records = list(JsonRecordSource(json_path).records())
        if not records:
            messagebox.showwarning("沒有可辨識的影像", "辨識結果沒有任何紀錄。")
            return
        self._autocapture_stills = []  # consumed
        messagebox.showinfo("辨識完成", f"已辨識 {len(records)} 筆，進入逐張人工校正。")
        self._set_loaded_records(records, json_path)
        self._push_status(f"連續拍照完成：{len(records)} 筆，請逐筆確認後寫入。")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m pytest tests/test_app_continuous_capture.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git -c safe.directory='*' add src/ocr_from2xlsx/app.py tests/test_app_continuous_capture.py
git -c safe.directory='*' commit -m "fix: keep continuous-capture stills recoverable; add recognition-complete dialog"
```

---

## Task 5: Docs + verification

**Files:**
- Modify: `README.md`, `CHANGELOG.md`

- [ ] **Step 1: README — update the continuous-capture section**

Replace the body of the "### 連續拍照（hands-free 自動掃描）" section in `README.md` with:

```markdown
### 連續拍照（hands-free 自動掃描）

App 工具列「連續拍照」可現場連續掃一疊紙本：開始時先**清空桌面擷取「空桌基準」**，之後把表單一張張放到鏡頭下，系統偵測到「畫面相對空桌出現內容、穩定且合焦」就自動拍照（快門聲＋計數），請拿開換下一張即可再拍（回到空桌才會再武裝，因此同版型一疊也能逐張拍）。背景/光線變了可按「重設空桌基準」重抓。連續多張太模糊會**暫停**等你處理。按「完成辨識」一次批次辨識全部，跳「辨識完成」後進入逐張人工校正（確認→寫入 xlsx→下一張）。偵測門檻可用 `AUTOCAPTURE_*` 環境變數對相機/光線微調。
```

- [ ] **Step 2: CHANGELOG — add the redesign entry under `## [Unreleased]` → `### Changed`**

```markdown
- 連續拍照偵測改用**空桌基準差異法（中央 ROI）**：原本以「與上一張已拍表單的差異」判定新張，對同版型一疊會漏拍第二張；改為與本 session「空桌基準」比對、淨空循環去重，並修正中文路徑寫檔（imencode+write_bytes）、連續模糊改**暫停**、合焦收斂改雙向 abs、相機中斷/辨識失敗保留已擷取影像可續辨識，辨識完成後跳通知再進逐張校正。校正進度 resume 另立 issue #37。
```

- [ ] **Step 3: Full suite + policy**

Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -W error -m pytest -q`
Expected: PASS (0 failures).
Run: `& "C:\Users\haman\auto-xlsx-tranlator\.venv\Scripts\python.exe" -m policy_check --repo .`
Expected: no failures.

- [ ] **Step 4: Commit**

```bash
git -c safe.directory='*' add README.md CHANGELOG.md
git -c safe.directory='*' commit -m "docs: document baseline-diff continuous-capture redesign"
```

- [ ] **Step 5: Manual + adversarial (record outcomes in the PR)**

- Real-camera walkthrough: clear desk → confirm baseline → place a same-template form (auto-captures after it settles) → lift → place the next identical form (also auto-captures) → "重設空桌基準" after a lighting change still works → "完成辨識" → "辨識完成" dialog → per-record review. Record `AUTOCAPTURE_*` overrides used.
- Re-run an adversarial review focused on detection; the `test_second_identical_template_form_is_captured` regression must stay green.

---

## Self-Review (completed during planning)

- **Spec coverage:** baseline-diff detection + central ROI (Task 1) · same-template regression (Task 1) · baseline capture + reset (Task 2) · clear-cycle dedup / PAUSED / abs settle (Task 1) · CJK-safe write + write-fail cooldown + STALLED pause (Task 3) · camera-loss/recognition-error recovery + 辨識完成 dialog (Task 4) · docs/verify (Task 5). All redesign-spec requirements map to a task.
- **Type/name consistency:** `FrameMetrics(motion, diff_from_baseline, sharpness)`, states `NEED_BASELINE/ARMED/DISARMED/PAUSED`, `set_baseline`, `present_thresh/clear_thresh/settle_tol/roi_fraction`, app vars `_autocapture_baseline_gray`/`_autocapture_need_baseline`, `_imwrite_unicode`, `_reset_baseline` are used identically across tasks; all old `change_from_ref`/`newpage_thresh`/`_autocapture_ref_gray` references are removed (autocapture.py Task 1; app.py Tasks 2-3; tests updated in each).
- **Placeholder scan:** every step has full code + exact commands.
```
