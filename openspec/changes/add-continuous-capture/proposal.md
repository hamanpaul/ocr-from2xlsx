# Proposal: Continuous hands-free webcam auto-capture (scan a stack of forms)

**Change ID:** `add-continuous-capture`
**Created:** 2026-06-22
**Updated:** 2026-06-24 (detection redesign — baseline-diff)
**Status:** Draft
**Design:** `docs/superpowers/specs/2026-06-22-continuous-capture-design.md` (original) +
`docs/superpowers/specs/2026-06-24-continuous-capture-detection-redesign-design.md` (detection redesign, authoritative for detection)
**Related:** issue #37 (resumable correction progress — separate change, out of scope here)

---

## Problem Statement

Recognition is settled: batch processing + a local small model (VLM) for Chinese handwriting. Two
input paths exist with a gap between them — **single webcam capture** (one-shot) and **folder batch**
(pre-existing files). Missing is the on-site workflow: **digitizing a physical stack of forms with the
document camera** — place a form, it is captured, swap to the next, repeat. Affected: the
cancer-resource-center operator scanning paper service-records into the monthly Excel.

The first implementation detected "a new page" by comparing each frame to the **previously captured
form**. An adversarial review proved this fails the primary use case: a stack of the **same printed
template** (forms ~99% identical) yields a frame difference far below the trigger threshold, so the
**second form is never captured** — and the metric measures movement, not content, so tuning cannot fix
it. The same review found additional defects: `cv2.imwrite` silently fails on non-ASCII (CJK) output
paths (this operator's locale), repeated-blur "STALLED" loops the shutter forever, the focus-convergence
check is one-sided, and a mid-session camera loss or a recognition error strands already-captured stills.

## Proposed Solution

A **hands-free continuous capture session** with **empty-desk-baseline** detection:

- At session start the user clears the capture area and the app captures an **empty-desk baseline**
  (central ROI). Each preview frame's central ROI is compared to that baseline: a form is **present**
  when the difference exceeds a present threshold; the desk is **clear** when it returns near the
  baseline. Presence/clearance are judged against the **empty desk**, never against the previous form,
  so identical templates all register and **dedup is the clear-cycle** (must return near-empty to
  re-arm). A **"reset baseline"** action re-establishes it (lighting/background drift, or resume).
- On trigger (present + stationary + focus settled, `abs(Δsharpness) ≤ tol`), the session uses the
  proven **`capture_still`** path (reopen + autofocus warm-up + full-resolution sharpness gate) so
  **focus is confirmed before the saved shot**. The still is written with a **CJK-safe** writer
  (`imencode` + `write_bytes`, new path only) and accumulated; no per-form button press.
- Repeated full-resolution blur (bounded retries) **pauses** the session and waits for the user (no
  infinite retry). Each capture gives a **shutter sound** + flash + running count; **Undo last**
  discards a mis-capture.
- On **Complete**, all stills are recognized via the existing `prepare_records_from_images` (per-form
  progress), a **"recognition complete"** dialog is shown, then the batch loads into the existing
  per-record review (confirm → write XLSX → next). Captured stills survive a mid-session camera loss
  and a recognition error (retryable), so work is not lost. **Cancel** discards without recognizing.

The only new core logic is the detector state machine (pure, unit-testable). The rest reuses
`capture_still`, `rotate_frame`, `prepare_records_from_images`, `_resolve_recognition_backend`, and the
existing review flow.

## Scope

### In Scope
- Empty-desk-baseline detection over a central ROI; clear-cycle dedup; explicit baseline capture at
  start + manual reset.
- Pure `autocapture` detector (states incl. NEED_BASELINE / ARMED / DISARMED / PAUSED) + thin
  cv2-guarded metric helpers; thresholds env-overridable, calibrated on-device.
- Focus-confirmed `capture_still`; CJK-safe still write (continuous path only); `abs()` convergence.
- Repeated-blur → paused session (no infinite retry).
- Per-capture shutter sound + flash + count; **Undo last**; **Cancel**.
- Completion: recognize via existing batch flow with `on_progress`, **"recognition complete" dialog**,
  then existing per-record review; data recovery (camera-loss stills finishable, recognition-error
  retryable).
- Bundle a license-clean `shutter.wav` and include it in packaging.

### Out of Scope
- **Resumable correction progress** (persisting review/confirm progress across app restarts) — issue #37.
- Background recognition while capturing, or review-as-you-go.
- CJK-write fix to the existing single-capture `_recognize_capture` (left untouched on purpose).
- Multi-photo-per-record stitching; auto edge-crop / de-skew / super-resolution; per-frame live
  orientation detection.
- Changes to the recognition backend, `service_record.v1`, `workbook.py`, or review UI semantics
  (beyond the completion dialog).

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `src/ocr_from2xlsx/autocapture.py` | Yes (rework) | Detector keyed on `diff_from_baseline` over a central ROI (replaces `change_from_ref`); NEED_BASELINE/PAUSED states; `set_baseline`; `abs()` convergence; env-overridable thresholds. |
| `src/ocr_from2xlsx/app.py` | Yes | Baseline capture prompt + "reset baseline" button; `_observe` uses baseline+ROI (no ref_gray); CJK-safe write; repeated-blur pause; camera-loss/recognition-error data recovery; "recognition complete" dialog. |
| `src/ocr_from2xlsx/scan.py` | Yes (small) | `prepare_records_from_images` optional `on_progress(done, total, name)`. |
| `capture_still` / `rotate_frame` / `measure_sharpness` | No (reuse) | Reused as-is. |
| Recognition backend / `service_record.v1` / `workbook.py` / review UI | No | Reused unchanged. |
| `assets/shutter.wav`, `build/package.py`, `pyproject.toml` | Yes | Bundled audio asset. |

## Architecture Considerations

Follows the repo's "pure decision logic + thin cv2 wrappers" pattern: the detector consumes only scalar
`FrameMetrics` (`motion`, `diff_from_baseline`, `sharpness`), 100% unit-testable without OpenCV; image
math (central-ROI gray, `mean_abs_diff`) is a guarded helper. Detection compares to a per-session
empty-desk baseline, so identical templates are distinguishable from the desk and dedup falls out of the
clear-cycle. Focus is confirmed twice (preview settle pre-gate + `capture_still`'s full-resolution gate).
Completion reuses `prepare_records_from_images`, emitting the same normalized `Batch` the review consumes.

## Success Criteria

- [ ] A stack of identical-template forms is captured form-by-form hands-free (regression test proves
  the 2nd identical form IS captured); the same form left in place is never captured twice.
- [ ] Stills save correctly to non-ASCII (CJK) output paths; repeated blur pauses (no infinite shutter).
- [ ] Each capture gives shutter + count; Undo-last and Cancel work; shutter degrades safely.
- [ ] Completion recognizes via the batch path with progress, shows a "recognition complete" dialog,
  enters per-record review; camera-loss keeps stills finishable; recognition error is retryable.
- [ ] `autocapture` has model-free, cv2-free unit tests (baseline present/clear, ROI, settle abs,
  re-arm, repeated-blur→PAUSED); app-level tests with fakes cover baseline capture/reset, CJK write,
  data recovery.
- [ ] `python -W error -m pytest -q` and `python -m policy_check --repo .` green; CHANGELOG / openspec
  base spec / README synced; `shutter.wav` bundled.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Baseline invalid (desk not actually clear at capture; lighting/background drift mid-session) | Med | Med | Explicit "clear desk" prompt at start + manual "reset baseline"; human review backstop + Undo-last. |
| Present/clear thresholds mis-tuned per camera | Med | Med | Env-overridable thresholds + on-device calibration; hysteresis (`clear_thresh < present_thresh`). |
| `capture_still` reopen per form is slow / flickers | High | Low | Accepted trade-off for the proven focus-confirmed path; capture time is small vs VLM recognition. |
| Transient occlusion (hand/shadow) over a present form perturbs detection | Med | Low | Stationary + settle gates; ROI central; dedup needs a real return-to-baseline. |
| Shutter asset licensing / unavailable | Low | Low | CC0 `shutter.wav`; safe degrade. |
