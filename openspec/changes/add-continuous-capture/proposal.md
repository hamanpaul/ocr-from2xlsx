# Proposal: Continuous hands-free webcam auto-capture (scan a stack of forms)

**Change ID:** `add-continuous-capture`
**Created:** 2026-06-22
**Status:** Draft
**Design:** `docs/superpowers/specs/2026-06-22-continuous-capture-design.md`

---

## Problem Statement

Recognition is settled: batch processing + a local small model (VLM) for Chinese handwriting. Two
input paths exist, with a gap between them:

- **Single webcam capture** (`擷取並辨識` / `_capture_and_recognize`) — captures one still, recognizes
  it, then reviews. One-shot; cannot scan a stack.
- **Folder batch** (`匯入資料夾批次` / `prepare_records_from_folder`) — recognizes every image/PDF in a
  folder, then reviews one-by-one with each record's original page shown. But the source is
  pre-existing files, not the live camera.

Missing is the on-site workflow: **digitizing a physical stack of forms with the document camera** —
place a form, it is captured, swap to the next, repeat. Affected: the cancer-resource-center operator
scanning paper service-records into the monthly Excel.

## Proposed Solution

A **hands-free continuous capture session** in the desktop app:

- While the live preview runs, a small **auto-capture detector** watches each frame. When a newly
  placed form is **stationary and in focus** (sharpness at/above a preview threshold and no longer
  rising — autofocus converged), it triggers a capture.
- On trigger, the session uses the existing **`capture_still`** path (reopen + autofocus warm-up +
  sharpness gate) to take a high-resolution still — so **focus is confirmed before the saved shot**.
  The still is accumulated; no per-form button press.
- **Re-arm = "lift then place"**: after a capture, the session waits until the scene changes
  substantially (the form removed/swapped) before arming the next, so the same form is never captured
  twice.
- Each capture gives an immediate **shutter sound** + on-screen flash and a running count, since a
  hands-free operator is not watching the screen. **Undo last** discards a mis-captured shot.
- On **Complete**, all accumulated stills are recognized in one pass through the existing
  `prepare_records_from_images` and loaded into the existing per-record review (original image shown
  per record), with `done/total` progress. **Cancel** discards without recognizing.

The only new core logic is the detector state machine (pure, unit-testable). Everything else reuses
`capture_still`, `rotate_frame`, `prepare_records_from_images`, `_resolve_recognition_backend`, and
the existing review flow.

## Scope

### In Scope
- A hands-free continuous capture session: auto-detect → focus-confirmed `capture_still` → accumulate.
- "Lift then place" re-arm (scene-change detection) so the same form is not double-captured.
- Pure `autocapture` detector state machine + thin cv2 frame-metric helpers; thresholds with env
  overrides, calibrated on-device.
- Per-capture shutter sound + on-screen flash + running count; **Undo last**; **Cancel**.
- On completion, recognize all stills via the existing image-batch flow into the existing review, with
  per-form progress (a small `on_progress` added to `prepare_records_from_images`, symmetric to the
  folder-batch path).
- Bundle a license-clean `shutter.wav` and include it in packaging.

### Out of Scope
- Background recognition while capturing, or review-as-you-go (capture-then-review per form).
- Multi-photo-per-record stitching; auto edge-crop / de-skew / super-resolution.
- Per-frame live orientation detection (CPU-infeasible; the existing rotate setting is reused).
- Changes to the recognition backend, `service_record.v1`, `workbook.py`, or the review UI semantics.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `src/ocr_from2xlsx/autocapture.py` | Yes (new) | Pure detector state machine + cv2-guarded frame-metric helpers (motion / change-from-ref / sharpness on downscaled grayscale). |
| `src/ocr_from2xlsx/app.py` | Yes | "連續拍照" button + session flow wired into `_poll_camera_frame`; status/count line; shutter+flash; Complete/Cancel/Undo. |
| `src/ocr_from2xlsx/scan.py` | Yes (small) | `prepare_records_from_images` gains optional `on_progress(done, total, name)` (mirrors `prepare_records_from_folder`). |
| `capture_still` / `rotate_frame` / `measure_sharpness` | No (reuse) | Capture, rotation, sharpness reused as-is. |
| Recognition backend / `service_record.v1` / `workbook.py` / review UI | No | Reused unchanged via the existing batch path. |
| `assets/shutter.wav`, `build/package.py` | Yes | New audio asset bundled into the PyInstaller exe. |

## Architecture Considerations

Follows the repo's "pure decision logic + thin cv2 wrappers" pattern (`decide_camera_selection`,
`passes_sharpness_gate`, `mark_detect`): the detector state machine consumes only scalar
`FrameMetrics`, so it is 100% unit-testable without OpenCV; image math is a separate guarded helper.
The session reuses the live-preview loop and the proven `capture_still` path (capture source: B), so
focus confirmation is enforced twice — preview-side convergence pre-gate plus `capture_still`'s
full-resolution sharpness gate. The preview sharpness threshold is intentionally separate from the
full-resolution `DEFAULT_MIN_SHARPNESS`. Completion reuses `prepare_records_from_images`, emitting the
same normalized `Batch` the review flow already consumes.

## Success Criteria

- [ ] A continuous session auto-captures successive forms hands-free, confirming focus before each
  saved still, and never double-captures the same form (lift-then-place re-arm).
- [ ] Each capture gives a shutter sound + on-screen count; Undo-last and Cancel work; the shutter
  degrades safely when audio is unavailable.
- [ ] Completion recognizes all stills via the existing batch path into the existing per-record review
  with `done/total` progress; zero captures starts no recognition.
- [ ] The `autocapture` state machine has model-free, cv2-free unit tests (arm/capture/re-arm/retry/
  cooldown/env-overrides); app-level tests with injected fakes cover accumulate/complete/undo/cancel.
- [ ] `python -W error -m pytest -q` and `python -m policy_check --repo .` green; CHANGELOG / openspec
  base spec / README synced; `shutter.wav` bundled in the exe.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Detection thresholds mis-tuned (false / missed triggers) on real camera | Med | Med | Env-overridable thresholds + on-device calibration; Undo-last and human review backstop. |
| `capture_still` reopen per form is slow / flickers (capture source B) | High | Low | Accepted trade-off for the proven path; capture time is small vs VLM recognition. |
| Same form double-captured if re-arm too sensitive | Med | Med | Lift-then-place requires a large sustained scene change (`clear_thresh` > `newpage_thresh`) for K frames; Undo-last. |
| Shutter audio asset licensing / unavailable on target | Low | Low | Ship a CC0 `shutter.wav`; safe degrade to a fallback tone / silent. |
| Per-frame detection cost on the Tk main thread | Low | Low | Metrics computed on a downscaled grayscale copy; existing poll cadence unchanged. |
