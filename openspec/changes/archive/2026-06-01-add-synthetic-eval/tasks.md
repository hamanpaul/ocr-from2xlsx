# Implementation Tasks: Synthetic evaluation tools

**Change ID:** `add-synthetic-eval`

All implementation used TDD with focused tests before production code.

## Phase 1: Pure metrics

- [x] Add fail-first tests for P/R/F1, stable set comparison, mark-set comparison, and layout-driven
  record comparison.
- [x] Implement `training/eval_metrics.py`.

## Phase 2: Mark-blinded evaluator

- [x] Add fail-first tests for answer-key source-image resolution and mark report shape.
- [x] Implement `training/eval_marks.py`, using workbook geometry and `mark_detect.is_marked`.

## Phase 3: Pipeline diagnostic evaluator

- [x] Add fail-first tests with a fake OCR backend and import-safe CLI module behavior.
- [x] Implement `training/eval_pipeline.py`, invoking `PluginOcrBackend` only from the CLI path.

## Phase 4: Docs and policy

- [x] Update README usage and CHANGELOG.
- [x] Update and archive OpenSpec documentation.
