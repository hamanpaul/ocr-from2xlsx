# Proposal: Handwritten name recognition via optional VLM agent + correction-learning loop

**Change ID:** `add-handwritten-name-agent`
**Created:** 2026-05-30
**Status:** Draft

---

## Problem Statement

The pipeline now recognizes `service_date`, `identity`, `gender`, and `medical_record_no` from the
service-record form, but the **handwritten name** — the most safety-critical field — is unsolved. On the
reference form `tests/fixtures/pdf/for testing only.pdf` the name (confirmed by the user as「葉心安」) is
cursive running-script Chinese overlapping printed gridlines. PaddleOCR PP-OCRv5 (mobile/server) cannot
read it; even the strongest cloud vision model can only produce a plausible guess, not a guaranteed-correct
one. In a medical context a wrong name means the wrong patient, so an auto-OCR'd name must never be trusted
without human confirmation.

Affected: anyone capturing real forms — the name comes out empty/wrong today, blocking trustworthy import.

## Proposed Solution

Treat the name as **OCR-assist → optional VLM suggestion → mandatory human confirmation**, with a
**correction-learning loop** that makes the system more accurate and less cloud-dependent over time:

- **A. Name crop (offline plugin):** emit a PII-minimized crop of just the handwritten name line (excluding
  the medical-record-no digits and diagnosis date), recording its path in the record metadata.
- **B. Optional cloud VLM name agent (main app):** a config-selected adapter that, given only the name crop,
  returns a suggested name. If unconfigured / disabled / unreachable / erroring, it is a no-op and the
  existing flow is unaffected.
- **C. Correction store (main app):** every human confirmation/correction is appended to a local JSONL
  store: crop path, raw OCR, agent suggestion, roster suggestion, final value, field, record id, source.
- **D. Confirmed-name roster + fuzzy match (main app):** confirmed names accumulate into a local roster;
  OCR/agent candidates are fuzzy-matched (stdlib difflib) to recommend the closest known name. As the roster
  grows, close matches resolve locally without calling the cloud agent.

The name is always flagged `name.unconfirmed` until a human confirms it.

## Scope

### In Scope
- PII-minimized name-crop extraction in the offline plugin (excludes medical-record-no).
- A config-driven, gracefully-optional cloud VLM name agent that suggests a name from the crop.
- Correction store (append-only JSONL) written on human confirmation/correction.
- Confirmed-name roster + fuzzy-match recommendation (pure stdlib).
- `name.unconfirmed` flagging so names are never auto-trusted.

### Out of Scope
- Local VLM backend / pluggable multi-backend (v1 is cloud VLM only).
- Training/fine-tuning a local handwriting model.
- Feeding recent corrections as few-shot examples to the VLM (roster fuzzy-match is the v1 loop).
- Rewriting the review UI (names ride as suggestion + `name.unconfirmed`; existing review/edit flow confirms).
- Auto-recognizing patient-only fields and Section A checkboxes (separate change).

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| OCR plugin (`plugins/paddleocr/`) | Yes | Emit name-only crop + path in record metadata (offline). |
| Main app (new modules) | Yes | Name-agent adapter, config loader, correction store, roster + fuzzy match, integration. |
| Cloud transport | Yes (optional) | Only the name crop leaves the machine, only when the agent is enabled. |
| `ocr_plugin.v1` contract | No (additive) | Record gains a name-crop reference + `name.unconfirmed` warning; shape otherwise unchanged. |
| Workbook writer | No | Unchanged. |

## Architecture Considerations

Keeps the offline plugin offline; the only network use is the optional name agent in the main app, isolated
behind a config-driven adapter that is a no-op when absent. Pure logic (crop geometry, roster fuzzy match,
correction store IO) is stdlib and unit-testable without the cloud or PaddleOCR. The correction store and
roster live locally, so accuracy improves and cloud reliance drops as usage grows.

## Success Criteria

- [ ] Offline plugin emits a name-only crop (excluding medical-record-no) and records its path.
- [ ] Name agent suggests a name from the crop when configured; when unconfigured/unavailable the pipeline is unchanged and does not error.
- [ ] Name is always flagged `name.unconfirmed`; never written without human confirmation.
- [ ] Human confirmation/correction is appended to the correction store and updates the local roster.
- [ ] Roster fuzzy-match recommends the correct confirmed name for a near-miss candidate (stdlib, CI-tested).
- [ ] Existing tests and policy checks stay green; real cloud calls verified only via a manual spike.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Even the strongest VLM misreads the cursive name | High | High | Design assumes no full automation; name always human-confirmed; agent only suggests. |
| Crop accidentally includes the medical-record-no → extra PII leaves machine | Med | High | Crop excludes the record-no line; test asserts crop content; cloud agent is opt-in. |
| Roster fuzzy-match recommends a wrong similar name | Med | High | Similarity threshold; recommend (not auto-apply); human still confirms. |
| Cloud agent changes/outage | Med | Low | Gracefully optional; absence does not affect the pipeline. |
| Single-sample overfitting of crop coordinates | Med | Med | Derive crop from OCR anchor geometry, not fixed pixels; revisit with more samples. |
