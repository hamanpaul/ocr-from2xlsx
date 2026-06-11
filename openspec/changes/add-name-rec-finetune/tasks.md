# Implementation Tasks: Handwritten name rec finetune training engine

**Change ID:** `add-name-rec-finetune`

All implementation uses TDD with focused tests before production code.

## Phase 1: Engine smoke (risk gate — must pass before later phases)

- [ ] Add `training/fetch_paddleocr_train.py`: clone/update the official PaddleOCR repo at a pinned
  tag into gitignored `training/vendor/PaddleOCR/` and download PP-OCRv5_mobile_rec pretrained
  weights; idempotent re-run.
- [ ] Smoke-run on Windows CPU: ~50 synthetic name crops, 1-epoch finetune via the official trainer,
  export an inference model dir, reload it with pip `paddleocr` (`text_recognition_model_dir`) and
  recognize one crop. Record single-epoch wall time.
- [ ] Decision checkpoint: pipeline works -> continue; otherwise evaluate PaddleX finetune API before
  building later phases.

## Phase 2: Name corpus generator

- [ ] Add fail-first tests for surname/given-char sampling coverage, seed reproducibility, rec label
  txt read/write, and path safety (no rendering in CI tests).
- [ ] Implement `training/gen_names.py`: embedded common-surname and given-char pools, 2-4 char
  names, handwriting-font rendering reusing `training/fonts` + augmentation, PaddleOCR rec
  `path\tlabel` output; fixed-seed train/validation/holdout batches.

## Phase 3: Train and eval wrappers

- [ ] Add fail-first tests for config assembly (paths, epochs, CPU device) and eval metrics
  (exact-match rate, char accuracy via edit distance) on synthetic prediction fixtures.
- [ ] Implement `training/train_name_model.py` (thin shell over the official trainer + export) and
  `training/eval_name_model.py` (report.json / report.md).

## Phase 4: Gate, deploy, and corrections harvest

- [ ] Add fail-first tests for gate decisions (exact-match up AND char accuracy not worse; reject
  keeps current model dir intact), atomic directory deploy, audit JSONL append, and
  `name_corrections.jsonl` -> rec label conversion (skip rows with missing/invalid crops).
- [ ] Implement `training/retrain_name.py` (candidate vs current/baseline on fixed holdout, atomic
  runtime deploy to `~/.ocr_from2xlsx/name_rec/`, audit log) and
  `training/harvest_name_corrections.py`.

## Phase 5: Plugin integration and packaging

- [ ] Add fail-first tests for `_resolve_name_rec_dir` resolution order
  (`NAME_REC_MODEL_DIR` env -> user runtime -> bundle -> None), name fill with preserved
  `name.unconfirmed`, failure fallback to current behavior, and bundle copy contents.
- [ ] Update `plugins/paddleocr/main.py` and `build/build_paddle_plugin.py`.

## Phase 6: v1 production run, docs, and policy

- [ ] Generate v1 corpora (train/validation/holdout, fixed seeds), finetune, gate, and commit the
  adopted model dir as bundle baseline `plugins/paddleocr/name_rec/`; record holdout exact-match and
  char-accuracy numbers vs the mobile-rec baseline.
- [ ] Update README, CHANGELOG `[Unreleased]`, base OpenSpec specs, and pass
  `python -m policy_check`, full pytest, and `build/package.py`.

## Completion Checklist

- [ ] All phases complete and quality gates green
- [ ] Ready for `/openspec-archive add-name-rec-finetune`
