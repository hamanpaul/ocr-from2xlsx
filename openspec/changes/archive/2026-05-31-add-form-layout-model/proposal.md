# Proposal: Shared form-layout model

**Change ID:** `add-form-layout-model`
**Created:** 2026-05-31
**Status:** Archived

---

## Problem Statement

Two independent upcoming sub-projects — (A) a single-page form-mirroring confirmation UI and (B) a
synthetic handwriting training-data generator — both need a structured description of the service-record
form (sections, fields, options, codes, cell references). Without a shared model each would hard-code the
form structure and they would drift apart and from the real form. There is currently no single source that
maps every form option to a canonical code and to its position in the workflow `service_record.v1` Record.

## Archived Outcome

This change was implemented as:

- a new pure-stdlib `src/ocr_from2xlsx/form_layout.py` module with immutable `Option`, `Field`, `Section`,
  and `FormLayout` dataclasses plus accessor helpers and invariant checks;
- a hand-curated `service_record_layout()` covering the whole `服務紀錄表` form with canonical codes reused
  from `constants.py` and `record_path` mappings into the workflow `service_record.v1` Record;
- workbook-backed tests that validate exact section/field order, canonical labels/codes, selected-code
  normalization, two-way sheet coverage against the real blank workbook, and `record_path` legality.

The accepted behavior is captured in the base `openspec/specs/form-layout/spec.md`.

## Scope

### In Scope
- `form_layout.py` dataclasses + `service_record_layout()` covering the whole form (sections A/B/C + top).
- `record_path` for every field (or `null` when the form field has no Record counterpart, e.g. 診斷日).
- Reuse of existing `constants.py` codes; no parallel code set.
- A validation test asserting model↔sheet two-way coverage and code/record_path legality.

### Out of Scope
- Geometry/pixel coordinates (B owns cell→pixel rendering; A owns UI layout).
- The confirmation UI (sub-project A) and the training generator / answer-key emitter (sub-project B).
- Replacing `form_template.py` (page-size check) or `constants.py`.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| New module `form_layout.py` | Yes | Dataclasses + `service_record_layout()`; pure stdlib. |
| `constants.py` | No | Reused for codes; unchanged. |
| `form_template.py` | No | Unchanged (page-size for preprocess). |
| Workflow Record schema | No | Model references it via `record_path`; no schema change. |
| Tests | Yes | Accessor unit tests + sheet two-way-coverage validation (openpyxl). |

## Architecture Considerations

Pure stdlib, render-agnostic. The model is the single shared dependency for sub-projects A and B; `record_path`
ties it to `service_record.v1` so B can assemble valid Records from marked options and evaluation can compare
the answer key (workflow-format JSON + `training` + `source_image`) against OCR output field-by-field.

## Success Criteria

- [x] `form_layout.py` provides the dataclasses and `service_record_layout()`, reusing constants codes.
- [x] Every field has a `record_path` (or `null`) matching the `service_record.v1` Record.
- [x] The model↔sheet two-way coverage test passes (consistent labels, no missing `□` options).
- [x] A and B can import the model instead of hard-coding the form.
- [x] Existing tests and policy stay green.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Sheet label vs constants label mismatch binds the wrong code | Med | High | Validation test compares each cell; codes curated + legality-checked |
| Form layout changes later | Low | Med | Two-way coverage test detects drift |
| `record_path` drifts from the Record schema | Med | High | Test validates every non-null `record_path` against the Record fields |
