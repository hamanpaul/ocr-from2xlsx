# Implementation Tasks: Form registration + full-checkbox extraction

**Change ID:** `add-form-registration`

All implementation uses TDD with focused tests before production code.

## Phase 0: Registration precision smoke (risk gate — must pass before later phases)

- [ ] Render the blank service-record form to the canonical coordinate space that `template_boxes.json`
  uses (reuse the training generator's base render); confirm size/coords match the boxes.
- [ ] On a high-res real capture: auto-register to the canonical reference, overlay the 125 boxes on
  the registered image, and eyeball that boxes land on the actual checkboxes; measure the
  post-registration mark hit rate vs unregistered.
- [ ] Decision checkpoint: precision sufficient (boxes aligned, mark hit rate clearly better than
  unregistered) → continue. Otherwise revisit (higher capture resolution, feature/matcher strategy,
  or lead with manual 4-corner) before building Phase 2+.

## Phase 1: Registration core (pure CV)

- [ ] Add fail-first tests (cv2 via `pytest.importorskip`): `register_to_template` recovers a known
  homography from injected fixed correspondences and sets `confident`; too-few inliers →
  `needs_manual`; `four_point_warp` maps known corners to the canonical rectangle.
- [ ] Implement `plugins/paddleocr/registration.py`: `register_to_template(image, reference,
  *, min_inliers)` (ORB + BFMatcher + `findHomography(RANSAC)` → `RegistrationResult` with
  `warped`/`homography`/`inliers`/`needs_manual`) and `four_point_warp(image, corners, size)`.

## Phase 2: Full-form checkbox → record mapping

- [ ] Add fail-first tests for mapping a set of marked `(field, code)` labels through the full
  `form_layout` into `service_record.v1`: single-choice at most one, multi-choice subset, unselected
  fields stay empty; mirror the training generator's `selection_to_record` constraints.
- [ ] Extend `plugins/paddleocr/field_extract.py` `extract_fields` to map ALL classified boxes (not
  only identity/gender) into the record.

## Phase 3: Plugin + app integration

- [ ] Add fail-first tests for the plugin scan path registering before geometry crops, and for the
  `needs_manual` signal surfacing; safe fallback (no assets / cv2 absent / registration error) keeps
  the current behavior.
- [ ] Wire registration into `plugins/paddleocr/main.py`; in `src/ocr_from2xlsx/app.py`, on
  `needs_manual` prompt a manual 4-corner pick on the preview and re-run, then fill the full form
  (names stay `name.unconfirmed`).

## Phase 4: Mark-accuracy measurement + docs

- [ ] Measure post-registration mark accuracy on real captures (per-box marked/unmarked); if below
  target, harvest real checkbox crops (`training/harvest_corrections`) and retrain via
  `training/retrain` (eval-gate) — record the decision, do not force a metric.
- [ ] README, CHANGELOG `[Unreleased]`, base OpenSpec specs synced; `python -W error -m pytest -q`,
  `python -m policy_check --repo .` green; manual real-capture → full-form recognition recorded in PR.

## Completion Checklist

- [ ] All phases complete and quality gates green (Phase 0/4 outcomes recorded)
- [ ] Ready for `/openspec-archive add-form-registration`
