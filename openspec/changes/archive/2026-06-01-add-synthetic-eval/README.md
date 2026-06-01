# Proposal: Synthetic evaluation tools

**Change ID:** `add-synthetic-eval`
**Created:** 2026-06-01
**Status:** Archived

---

## Problem Statement

The synthetic training generator can produce labeled images and `answers.json`, but there was no
repeatable way to quantify whether checkbox mark detection or the full OCR pipeline matches that
ground truth.

## Archived Outcome

This change was implemented as:

- pure metric helpers in `training/eval_metrics.py` for P/R/F1, set comparison, mark comparison, and
  layout-driven record comparison;
- `python -m training.eval_marks` for mark-blinded checkbox evaluation using generated answer keys,
  workbook geometry, and `plugins.paddleocr.mark_detect.is_marked` without invoking OCR;
- `python -m training.eval_pipeline` for diagnostic full-pipeline evaluation through an explicit OCR
  plugin directory;
- JSON and Markdown report outputs for both evaluators;
- tests, README usage, changelog entry, and base `training-data` spec updates.

The accepted behavior is captured in the base `openspec/specs/training-data/spec.md`.

## Scope / Impact

- Affects only the dev-only `training/` workflow.
- Keeps report generation deterministic and file-based.
- Does not run PaddleOCR in normal tests; real OCR execution stays explicit through CLI options.
