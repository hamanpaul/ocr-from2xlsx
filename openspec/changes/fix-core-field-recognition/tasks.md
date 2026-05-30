# Implementation Tasks: Fix core field recognition

**Change ID:** `fix-core-field-recognition`

All code uses TDD (test first, watch it fail, implement, watch it pass, commit). Pure logic is tested
with the main `.venv`; real-PaddleOCR checks run with `.venv-paddle` / the built bundle.

---

## Phase 1: Handwritten name / medical-record-no parsing (pure)

- [ ] 1.1 Failing tests in `tests/test_paddle_field_extract.py`: from 姓名/病歷號 anchor-row lines, extract a CJK run as `name` and a long digit run as `medical_record_no`; cover the reference case (`葉心安` + `6250712919`, even when OCR merges as `病人62507…`).
- [ ] 1.2 Implement parsing in `plugins/paddleocr/field_extract.py` (extend `extract_name_and_mrn`); keep stray-mark rejection from the prior change.

**Quality Gate:**
- [ ] `.venv` pytest passes for `test_paddle_field_extract.py`
- [ ] No regression in the full suite

---

## Phase 2: Mark-scoring core (pure, image-library-free)

- [ ] 2.1 Failing tests in `tests/test_mark_detect.py`: a pure `mark_score(region_pixels)` / `is_marked(...)` over a 2D grayscale array (list-of-lists) returns high score for a filled/ticked region and low for an empty box; threshold boundary covered.
- [ ] 2.2 Implement the pure scorer in `plugins/paddleocr/mark_detect.py` (dark-pixel ratio over a normalized region; no cv2/PIL in the pure core).

**Quality Gate:**
- [ ] `.venv` pytest passes for `test_mark_detect.py`

---

## Phase 3: Checkbox field resolution from OCR lines + marks

- [ ] 3.1 Failing tests: given OCR lines (text + bbox) for the identity/gender options plus a `marked` predicate, resolve `identity` (病人/親友及照顧者/一般民眾及其他) and `gender` (女性/男性/其他) to their codes; secondary OCR-anomaly signal (missing `□` / `中`/`V` prefix) covered.
- [ ] 3.2 Implement label→code dictionaries and the resolution logic (pure; takes an injected `is_marked(label_box)->bool`).

**Quality Gate:**
- [ ] `.venv` pytest passes

---

## Phase 4: Plugin composition + image ink-probe wrapper

- [ ] 4.1 Failing test for `run(request, ocr_fn, mark_fn)` in `tests/test_paddle_plugin_run.py`: with fake `ocr_fn` (reference lines) and fake `mark_fn`, the record contains `identity=patient`, `gender=female`, `name=葉心安`, `medical_record_no=6250712919`, `service_date=2025-06-25`.
- [ ] 4.2 Implement: extend `run()` to accept `mark_fn`; add the plugin-only image wrapper (load image, grayscale, crop the checkbox region left of each option label, call the pure scorer). Wire `_paddle` path to provide the real `mark_fn`.

**Quality Gate:**
- [ ] `.venv` pytest passes (fake-driven, no paddle)

---

## Phase 5: Non-blocking verification output

- [ ] 5.1 Failing tests: a non-blocking path emits/writes recognized fields when some required fields are missing, recording the gaps as warnings (not blockers). Decide and test the surface (e.g. `import-json --allow-incomplete` or an equivalent verification flag).
- [ ] 5.2 Implement the non-blocking path in the validation/session/CLI layer without changing default (blocking) behavior.

**Quality Gate:**
- [ ] `.venv` pytest passes; default blocking behavior unchanged

---

## Phase 6: Ground-truth regression + real-OCR verification

- [ ] 6.1 Add the reference ground-truth fixture: `{service_date:2025-06-25, identity:patient, name:葉心安, medical_record_no:6250712919, gender:female}`.
- [ ] 6.2 Add an optional-marker real-OCR test asserting the built bundle's output for the reference form equals the ground truth (skipped in default CI; run manually with the bundle).
- [ ] 6.3 Manually run the full chain on the reference form via the bundle and confirm each of the four fields against the image; record results.

**Quality Gate:**
- [ ] Pure/CI tests pass; manual real-OCR verification matches the image field-by-field

---

## Phase 7: Docs, policy, integration

- [ ] 7.1 Update `CHANGELOG.md [Unreleased]`.
- [ ] 7.2 Update README plugin section to describe checkbox/handwriting recognition + the verification path.
- [ ] 7.3 `python -W error -m pytest -q` and `python build/package.py` pass; `python -m policy_check --repo .` passes.

**Quality Gate:**
- [ ] All tests pass, policy check clean, docs synced

---

## Completion Checklist

- [ ] All phases complete and quality gates passed
- [ ] Reference form recognized correctly field-by-field (verified against image)
- [ ] Ready for `requesting-code-review` then `openspec-archive`
