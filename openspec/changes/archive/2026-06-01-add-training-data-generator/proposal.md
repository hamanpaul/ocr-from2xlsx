# Proposal: Handwriting training-data generator

**Change ID:** `add-training-data-generator`
**Created:** 2026-05-31
**Status:** Archived

---

## Problem Statement

Measuring and improving OCR (especially checkbox-mark recognition) needs a labeled corpus of form images,
but only one real sample exists — too few to compute accuracy or train. There is no way to generate
service-record images with known ground truth aligned to the workflow JSON.

## Archived Outcome

This change was implemented as:

- a new repo-local `training/` toolchain (`sampler.py`, `answer_key.py`, `layout_render.py`,
  `handwriting.py`, `fetch_fonts.py`, `generate.py`) for synthetic service-record generation;
- coverage-driven sampling keyed by `(field_key, code)` so repeated raw option codes across different
  fields do not collapse coverage;
- workflow-aligned answer-key assembly via the shared form helpers, producing `service_record.v1`
  records with `training` and `source_image`;
- workbook-geometry-based base-form rendering, varied tick/dash/blackout marks, and bbox-safe text
  placement that keeps rendered ink inside its target box even for tight cells;
- offline font setup plus glyph-aware CJK fallback to Windows system fonts, and repo-local
  `python -m training.generate` execution from the repository root;
- documentation, changelog, ignore rules, smoke tests, and repository verification updates.

The accepted behavior is captured in the base `openspec/specs/training-data/spec.md`.

## Scope / Impact

- Affects only the dev-only `training/` workflow; the shipped package, workbook schema, and OCR workflow
  remain unchanged.
- Reuses the shared `form_layout` and `confirm_form` helpers so the synthetic answer key matches the
  review/import workflow.
- Keeps pure logic testable under `.venv`; rendering and smoke flows run under `.venv-paddle`.

## Architecture Notes

Pure, testable logic (sampler, answer-key assembler, workbook geometry) is separated from PIL rendering.
The generator reconstructs positions from the workbook geometry and `form_layout`, so checkbox/text
ground truth stays aligned with the workflow schema without adding runtime dependencies to the shipped
application.
