# Implementation Tasks: Mark classifier self-training loop

**Change ID:** `add-mark-classifier-self-training`

All implementation used TDD with focused tests before production code.

## Phase 1: Feature/model/gate core

- [x] Add fail-first tests for mark features, JSON model scoring/fallback, operating-point selection, and
  eval-gate adoption safety.
- [x] Implement `plugins/paddleocr/mark_features.py`, `plugins/paddleocr/mark_model.py`, and
  `training/eval_gate.py`.

## Phase 2: Template boxes and crop provider

- [x] Add fail-first tests for template-box export, geometry crop provider, import safety, and invalid
  template validation.
- [x] Implement `training/export_template_boxes.py` and `plugins/paddleocr/crop_provider.py`.

## Phase 3: Dataset harvest

- [x] Add fail-first tests for JSONL manifest validation, crop PNG writing, confirmed-record label
  derivation, and partial-write prevention.
- [x] Implement `training/mark_dataset.py` and `training/harvest_corrections.py`.

## Phase 4: Training/export

- [x] Add fail-first tests for deterministic training, threshold selection, reject-all thresholds,
  model export/load, manifest crop loading, and CLI export.
- [x] Implement `training/train_mark_model.py`.

## Phase 5: Plugin integration and packaging

- [x] Add fail-first tests for classifier label mapping, run injection, fallback behavior, and bundle
  copy contents.
- [x] Update `plugins/paddleocr/main.py` and `build/build_paddle_plugin.py`.

## Phase 6: Docs and policy

- [x] Update README, CHANGELOG, base OpenSpec, and archive docs.
