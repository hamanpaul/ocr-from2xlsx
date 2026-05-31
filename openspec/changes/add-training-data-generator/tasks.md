# Implementation Tasks: Handwriting training-data generator

**Change ID:** `add-training-data-generator`

All code uses TDD. Pure logic (sampler, answer_key, layout geometry) is tested with `.venv` (or `.venv-paddle`);
image drawing/synthesis has a smoke test and runs under `.venv-paddle` (PIL+numpy). The `training/` tool is
standalone and adds no main-package dependency.

---

## Phase 1: Coverage-driven sampler (pure)

- [ ] 1.1 Failing tests: a sampler over `form_layout` options yields per-image selections where single-choice
  fields have ≤1 selected, multi-choice get a non-empty subset when chosen, the per-image marked ratio is in
  10–50% of all options, at least one option is marked; and running a batch until every option is marked ≥5
  times terminates with full coverage.
- [ ] 1.2 Implement `training/sampler.py` (pure; seeded RNG for determinism; bias under-covered options).

**Quality Gate:** pure pytest passes; constraints + coverage hold.

---

## Phase 2: Answer-key assembler (pure, reuses confirm_form)

- [ ] 2.1 Failing tests: given a per-image selection (selected codes + text-field values), build a `Record`
  via `confirm_form.apply_form_state`; assemble a `service_record.v1` `Batch` where each record has
  `training: true` and `source_image`; the batch's records load through `json_io.load_batch` (extra keys
  ignored) and the selected codes land at their `record_path`.
- [ ] 2.2 Implement `training/answer_key.py` (pure; uses `form_layout`, `confirm_form`, `record_access`, `json_io`).

**Quality Gate:** pure pytest passes; answer key matches workflow schema.

---

## Phase 3: Layout reconstruction geometry (pure)

- [ ] 3.1 Failing tests: a geometry function maps each `form_layout` option/field cell to a pixel box using
  the blank xlsx column widths/row heights (with documented defaults for unstyled rows/cols); every box is
  within the page bounds and option boxes do not overlap across distinct cells.
- [ ] 3.2 Implement `training/layout_render.py` geometry part (pure; openpyxl to read widths/heights).

**Quality Gate:** pure pytest passes; boxes sane and cell-aligned.

---

## Phase 4: Base image + handwriting + mark synthesis (PIL)

- [ ] 4.1 Implement `training/layout_render.py` base-image drawing (grid + printed labels) and
  `training/handwriting.py`: text via OFL fonts (multiple, with jitter/rotation/size; fallback to system
  fonts) and procedural checkbox marks (✓ / dash / partial blackout) with style/thickness/offset variation.
- [ ] 4.2 `training/fetch_fonts.py`: download a curated set of OFL handwriting CJK fonts (TC-covering) into
  `training/fonts/`, writing a `SOURCES.md`/license note; idempotent; skip already-present fonts.

**Quality Gate:** runs under `.venv-paddle`; a mark drawn into an option box lands within that box (smoke test).

---

## Phase 5: Generator orchestration + outputs

- [ ] 5.1 Implement `training/generate.py`: sample → draw base + handwriting + marks → save
  `out/images/*.png` → assemble `out/answers.json`; optional light augmentation flag (noise/rotation/blur).
- [ ] 5.2 Smoke test (under `.venv-paddle`): generate a tiny batch (e.g. 2 images), assert PNGs exist, the
  answer key has matching records with `training`/`source_image`, and marked option boxes contain ink.

**Quality Gate:** smoke test passes; tiny batch produced end-to-end.

---

## Phase 6: Docs, gitignore, policy

- [ ] 6.1 `.gitignore`: add `training/fonts/` and `training/out/`.
- [ ] 6.2 README: a `training/` section (how to fetch fonts and generate; OFL note; offline generation).
- [ ] 6.3 `CHANGELOG.md [Unreleased]` entry.
- [ ] 6.4 `python -W error -m pytest -q` (pure tests), `python build/package.py`, `python -m policy_check --repo .` pass.

**Quality Gate:** all tests pass, policy clean, docs synced, fonts/out ignored.

---

## Completion Checklist

- [ ] Synthetic forms + workflow-format answer key generated; coverage/ratio/constraints met
- [ ] Pure sampler/answer_key/geometry unit-tested; image gen smoke-tested; no main-package dep added
- [ ] Ready for `requesting-code-review` then `openspec-archive`
