# Synthetic eval implementation plan

Implement the approved synthetic-eval design in `docs/superpowers/specs/2026-06-01-synthetic-eval-design.md`.

## Scope

- Add pure metrics for set precision/recall/F1, mark-set comparison, and layout-driven record comparison.
- Add mark-blinded synthetic evaluation that reads generator `answers.json`, reuses workbook geometry, runs `mark_detect.is_marked` over known checkbox boxes, and writes `report.json` plus `report.md`.
- Add diagnostic end-to-end pipeline evaluation that invokes `PluginOcrBackend` for generated images, compares predicted records with gold records, and labels the report as synthetic-diagnostic.
- Add CLI entrypoints via `python -m training.eval_marks` and `python -m training.eval_pipeline`.
- Update docs, changelog, and OpenSpec after implementation.

## Task 1: Pure metrics

Tests first:
- `prf()` returns `(0, 0, 0)` for zero denominators and correct fractions otherwise.
- `compare_sets()` returns stable TP/FP/FN sets.
- `compare_mark_sets()` reports aggregate and per-field metrics for `(field_key, code)` pairs.
- `compare_records()` skips fields with `record_path=None`, exact-matches scalar fields, and micro-averages multi-choice sets.

Implementation:
- Create `training/eval_metrics.py`.
- Use `FormLayout.iter_fields()` and `record_access.get_by_path()`.
- Return JSON-serializable dictionaries with counts and ratios.

## Task 2: Mark-blinded evaluator

Tests first:
- Generate a tiny synthetic answer batch and confirm mark evaluation emits a report with sample count, aggregate mark metrics, per-field metrics, and no OCR dependency.
- Unit-test source image path resolution relative to the answer-key directory.

Implementation:
- Create `training/eval_marks.py`.
- Load answers with `json_io.load_batch()`.
- For every choice option, crop the known `layout_render.option_mark_box()` region from the source image and classify it via `plugins.paddleocr.mark_detect.is_marked()`.
- Derive gold marked sets from the record and layout.
- Write `report.json` and `report.md` under a requested output directory.

## Task 3: End-to-end pipeline evaluator

Tests first:
- Use a fake backend to compare one gold answer record with one predicted record and confirm diagnostic report shape and mismatch details.
- Confirm CLI path can be imported without requiring a plugin bundle.

Implementation:
- Create `training/eval_pipeline.py`.
- Build `PreparedPage` for each generated image and call `PluginOcrBackend.extract()`.
- Convert returned record payloads to `Record`, compare with `compare_records()`, and write report files.
- Keep plugin execution explicit via `--ocr-plugin-dir` so CI does not run PaddleOCR accidentally.

## Task 4: Documentation, OpenSpec, review, PR

- Add README usage under Training data generator.
- Update `CHANGELOG.md [Unreleased]`.
- Add or archive OpenSpec entries for synthetic evaluation.
- Run focused tests, full tests, package build, and policy check.
- Request code review, address issues, commit, push, open PR against `feature/bootstrap-ocr-design`, and wait for PR checks.
