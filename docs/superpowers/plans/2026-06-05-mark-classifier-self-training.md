# Mark Classifier Self-Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight checkbox mark classifier and self-training loop that improves synthetic mark recall while preserving precision and plugin runtime simplicity.

**Architecture:** Add plugin-local, dependency-light feature extraction/model/crop-provider modules that can run inside the PaddleOCR bundle without importing the main package. Add training-side tools that export template boxes, harvest labeled crops, train/export pure JSON weights, and eval-gate candidate weights before deployment. Keep registration out of scope but expose the `CropProvider` boundary for future registration work.

**Tech Stack:** Python 3.12, stdlib JSON/CSV/math/pathlib, PIL for image IO in crop/dataset tools, existing `form_layout`/`layout_render` for offline template geometry, existing pytest suites.

---

## File map

- Create `plugins/paddleocr/mark_features.py`: plugin-safe image/crop feature extraction over grayscale arrays.
- Create `plugins/paddleocr/mark_model.py`: plugin-safe JSON model loading, sigmoid scoring, thresholding, fallback to `mark_detect.is_marked`.
- Create `plugins/paddleocr/crop_provider.py`: plugin-safe `CropProvider` contract and `GeometryCropProvider` from `template_boxes.json`.
- Modify `plugins/paddleocr/main.py`: optionally use geometry crop provider + mark model when template boxes/aligned image are available; keep OCR-label fallback.
- Modify `build/build_paddle_plugin.py`: copy new plugin modules and optional baseline assets into the bundle.
- Create `training/export_template_boxes.py`: export `template_boxes.json` from `layout_render.option_mark_box`.
- Create `training/mark_dataset.py`: JSONL manifest writer/reader for labeled crop image datasets.
- Create `training/harvest_corrections.py`: convert confirmed records + image + template boxes into labeled crop dataset rows.
- Create `training/train_mark_model.py`: deterministic lightweight logistic/perceptron-style trainer, operating-point chooser, JSON weight export.
- Create `training/eval_gate.py`: pure candidate-vs-current adoption/rejection logic.
- Modify `README.md`, `CHANGELOG.md`, `openspec/specs/training-data/spec.md`; add OpenSpec archive under `openspec/changes/archive/2026-06-05-add-mark-classifier-self-training/`.

## Task 1: Feature extraction, model scoring, and eval gate

**Files:**
- Create: `plugins/paddleocr/mark_features.py`
- Create: `plugins/paddleocr/mark_model.py`
- Create: `training/eval_gate.py`
- Create: `tests/test_mark_classifier_core.py`

- [ ] **Step 1: Write failing tests**

Test `extract_features()` with empty, tick-like, dash-like, and filled crops; test `predict_proba()` against hand-calculated sigmoid; test fallback behavior when no model is loaded; test operating-point/eval-gate precision safety.

Run:

```powershell
.venv\Scripts\python -W error -m pytest -q tests\test_mark_classifier_core.py
```

Expected: FAIL because modules do not exist.

- [ ] **Step 2: Implement minimal plugin-safe code**

Implement feature names:

```python
FEATURE_NAMES = (
    "dark_ratio", "centroid_dx", "centroid_dy", "ink_w", "ink_h",
    "rows_with_ink", "cols_with_ink", "max_run", "diag_ratio", "row_transitions",
)
```

Implement `extract_features(region, grid_size=24) -> dict[str, float]`, `score_features()`, `predict_proba()`, `is_marked_by_model()`, and `decide_candidate()`.

- [ ] **Step 3: Verify green**

Run the focused test command above. Expected: PASS.

## Task 2: Template boxes and crop provider

**Files:**
- Create: `plugins/paddleocr/crop_provider.py`
- Create: `training/export_template_boxes.py`
- Create: `tests/test_mark_crop_provider.py`

- [ ] **Step 1: Write failing tests**

Test that exported boxes match `layout_render.option_mark_box`, that `GeometryCropProvider` crops every option from a generated template image, and that invalid JSON/box shape raises a clear `ValueError`.

Run:

```powershell
.venv\Scripts\python -W error -m pytest -q tests\test_mark_crop_provider.py
```

Expected: FAIL because modules do not exist.

- [ ] **Step 2: Implement minimal code**

Export JSON shape:

```json
{"template_id": "service_record.v1", "boxes": [{"field": "...", "code": "...", "box": [x0, y0, x1, y1]}]}
```

Implement plugin-safe crop provider returning `{(field, code): region}` where `region` is a 2D grayscale list.

- [ ] **Step 3: Verify green**

Run the focused test command above. Expected: PASS.

## Task 3: Dataset harvesting

**Files:**
- Create: `training/mark_dataset.py`
- Create: `training/harvest_corrections.py`
- Create: `tests/test_mark_dataset_harvest.py`

- [ ] **Step 1: Write failing tests**

Test JSONL append/read round-trip, deterministic crop filenames, label derivation from confirmed `Record` values, and one row per template box.

Run:

```powershell
.venv-paddle\Scripts\python -W error -m pytest -q tests\test_mark_dataset_harvest.py
```

Expected: FAIL because modules do not exist.

- [ ] **Step 2: Implement minimal code**

Manifest rows contain `crop`, `label`, `field`, `code`, `source`, `provider`, `record_id`, and `created_at`.

- [ ] **Step 3: Verify green**

Run the focused test command above. Expected: PASS.

## Task 4: Training, operating point, and synthetic smoke

**Files:**
- Create: `training/train_mark_model.py`
- Create: `tests/test_train_mark_model.py`
- Modify: `training/eval_marks.py` only if needed to accept model-backed detector injection.

- [ ] **Step 1: Write failing tests**

Test deterministic train/export on tiny separable feature rows, operating-point threshold selection, and exported JSON schema.

Run:

```powershell
.venv\Scripts\python -W error -m pytest -q tests\test_train_mark_model.py tests\test_mark_classifier_core.py
```

Expected: FAIL because trainer does not exist.

- [ ] **Step 2: Implement minimal trainer**

Use a deterministic lightweight linear classifier implemented with stdlib math (no sklearn dependency) and export pure JSON weights. Select threshold by highest recall among thresholds satisfying `precision >= min_precision`; if none satisfy, choose threshold above max score to reject all marks.

- [ ] **Step 3: Verify green**

Run focused tests. Expected: PASS.

## Task 5: Plugin integration and packaging

**Files:**
- Modify: `plugins/paddleocr/main.py`
- Modify: `build/build_paddle_plugin.py`
- Create: `tests/test_paddle_mark_model_integration.py`

- [ ] **Step 1: Write failing tests**

Test `main.run()` can receive a geometry mark function that returns classifier labels for all options, and that `build_paddle_plugin.py` copies `mark_features.py`, `mark_model.py`, and `crop_provider.py`.

Run:

```powershell
.venv\Scripts\python -W error -m pytest -q tests\test_paddle_mark_model_integration.py tests\test_build_paddle_plugin.py
```

Expected: FAIL until integration and copy list are updated.

- [ ] **Step 2: Implement minimal integration**

Add plugin helper that loads template boxes and model weights from env/runtime/bundle paths, classifies aligned images when assets exist, and otherwise preserves `detect_marked_labels` fallback.

- [ ] **Step 3: Verify green**

Run focused tests. Expected: PASS.

## Task 6: Documentation, OpenSpec archive, final verification

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `openspec/specs/training-data/spec.md`
- Create: `openspec/changes/archive/2026-06-05-add-mark-classifier-self-training/*`

- [ ] **Step 1: Update docs**

Document template box export, dataset harvesting, training, eval-gate, runtime model resolution, and fallback behavior.

- [ ] **Step 2: Archive OpenSpec change**

Add archived README/proposal/tasks/delta matching the implemented behavior.

- [ ] **Step 3: Final verification**

Run:

```powershell
.venv\Scripts\python -W error -m pytest -q
.venv\Scripts\python build\package.py
python -m policy_check --repo .
.venv-paddle\Scripts\python -W error -m pytest -q tests\test_mark_dataset_harvest.py tests\test_training_eval_marks.py
```

Expected: all pass.

## Self-review notes

- The spec mentions sklearn as an offline option, but this plan deliberately uses a deterministic stdlib linear trainer to avoid adding a new repo dependency while still exporting pure JSON weights.
- Registration remains out of scope; `CropProvider` is the extension boundary.
- The plugin keeps the existing OCR-label fallback for non-aligned images and no-model cases.
