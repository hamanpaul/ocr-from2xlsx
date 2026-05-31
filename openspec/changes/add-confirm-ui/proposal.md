# Proposal: Single-page form-mirroring confirmation UI

**Change ID:** `add-confirm-ui`
**Created:** 2026-05-31
**Status:** Draft

---

## Problem Statement

The review UI (`app.py`) only shows six text Entry fields (record_id, service_date, identity, name,
medical_record_no, gender). It has no choice controls for identity/gender, no patient-only fields, and none
of the Section-A checkboxes, so a human must squint field-by-field and cannot review or correct the whole
record. The shared `form_layout` model (sections/fields/options/codes/record_path) now exists and can drive
the whole form data-driven.

## Proposed Solution

Replace the six-field form with a **single-page, form-layout-driven, fully editable confirmation** that shows
every field of the service record at once and writes on one click:

- **`record_access`** (pure): read/write the Record by the dotted `record_path` from `form_layout`
  (`identity`, `patient_fields.age_group`, `services.consultation.health_medical`, `patient_fields.cancers`
  (list), `patient_fields.newly_diagnosed_within_year` (bool), …).
- **`confirm_form`** (pure): `record_to_form_state(layout, record)` and `apply_form_state(layout, record,
  state)` round-trip the record ↔ a Tkinter-free form-state, via `record_access`.
- **Form view** (Tkinter): build widgets from `form_layout` by kind — text→Entry, single_choice→Radiobutton,
  multi_choice→Checkbutton — grouped by section (A/B/C), scrollable, pre-filled from the record.
- **Adaptive source panel**: when the record has a source page image, show it beside the form for
  comparison; when it does not (webcam), show the form alone.
- **One-click confirm**: apply all widget values back to the Record, then
  `session.accept_scan(record, human_confirmed=True)` writes to the XLSX (stripping `name.unconfirmed`,
  persisting the name correction), and advances. Keep a force-write for incomplete records.

## Scope

### In Scope
- `record_access` (path-based get/set) and `confirm_form` (round-trip), both pure and unit-tested.
- A `form_layout`-driven single-page editable confirm view (all fields, all sections), pre-filled and editable.
- Adaptive source-image panel (shown only when a source page image exists).
- One-click `human_confirmed` write via the existing `ImportSession`, with force-write retained.

### Out of Scope
- Live webcam capture itself (existing capture is reused; this change is the confirm UI only).
- Extending the learning loop beyond the name (correction store stays name-focused as today).
- Changing the workbook writer, `ocr_plugin.v1`, `form_layout`, or `session` core semantics.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| New `record_access.py` | Yes | Pure path-based get/set over the Record (stdlib). |
| New `confirm_form.py` | Yes | Pure record↔form-state round-trip using record_access + form_layout. |
| `app.py` | Yes | Rework the review form into the form-layout-driven single page + adaptive panel + one-click confirm. |
| `session` / `correction_store` / `form_layout` | No | Reused; unchanged. |
| Workbook writer / `ocr_plugin.v1` | No | Unchanged. |

## Architecture Considerations

Keeps Tkinter-free, unit-testable logic (`record_access`, `confirm_form`) separate from the Tkinter view, so
the field read/write and prefill/collect are tested without a display. The view is data-driven from
`form_layout`, so adding/removing form fields needs no UI code change. `record_path == None` fields (e.g.
diagnosis date) are editable in the form but not written to the Record.

## Success Criteria

- [ ] One page shows every service-record field (text + single + multi), data-driven from `form_layout`, directly editable.
- [ ] `record_access` reads/writes every `record_path` correctly (nested, multi-choice list, bool, None).
- [ ] One-click confirm applies the whole page and writes via `human_confirmed=True`, advancing; name correction persisted.
- [ ] Source image is shown beside the form when present, hidden when absent (adaptive).
- [ ] Pure logic has unit tests; the UI has a construction smoke test; existing tests and policy stay green.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Path write mis-places nested / multi-choice / bool values | Med | High | `record_access` unit tests cover every path shape |
| ~120 widgets make the page cluttered/slow | Med | Med | Section LabelFrames + scrolling; data-driven generation |
| Source-image path resolution fails | Low | Low | Hide the panel (fall back to form-only); confirm flow unaffected |
| Confirmed record still blocked by an invalid code | Low | Med | Show the blocker inline; retain force-write |
