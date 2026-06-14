# Proposal: Fix core field recognition (identity / gender / name / medical-record-no)

**Change ID:** `fix-core-field-recognition`
**Created:** 2026-05-30
**Status:** Superseded by `replace-recognition-with-local-vlm` (2026-06-14)

> The text-anchor + ink-probe hybrid below was empirically found too brittle on real
> document-camera captures (checkbox marks do not reliably leak into the OCR text layer, and
> geometric registration cannot reach 6px box precision). Recognition is replaced by a
> fully-local Vision-LLM pre-fill — see `replace-recognition-with-local-vlm`. This change will
> NOT be implemented or archived.

---

## Problem Statement

The PaddleOCR plugin reads the service-record form well at the text layer, but the
normalized record is almost empty: only `service_date` is extracted. Cross-checking the real
filled reference form (`tests/fixtures/pdf/for testing only.pdf`) against the OCR output showed:

- The form **is fully filled** (✓病人, ✓女性, ✓本國籍, ✓門診, ✓10.肝癌, handwritten 姓名「葉心安」/病歷號「6250712919」, 年齡「29」…), yet the pipeline produced `identity=""`, `gender=""`, `name=None`, `medical_record_no=None`.
- The OCR text layer **did capture** much of this (e.g. `病人62507…`, `中女性`, `本國籍`), but `field_extract` only parsed the date, used a naive name/MRN anchor that grabbed stray marks (returned `"V"`), and performed **no checkbox/mark detection**.
- Because required fields were missing, validation **blocked** the record, so nothing reached the workbook and the (incorrect) result was invisible.

Affected: anyone relying on the OCR→JSON→XLSX flow to capture real form content. Current pain: the
recognized content is wrong/empty and silently blocked.

## Proposed Solution

Recognize the four core fields the form actually carries, using a **text-anchor + ink-probe hybrid**,
and make recognition results **verifiable (non-blocking)**:

- **Checkbox fields (identity, gender):** locate each option label via the OCR line bounding box, then
  measure ink density in the checkbox region to the left of the label to decide marked/unmarked. Use the
  OCR text anomaly (a checked box often loses its `□` glyph or reads the tick as `中/V`) as a secondary
  signal. Coordinates are derived from runtime OCR positions, not hard-coded, so the approach tolerates
  future webcam capture.
- **Handwritten fields (name, medical-record-no):** parse the handwriting on the 姓名/病歷號 anchor row —
  a CJK run is the name, a long digit run is the medical-record-no.
- **Non-blocking verification output:** allow recognized fields to be written out even when some required
  fields are missing, recording the gaps as warnings rather than blockers, so results can be checked
  against the image instead of being hidden.

## Scope

### In Scope
- Recognize `identity` (病人/親友及照顧者/一般民眾及其他) and `gender` (女性/男性/其他) via mark detection.
- Recognize handwritten `name` and `medical_record_no` from the 姓名/病歷號 region.
- A non-blocking / "allow incomplete" path so recognized values are emitted for verification.
- A ground-truth fixture for the reference form and a real-OCR regression check.

### Out of Scope
- Patient-only fields (國籍/年齡/管道/疾病狀態/來源/癌別) and Section A consultation/supply/referral
  checkboxes — deferred to a later change.
- Full form-corner registration / perspective de-warp (handled later if webcam distortion demands it).
- Changing the workbook writer or the `ocr_plugin.v1` contract shape.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| OCR plugin (`plugins/paddleocr/`) | Yes | New `mark_detect` (image ink-probe) + improved `field_extract` name/MRN parse; `run()` composes both. |
| Pure logic / tests | Yes | New pure functions (mark scoring, name/MRN parse) unit-tested without paddle. |
| Validation / import | Yes | Add a non-blocking verification path so incomplete-but-recognized records are emitted. |
| `ocr_plugin.v1` contract | No | Record shape unchanged; only more fields populated. |
| Workbook writer | No | Unchanged. |

## Architecture Considerations

Fits the existing plugin split: pure, CI-testable logic (`field_extract`, mark-scoring core) stays free of
PaddleOCR/image libraries; image I/O and PaddleOCR live in the plugin. `run()` gains an injectable
`mark_fn` alongside `ocr_fn` so the composition is testable with fakes. Label→field dictionaries for
identity/gender are the only layout knowledge added; positions come from runtime OCR.

## Success Criteria

- [ ] For the reference form, the plugin produces `identity=patient`, `gender=female`, `name=葉心安`, `medical_record_no=6250712919`, `service_date=2025-06-25` — each verified against the image.
- [ ] Pure mark-scoring and name/MRN parsing have unit tests that pass without PaddleOCR.
- [ ] A real-OCR regression test (optional marker) asserts the reference form maps to the ground-truth record.
- [ ] Recognized fields are emitted/written even when other required fields are missing (non-blocking verification), with gaps recorded as warnings.
- [ ] Existing tests and policy checks remain green.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Ink-probe misreads faint ticks or grid lines as marks | Med | Med | Tune threshold against the ground-truth form; require both ink and/or OCR-anomaly signal; flag low-confidence as warning. |
| Handwritten name/MRN split is ambiguous | Med | Med | CJK-run → name, digit-run → MRN; emit warning when uncertain, leave for review. |
| Non-blocking write lets bad data into the workbook | Med | Med | Gate behind an explicit opt-in path; record all demoted gaps as warnings in the import report. |
| Single reference form over-fits detection | Med | Med | Keep detection parameterized; treat the form as v1 ground truth and revisit with more samples later. |
