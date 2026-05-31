# Implementation Tasks: Shared form-layout model

**Change ID:** `add-form-layout-model`

All code uses TDD. Pure stdlib; the validation test may use openpyxl to read the repo's blank xlsx.

---

## Phase 1: Dataclasses + accessors (pure)

- [x] 1.1 Failing tests for `Option`/`Field`/`Section`/`FormLayout` dataclasses and accessors (`field_by_key`, `iter_fields`, `iter_options`, `options_by_code`).
- [x] 1.2 Implement the dataclasses + accessors in `src/ocr_from2xlsx/form_layout.py` (pure stdlib).

**Quality Gate:** `.venv` pytest passes; pure stdlib (no paddle/PIL/openpyxl import in the module).

---

## Phase 2: `service_record_layout()` content (curated, reuses constants)

- [x] 2.1 Failing tests asserting the built layout covers all sections/fields with the expected counts, every field's `kind` and `record_path`, and that choice options carry `constants.py` codes (identity/gender/nationality/age/channel/disease_status/source/cancer + consultation categories/supplies/referrals/outcomes), with cell refs.
- [x] 2.2 Implement `service_record_layout()` binding each sheet option (label@cell) to its constants code and `record_path`.

**Quality Gate:** `.venv` pytest passes; codes/record_paths legal.

---

## Phase 3: Model↔sheet two-way coverage validation

- [x] 3.1 Failing test (`tests/test_form_layout.py`, openpyxl): load the repo blank `服務紀錄表` sheet and assert (a) each `Option.cell` text contains its label, (b) every `□`-bearing option cell is represented by some Option, (c) every `Option.code` is legal for its field, (d) every non-null `record_path` matches a real Record field path.
- [x] 3.2 Resolve any mismatches by correcting the curated layout (NOT by weakening the test).

**Quality Gate:** two-way coverage test passes against the real sheet.

---

## Phase 4: Docs, policy

- [x] 4.1 Update `CHANGELOG.md [Unreleased]`; note the shared model and that A/B will consume it.
- [x] 4.2 `python -W error -m pytest -q`, `python build/package.py`, `python -m policy_check --repo .` all pass.

**Quality Gate:** all tests pass, policy clean, docs synced.

---

## Completion Checklist

- [x] All phases complete; model↔sheet coverage verified
- [x] Ready for `requesting-code-review` then `openspec-archive`
