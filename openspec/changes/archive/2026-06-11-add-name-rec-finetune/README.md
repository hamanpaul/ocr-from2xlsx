# Proposal: Handwritten name rec finetune training engine

**Change ID:** `add-name-rec-finetune`
**Created:** 2026-06-11
**Status:** Archived

---

## Problem Statement

Handwritten Chinese names were the weakest recognition path: the mobile full-page recognizer misses
real handwriting, and the only "learning" was roster fuzzy matching over confirmed corrections — the
underlying OCR never improved. The project needed a repeatable, CPU-only training engine so the name
recognizer itself can be bootstrapped from synthetic data and strengthened from confirmed
corrections.

## Archived Outcome

This change was implemented as:

- a pinned-tag vendored PaddleOCR trainer fetch (`training.fetch_paddleocr_train`, corrected weights
  URL recorded in tasks notes) with single-epoch CPU smoke verified (88.69s/epoch);
- a synthetic name corpus generator (`training.gen_names`): surname × given-char pools, handwriting
  fonts + augmentation, OOV-dict filtering, disjoint fixed-seed train/validation/holdout batches;
- finetune/export wrapper (`training.train_name_model`), holdout evaluation
  (`training.eval_name_model`: exact-match + char accuracy), and gated atomic deploy with audit
  JSONL (`training.retrain_name`);
- corrections harvest (`training.harvest_name_corrections`) converting confirmed
  `name_corrections.jsonl` rows into rec label format;
- plugin name-model resolution (`NAME_REC_MODEL_DIR` → user runtime `name_rec/` → bundle) filling
  `record.name` as an unconfirmed suggestion with full fallback to prior behavior, plus bundle copy
  support in `build/build_paddle_plugin.py`.

v1 holdout results (298 names, seed-20 corpus): exact-match **0.9832** / char accuracy **0.9944**
vs pip PP-OCRv5_mobile_rec baseline 0.8255 / 0.9145; gate adopted.

**Deviation:** the adopted v1 model was NOT committed as a bundle baseline — the exported inference
dir is ~136 MB (official mobile rec inference models are ~16 MB), far over the ~30 MB commit
threshold. It is kept local under gitignored `plugins/paddleocr/name_rec/`; the runtime-dir deploy
via `training.retrain_name` is the deployment path of record. Follow-up: investigate the oversized
export and commit the baseline if it shrinks below the threshold.

The accepted behavior is captured in `openspec/specs/training-data/spec.md` and
`openspec/specs/record-preparation/spec.md`.

## Scope / Impact

- Open-set recognition (official dict retained); CPU-only training accepted by design.
- Names remain suggestions: `name.unconfirmed` until human confirmation; agent/roster unchanged.
- Detection training, GPU support, and confirm-flow auto-triggering remain out of scope.

Design: `docs/superpowers/specs/2026-06-11-name-rec-finetune-design.md`.
Plan: `docs/superpowers/plans/2026-06-11-name-rec-finetune.md`.
