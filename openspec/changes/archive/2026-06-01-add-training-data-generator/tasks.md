# Implementation Tasks: Handwriting training-data generator

**Change ID:** `add-training-data-generator`

All code uses TDD. Pure logic (sampler, answer_key, layout geometry) is tested with `.venv` (or
`.venv-paddle`); image drawing/synthesis has a smoke test and runs under `.venv-paddle` (PIL). The
`training/` tool is standalone and adds no main-package dependency.

---

## Phase 1: Coverage-driven sampler (pure)

- [x] 1.1 Failing tests: a sampler over `form_layout` options yields per-image selections where
  single-choice fields have ≤1 selected, multi-choice get a non-empty subset when chosen, the
  per-image marked ratio is in 10–50% of all options, at least one option is marked; and running a
  batch until every option is marked ≥5 times terminates with full coverage.
- [x] 1.2 Implement `training/sampler.py` (pure; seeded RNG for determinism; bias under-covered
  options with `(field_key, code)` coverage so repeated raw codes remain distinct across fields).

**Quality Gate:** pure pytest passes; constraints + coverage hold.

---

## Phase 2: Answer-key assembler (pure, reuses confirm_form)

- [x] 2.1 Failing tests: given a per-image selection (selected codes + text-field values), build a
  `Record` via `confirm_form.apply_form_state`; assemble a `service_record.v1` `Batch` where each
  record has `training: true` and `source_image`; the batch's records load through `json_io.load_batch`
  (extra keys ignored) and the selected codes land at their `record_path`.
- [x] 2.2 Implement `training/answer_key.py` (pure; uses `form_layout`, `confirm_form`,
  `record_access`, `json_io`).

**Quality Gate:** pure pytest passes; answer key matches workflow schema.

---

## Phase 3: Layout reconstruction geometry (pure)

- [x] 3.1 Failing tests: a geometry function maps each `form_layout` option/field cell to a pixel box
  using the blank xlsx column widths/row heights (with documented defaults for unstyled rows/cols);
  every box is within the page bounds and option boxes do not overlap across distinct cells.
- [x] 3.2 Implement `training/layout_render.py` geometry part (pure; openpyxl to read widths/heights).

**Quality Gate:** pure pytest passes; boxes sane and cell-aligned.

---

## Phase 4: Base image + handwriting + mark synthesis (PIL)

- [x] 4.1 Implement `training/layout_render.py` base-image drawing (grid + printed labels) and
  `training/handwriting.py`: text via downloadable fonts or system fallback, with bbox-aware placement
  that keeps ink inside the target box, and procedural checkbox marks (✓ / dash / partial blackout)
  with style/thickness/offset variation.
- [x] 4.2 `training/fetch_fonts.py`: download a curated set of OFL handwriting fonts into
  `training/fonts/`, writing a `SOURCES.md` note; idempotent; skip already-present fonts.

**Quality Gate:** runs under `.venv-paddle`; targeted regression tests cover vertical/tight-box
overflow paths and a mark drawn into an option box lands within that box.

---

## Phase 5: Generator orchestration + outputs

- [x] 5.1 Implement `training/generate.py`: sample → draw base + handwriting + marks → save
  `out/images/*.png` → assemble `out/answers.json`; support repo-local `python -m training.generate`,
  field-aware option lookup, optional light augmentation, and CJK-aware font fallback.
- [x] 5.2 Smoke test (under `.venv-paddle`): generate a tiny batch, assert PNGs exist, the answer key
  has matching records with `training`/`source_image`, marked option boxes contain ink, and CJK text
  selection does not get stuck on Latin-only fonts.

**Quality Gate:** smoke test passes; tiny batch produced end-to-end.

---

## Phase 6: Docs, gitignore, policy

- [x] 6.1 `.gitignore`: add `training/fonts/`, `training/out/`, and `training_smoke.png`.
- [x] 6.2 README: document font fetch + generation flow, offline behavior, outputs, and system-font
  fallback.
- [x] 6.3 `CHANGELOG.md [Unreleased]` entry.
- [x] 6.4 `.venv\Scripts\python -W error -m pytest -q`, `.venv\Scripts\python build\package.py`,
  `python -m policy_check --repo .`, and the `.venv-paddle` training smoke all pass.

**Quality Gate:** all tests pass, policy clean, docs synced, fonts/out ignored.

---

## Completion Checklist

- [x] Synthetic forms + workflow-format answer key generated; coverage/ratio/constraints met
- [x] Pure sampler/answer_key/geometry unit-tested; image gen smoke-tested; no main-package dep added
- [x] Ready for final review and archive
