# Proposal: Single-page form-mirroring confirmation UI

**Change ID:** `add-confirm-ui`
**Created:** 2026-05-31
**Status:** Archived

---

## Problem Statement

The current review UI only exposes a handful of top-level fields (`record_id`, `name`, `identity`,
`service_date`, `institution_name`, `source`) and a per-field confirm button. It does **not** surface the rest
of the Section-A checkboxes, so a human must squint field-by-field and cannot review or correct the whole
record. The shared `form_layout` model (sections/fields/options/codes/record_path) now exists and can drive
the whole form data-driven.

## Archived Outcome

This change was implemented as:

- a new pure `src/ocr_from2xlsx/record_access.py` module for dotted `record_path` get/set over `Record`,
  including nested patient/service fields and consultation categories;
- a new pure `src/ocr_from2xlsx/confirm_form.py` module for `record_to_form_state()` /
  `apply_form_state()` round-tripping between the workflow record and a Tkinter-free form-state;
- a `form_layout`-driven Tkinter confirmation view that renders the whole service record on one scrollable
  page, including clearable single-choice inputs and all section fields;
- adaptive source-image display in the review UI when a prepared page image is available;
- whole-page `確認並寫入` / `強制寫入` flows that write through `ImportSession` as human-confirmed and keep
  end-of-list navigation safe after the final record.

The accepted behavior is captured in the base `openspec/specs/record-confirmation/spec.md`.

## Scope / Impact

- Affects the Tk review GUI only; no CLI option or JSON schema changes.
- Introduces a pure record-path accessor layer and a pure form-state mapper for reuse and testability.
- Reuses the existing `form_layout` model as the single source of truth for fields/options/codes.

## Architecture Notes

- `record_access` stays GUI-independent and only navigates the workflow `Record`.
- `confirm_form` is GUI-independent and converts between Record and simple form-state.
- The Tkinter layer is responsible only for widget construction/binding and for handing a form-state to
  `confirm_form`; it does **not** hard-code field semantics.
- The source image panel is adaptive: present when an image exists, absent otherwise.

## Success Criteria

- [x] One page shows every service-record field (text + single + multi), data-driven from `form_layout`, directly editable.
- [x] `record_access` reads/writes every `record_path` correctly (nested, multi-choice list, bool, None).
- [x] One-click confirm applies the whole page and writes via `human_confirmed=True`, advancing; name correction persisted.
- [x] Source image is shown beside the form when present, hidden when absent (adaptive).
- [x] Pure logic has unit tests; the UI has a construction smoke test; existing tests and policy stay green.
