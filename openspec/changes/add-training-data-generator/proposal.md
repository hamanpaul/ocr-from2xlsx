# Proposal: Handwriting training-data generator

**Change ID:** `add-training-data-generator`
**Created:** 2026-05-31
**Status:** Draft

---

## Problem Statement

Measuring and improving OCR (especially checkbox-mark recognition) needs a labeled corpus of form images,
but only one real sample exists — too few to compute accuracy or train. There is no way to generate
service-record images with known ground truth aligned to the workflow JSON.

## Proposed Solution

Add a standalone `training/` tool that synthesizes service-record images from the blank form (via the shared
`form_layout` model) and emits a workflow-format **answer key**:

- **Layout reconstruction**: compute each option/field's pixel box from `form_layout` cells + the blank
  xlsx geometry, and draw a blank base form — positions are exact by construction (precise ground truth).
- **Handwriting synthesis**: render text fields (name / medical-record-no / date) with OFL handwriting CJK
  fonts (multiple styles) plus jitter/rotation; synthesize checkbox marks procedurally (✓, dash, partial
  blackout) in varied styles. A `fetch_fonts.py` setup script downloads OFL fonts (Traditional-Chinese
  covering) into a gitignored `training/fonts/`; generation itself is offline and falls back to system
  printed fonts when no handwriting font is present.
- **Sampler**: per image select 10–50% of the form's options to mark (≥1), with single-choice ≤1 and
  multi-choice random subsets; across the batch ensure every option is marked ≥5 times (coverage-driven).
- **Answer key**: turn the selected codes into a valid `Record` by reusing `confirm_form.apply_form_state`
  + `record_access`, emit a `service_record.v1` `Batch` where each record adds `training: true` and
  `source_image`, so the answer key aligns field-by-field with OCR output.

Runs under `.venv-paddle` (PIL+numpy); not part of the shipped package; adds no main-package dependency.

## Scope

### In Scope
- `training/` tool: font fetch, layout reconstruction (geometry + base image), handwriting + mark synthesis,
  coverage-driven sampler, answer-key assembler, generator orchestration.
- Checkbox marks in varied styles (✓ / dash / partial blackout); per-image 10–50% / ≥1; per-option ≥5 across the batch.
- Answer key in `service_record.v1` format + `training` + `source_image`, built via the existing pure helpers.

### Out of Scope
- Training/fine-tuning any model (this produces only the labeled dataset).
- Perfect scan realism (basic augmentation only).
- Changing `form_layout` / `Record` / workflow / shipped package.
- Fonts beyond OFL/open license; bundling fonts into the repo (fetched locally, gitignored).

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| New `training/` tool | Yes | Standalone generator; runs under `.venv-paddle`. |
| `.gitignore` | Yes | Ignore `training/fonts/` and `training/out/`. |
| `form_layout` / `confirm_form` / `record_access` | No | Reused. |
| shipped package / workbook / `ocr_plugin.v1` | No | Unchanged. |

## Architecture Considerations

Pure, testable logic (sampler, answer-key assembler, layout geometry) is separated from PIL image drawing so
it is unit-tested without rendering. The answer key is built through `confirm_form`/`record_access`, so it is
guaranteed to share the workflow Record schema and align with OCR output. Image generation and fonts live in
the dev-only `.venv-paddle`, keeping the shipped package dependency-light.

## Success Criteria

- [ ] `fetch_fonts.py` downloads OFL handwriting fonts locally (sources/licenses recorded); generator falls back to system fonts when absent.
- [ ] Generator outputs synthetic form PNGs and a `service_record.v1` answer key (with `training`/`source_image`).
- [ ] Marks cover ✓/dash/blackout styles; per-option ≥5 across the batch; per-image 10–50%, ≥1; single/multi constraints respected.
- [ ] Answer key is built via `confirm_form` and aligns field-by-field with OCR output.
- [ ] Sampler / answer-key / geometry have pure unit tests; image generation has a smoke test; existing tests and policy stay green.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Downloaded fonts miss Traditional-Chinese glyphs | Med | Med | Pick TC-covering OFL fonts; check glyph drawability, fall back to system fonts on missing glyphs |
| Reconstructed base differs from real scans → limited transfer | Med | Med | Primary value is checkbox marks (synthesizable); offer augmentation; names still gated by human confirmation |
| Font licensing | Low | High | OFL/open only; record sources + licenses in `fonts/` |
| Large fonts bloat the repo | Low | Med | `training/fonts/` gitignored; fetched by setup script |
| Coverage can't reach ≥5 for rare single-choice options | Med | Med | Coverage-driven: bias selection toward under-covered options until all reach ≥5 |
