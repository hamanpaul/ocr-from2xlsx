# Implementation Tasks: Handwritten name rec finetune training engine

**Change ID:** `add-name-rec-finetune`

All implementation uses TDD with focused tests before production code.

## Phase 1: Engine smoke (risk gate — must pass before later phases)

- [x] Add `training/fetch_paddleocr_train.py`: clone/update the official PaddleOCR repo at a pinned
  tag into gitignored `training/vendor/PaddleOCR/` and download PP-OCRv5_mobile_rec pretrained
  weights; idempotent re-run.
- [x] Smoke-run on Windows CPU: ~50 synthetic name crops, 1-epoch finetune via the official trainer,
  export an inference model dir, reload it with pip `paddleocr` (`text_recognition_model_dir`) and
  recognize one crop. Record single-epoch wall time.
- [x] Decision checkpoint: pipeline works -> continue; otherwise evaluate PaddleX finetune API before
  building later phases.

Smoke notes:
- Corrected `training/fetch_paddleocr_train.py` `DEFAULT_WEIGHTS_URL` to the PaddleX official
  pretrained host: `https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv5_mobile_rec_pretrained.pdparams`
  (tag and config relpath were already valid).
- Installed missing `.venv-paddle` training deps as import errors surfaced: `scikit-image`,
  `albumentations`, `lmdb`, `rapidfuzz`.
- `training.gen_names` summary for `--total 50 --seed 99`: `{"train": 40, "validation": 5, "holdout": 5}`.
- Single-epoch CPU wall time: `88.69s`.
- Export and pip-side reload both succeeded.

## Phase 2: Name corpus generator

- [x] Add fail-first tests for surname/given-char sampling coverage, seed reproducibility, rec label
  txt read/write, and path safety (no rendering in CI tests).
- [x] Implement `training/gen_names.py`: embedded common-surname and given-char pools, 2-4 char
  names, handwriting-font rendering reusing `training/fonts` + augmentation, PaddleOCR rec
  `path\tlabel` output; fixed-seed train/validation/holdout batches.

## Phase 3: Train and eval wrappers

- [x] Add fail-first tests for config assembly (paths, epochs, CPU device) and eval metrics
  (exact-match rate, char accuracy via edit distance) on synthetic prediction fixtures.
- [x] Implement `training/train_name_model.py` (thin shell over the official trainer + export) and
  `training/eval_name_model.py` (report.json / report.md).

## Phase 4: Gate, deploy, and corrections harvest

- [x] Add fail-first tests for gate decisions (exact-match up AND char accuracy not worse; reject
  keeps current model dir intact), atomic directory deploy, audit JSONL append, and
  `name_corrections.jsonl` -> rec label conversion (skip rows with missing/invalid crops).
- [x] Implement `training/retrain_name.py` (candidate vs current/baseline on fixed holdout, atomic
  runtime deploy to `~/.ocr_from2xlsx/name_rec/`, audit log) and
  `training/harvest_name_corrections.py`.

## Phase 5: Plugin integration and packaging

- [x] Add fail-first tests for `_resolve_name_rec_dir` resolution order
  (`NAME_REC_MODEL_DIR` env -> user runtime -> bundle -> None), name fill with preserved
  `name.unconfirmed`, failure fallback to current behavior, and bundle copy contents.
- [x] Update `plugins/paddleocr/main.py` and `build/build_paddle_plugin.py`.

## Phase 6: v1 production run, docs, and policy

- [x] Generate v1 corpora (train/validation/holdout, fixed seeds), finetune, gate, and commit the
  adopted model dir as bundle baseline `plugins/paddleocr/name_rec/`; record holdout exact-match and
  char-accuracy numbers vs the mobile-rec baseline.
  - **Deviation:** the adopted model was NOT committed as a bundle baseline — the exported inference
    dir is 136 MB (`inference.pdiparams` 135.88 MB), far over the plan's ~30 MB commit threshold.
    It is kept local at `plugins/paddleocr/name_rec/` (now gitignored); local plugin builds bundle
    it, fresh clones run without it (plugin falls back to current behavior). Deployment path of
    record is the runtime dir via `training.retrain_name`.
  - v1 numbers (holdout 298 names, seed 20 corpus): candidate exact-match **0.9832** /
    char-accuracy **0.9944** vs pip PP-OCRv5_mobile_rec baseline 0.8255 / 0.9145; gate adopted.
  - **Follow-up:** official PP-OCRv5_mobile_rec inference models are ~16 MB; investigate why our
    export is 136 MB (likely exporting non-mobile weights or unstripped states). If fixed below the
    threshold, commit the bundle baseline then.
- [x] Update README, CHANGELOG `[Unreleased]`, base OpenSpec specs, and pass
  `python -m policy_check`, full pytest, and `build/package.py`.

## Completion Checklist

- [x] All phases complete and quality gates green (Phase 6 bundle-baseline deviation recorded above)
- [x] Ready for `/openspec-archive add-name-rec-finetune`
