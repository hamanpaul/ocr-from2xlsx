# Proposal: Mark classifier self-training loop

**Change ID:** `add-mark-classifier-self-training`
**Created:** 2026-06-05
**Status:** Archived

---

## Problem Statement

Fixed `dark_ratio` mark detection had high precision but missed many synthetic marks, and the live
PaddleOCR plugin only probed a small subset of checkbox labels. The training workflow needed a
precision-safe, file-based loop for harvesting confirmed checkbox crops and deploying lightweight
runtime weights.

## Archived Outcome

This change was implemented as:

- plugin-safe feature extraction, model scoring, and geometry crop provider modules under
  `plugins/paddleocr/`;
- template-box export, labeled crop JSONL dataset helpers, confirmed-record harvesting, and deterministic
  stdlib model training under `training/`;
- precision-safe operating-point/eval-gate helpers, including reject-all thresholds for unsafe models;
- optional PaddleOCR plugin geometry-classifier path enabled by template/model assets, while retaining
  existing OCR-label fallback when assets are absent;
- bundle copy updates, README usage, changelog entry, tests, and base `training-data` spec updates.

The accepted behavior is captured in `openspec/specs/training-data/spec.md`.

## Scope / Impact

- Registration remains out of scope; geometry crops assume aligned images.
- Runtime plugin code remains dependency-light and can run from the plugin bundle.
- The current plugin record extraction consumes classifier output for identity/gender labels; broader
  record-field population remains a later integration step.
