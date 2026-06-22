# Implementation Tasks: Continuous hands-free webcam auto-capture

**Change ID:** `add-continuous-capture`

All implementation uses TDD with fail-first tests before production code. Phase 1 (the pure detector)
is the foundation and lands first; the state machine must be testable with no camera and no OpenCV.

## Phase 1: Auto-capture detector (pure state machine + cv2-guarded metrics)

- [ ] Add fail-first tests for `autocapture` driven by scalar `FrameMetrics` sequences (no cv2):
  arm → CAPTURE only when stationary (`motion < thresh` for `stable_frames`) AND focus converged
  (`sharpness ≥ preview_min_sharpness` and not still rising) AND new (`change_from_ref ≥ newpage_thresh`
  or first); no capture while sharpness is still rising; `mark_captured()` → DISARMED; re-arm only on
  scene clear (`change_from_ref ≥ clear_thresh` for `clear_frames`); `note_failed_capture()` cooldown +
  `retry_limit` → STALLED; cooldown suppresses re-fire; env threshold overrides parsed.
- [ ] Implement `src/ocr_from2xlsx/autocapture.py`: the pure `AutoCaptureDetector` (states ARMED /
  DISARMED, actions CAPTURE / REARMED / STALLED / none), config dataclass with defaults +
  `AUTOCAPTURE_*` env overrides, and cv2-guarded frame-metric helpers (`motion`, `change_from_ref`,
  `sharpness` on a downscaled grayscale copy) kept separate from the state machine.

**Quality Gate:**
- [ ] State-machine tests pass with neither a camera nor OpenCV imported.

## Phase 2: Batch-from-stills progress + shutter sound asset

- [ ] Add a fail-first test that `prepare_records_from_images` calls an optional
  `on_progress(done, total, name)` once per still, in order.
- [ ] Implement the optional `on_progress` param on `prepare_records_from_images` (mirrors
  `prepare_records_from_folder`); default `None` keeps current behavior.
- [ ] Add `assets/shutter.wav` (short, mono, license-clean CC0) and an `app._play_shutter()` helper:
  `winsound.PlaySound(path, SND_FILENAME | SND_ASYNC)` on Windows, safe no-op / fallback tone when
  winsound, the asset, or audio is unavailable. Add a test that the unavailable path is a silent no-op.

**Quality Gate:**
- [ ] `on_progress` test green; `_play_shutter` degrade path test green (no audio in CI).

## Phase 3: App continuous-capture session

- [ ] Add fail-first app-level tests (inject fake `capture_still`, fake detector, fake camera; mirror
  `test_scan_folder` / `test_app_navigation`): a session accumulates N stills; **Complete** routes to
  `prepare_records_from_images` and loads the records into review; **Undo last** deletes the last still
  and decrements the count; **Cancel** runs no recognition; starting a session while `editing` is
  blocked; **Complete** with zero captures warns and runs no recognition.
- [ ] Implement the session in `app.py`: a "連續拍照" toolbar button (toggle), gated by
  `require_camera_support()` + a selected camera + not-`editing`; pick the output dir once; drive the
  detector from `_poll_camera_frame` (compute `FrameMetrics`, act on CAPTURE/REARMED/STALLED) only when
  a session is active; on CAPTURE run `capture_still`, apply `self._preview_rotation`, save
  `scan-capture-NNNN.png`, increment count, play shutter + flash, `mark_captured`; status/count line
  states (place form / focusing / captured-lift / waiting / too-blurry); Complete (modal `done/total`
  via `on_progress` → `prepare_records_from_images` → `_set_loaded_records`), Cancel, Undo-last.

**Quality Gate:**
- [ ] App-level session tests pass headless with injected fakes.

## Phase 4: Integration, packaging & verification

- [ ] `build/package.py`: include `assets/shutter.wav` in the PyInstaller datas so the one-file exe can
  play it; add/extend the bundle-content test if applicable.
- [ ] README continuous-capture section (next to the webcam docs); CHANGELOG `[Unreleased]` `### Added`
  entry; base OpenSpec spec (`openspec/specs/record-preparation/spec.md`) synced on archive. (No new CLI
  subcommand → CLI help unchanged.)
- [ ] `python -W error -m pytest -q` and `python -m policy_check --repo .` green; manually verify a real
  webcam continuous session (place → auto-capture → lift → repeat → Complete → batch recognize →
  review) and record the behavior/thresholds used in the PR.

**Quality Gate:**
- [ ] Full suite + policy green; `shutter.wav` present in the built bundle; manual run recorded.

## Completion Checklist

- [ ] All phases complete and quality gates green
- [ ] CHANGELOG `[Unreleased]`, README, and PR-template checklist done
- [ ] Ready for `/openspec-archive add-continuous-capture`
