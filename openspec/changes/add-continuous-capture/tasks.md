# Implementation Tasks: Continuous hands-free webcam auto-capture

**Change ID:** `add-continuous-capture`

> Reflects the 2026-06-24 detection redesign (baseline-diff). The first implementation already landed on
> the branch (autocapture.py, scan on_progress, shutter asset, app session/wiring/finish, docs); these
> tasks **rework** detection to baseline-diff and fold in the adversarial-review fixes. TDD throughout;
> the detector stays camera-free and OpenCV-free for unit tests.

## Phase 1: Detector rework — empty-desk baseline + central ROI (pure)

- [ ] Fail-first tests (no cv2) for the reworked `autocapture`: `FrameMetrics(motion, diff_from_baseline,
  sharpness)`; states NEED_BASELINE → ARMED → DISARMED → ARMED and PAUSED; no capture before
  `set_baseline`; CAPTURE when `diff_from_baseline ≥ present_thresh` + stationary + `abs(Δsharpness) ≤
  settle_tol` for `stable_frames`; re-arm when `diff_from_baseline ≤ clear_thresh` (< present_thresh) for
  `clear_frames`; **regression: a 2nd near-identical form (high diff vs empty baseline) IS captured after
  a clear-cycle**; repeated `note_failed_capture` → PAUSED and observe stops capturing; `abs()`
  convergence (a falling sharpness is not "settled"); env overrides incl. `roi_fraction`.
- [ ] Rework `src/ocr_from2xlsx/autocapture.py`: replace `change_from_ref` with `diff_from_baseline`;
  add NEED_BASELINE/PAUSED + `set_baseline`; central-ROI metric helper (`to_metric_gray` honoring an ROI
  fraction) + `mean_abs_diff`; `present_thresh`/`clear_thresh`/`settle_tol`/`roi_fraction` defaults +
  `AUTOCAPTURE_*` env.

**Quality Gate:** state-machine + ROI/metric tests pass with no camera and no OpenCV.

## Phase 2: App detection wiring — baseline capture + reset

- [ ] Fail-first app tests (bare `ReviewApp.__new__`, fakes): starting a session prompts to clear desk
  and sets the detector baseline; "reset baseline" re-captures; `_observe` computes `diff_from_baseline`
  (vs baseline ROI) and `motion` (vs prev ROI) and drives the detector; no `ref_gray` remains.
- [ ] Implement in `app.py`: baseline capture on start (clear-desk prompt → central-ROI gray →
  `set_baseline`), "重設空桌基準" button, reworked `_observe_autocapture_frame`; remove ref_gray
  management.

**Quality Gate:** app detection tests pass headless.

## Phase 3: App robustness — CJK write, pause, data recovery, completion dialog

- [ ] Fail-first tests: still saves to a **non-ASCII (CJK) output dir** (assert file exists); repeated
  full-res blur pauses the session (no further capture / no loop); camera lost mid-session keeps stills
  and `完成辨識` still recognizes them; recognition error preserves stills and is retryable; completion
  shows a "辨識完成" dialog before review.
- [ ] Implement: `_imwrite_unicode` (`cv2.imencode` + `Path.write_bytes`) in `_perform_autocapture`
  (continuous path only); STALLED → pause session + guidance; `_finish` works whenever stills exist
  (camera-loss) and preserves stills on error (retry); add the "辨識完成" messagebox before
  `_set_loaded_records`.

**Quality Gate:** robustness tests pass; no regression in existing app tests.

## Phase 4: Integration, docs & verification

- [ ] CHANGELOG `[Unreleased]` updated for the redesign; README continuous-capture note adjusted to the
  baseline workflow ("先擷取空桌基準"); base OpenSpec spec synced on archive.
- [ ] `python -W error -m pytest -q` and `python -m policy_check --repo .` green.
- [ ] Adversarial review re-run focused on detection (must include the same-template-stack regression);
  manual real-camera verify (clear desk → baseline → place/lift a few same-template forms → Complete →
  recognition-complete dialog → review), recording thresholds used.

**Quality Gate:** full suite + policy green; adversarial pass clean; manual run recorded.

## Completion Checklist

- [ ] All phases complete and quality gates green
- [ ] CHANGELOG `[Unreleased]`, README, PR-template checklist done
- [ ] Ready for `/openspec-archive add-continuous-capture`
