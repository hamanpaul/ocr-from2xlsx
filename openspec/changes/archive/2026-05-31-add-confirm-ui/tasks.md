# Tasks: Single-page form-mirroring confirmation UI

## Phase 1: `record_access` — path-based get/set (pure)

- [x] 1.1 Failing tests: `get_by_path(record, path)` / `set_by_path(record, path, value)` for `identity`,
  `name`, `service_date`, `patient_fields.age_group`, `patient_fields.cancers` (list set/get),
  `patient_fields.newly_diagnosed_within_year` (bool), `services.consultation.health_medical` (list);
  unknown path raises; `set_by_path(record, None, …)` is a no-op (for `record_path=None` fields).
- [x] 1.2 Implement `src/ocr_from2xlsx/record_access.py` (pure stdlib; navigates Record dataclass attrs +
  the nested `patient_fields`/`services`/`services.consultation` dict).

## Phase 2: `confirm_form` — record ↔ form-state round-trip (pure)

- [x] 2.1 Failing tests: `record_to_form_state(layout, record)` returns per-field state (text value;
  single-choice selected code or ""; multi-choice set of selected codes; bool field as selected/not);
  `apply_form_state(layout, record, state)` writes it back via `record_access`; a round-trip on a populated
  record is stable (`apply_form_state(record_to_form_state(r)) == r` for layout-covered fields).
- [x] 2.2 Implement `src/ocr_from2xlsx/confirm_form.py` using `form_layout` + `record_access`.

## Phase 3: Form view widgets from `form_layout` (Tkinter)

- [x] 3.1 Build the view in `app.py` (or a new `ui_form.py`): iterate `service_record_layout()`, per field
  create text→Entry, single_choice→Radiobutton group (with an unselected state), multi_choice→Checkbutton
  per option, grouped by Section in scrollable LabelFrames; pre-fill from `record_to_form_state`.
- [x] 3.2 Collect widget state back into a form-state and `apply_form_state` to the Record on demand.

## Phase 4: Adaptive source-image panel

- [x] 4.1 When `record.source.preprocessed_image_path` resolves to an existing file (relative to the loaded
  JSON / output dir), show it beside the form; otherwise hide the panel (form-only).
- [x] 4.2 Smoke test: panel shown when a source image path exists, hidden when absent.

## Phase 5: One-click confirm-and-write flow

- [x] 5.1 Replace the per-field confirm with a single "確認並寫入": apply the whole page to the Record, mark
  `review.edited_by_user=True`, call `session.accept_scan(record, human_confirmed=True)`, persist the name
  correction, advance; show blockers inline; retain "強制寫入" (`force=True, human_confirmed=True`).
- [x] 5.2 Integration test (test_app_navigation style): a record edited on the page writes with status
  written/forced and the name.unconfirmed warning is cleared.

## Phase 6: Docs, policy

- [x] 6.1 Update `CHANGELOG.md [Unreleased]`.
- [x] 6.2 `python -W error -m pytest -q`, `python build/package.py`, `python -m policy_check --repo .` all pass.

## Completion Checklist

- [x] Single page shows/edits all fields; one-click confirm writes via human_confirmed
- [x] record_access / confirm_form pure unit-tested; view smoke-tested; adaptive panel works
- [x] Ready for `requesting-code-review` then `openspec-archive`
