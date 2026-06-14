# Implementation Tasks: Webcam capture quality + recognition bridge

**Change ID:** `add-webcam-capture-quality`

All implementation uses TDD with focused tests before production code. Phases A/B/C can ship as
separate PRs; A is the proven foundation and must land first.

## Phase A: Capture quality + webcam→OCR→form bridge

- [ ] Add fail-first tests: `measure_sharpness` numeric behaviour (sharp vs blurred synthetic array);
  sharpness-gate decision (pass/fail/boundary); image → `service_record.v1` batch JSON wrapping with
  stable record_id; CLI/app handler logic with capture + bridge monkeypatched.
- [ ] Implement `capture.py` `measure_sharpness`, `negotiate_max_resolution` (request oversized, read
  back actual — never hardcode a target), and `capture_still` (autofocus on, native max resolution,
  warm-up, returns frame + resolution + sharpness + brightness + passed); cv2-guarded.
- [ ] Implement the bridge: still image (webcam capture or file) → existing OCR plugin →
  `service_record.v1` JSON, reusing existing normalization/record_id; wire the app
  "擷取並辨識" button (manual, with the sharpness gate + retake prompt) and a CLI path; graceful
  fallback when no camera / too blurry / OCR fails.

## Phase B: Optional conditioning (adopt only if measured to help)

- [ ] Add fail-first tests for `document_condition.enhance` (grayscale/upscale/CLAHE/denoise output
  shape + dtype) and the webcam-path toggle for PaddleOCR `use_doc_orientation_classify` /
  `use_doc_unwarping` (scan path unchanged).
- [ ] Implement conditioning + plugin toggle; run the eval harness before/after and record whether it
  improves recognition. Keep it in the default flow ONLY if it helps; otherwise leave it an opt-in
  flag and log the conclusion.

## Phase C: Handwritten name + MRN recognition improvements

- [ ] Add fail-first tests (on captured-form OCR-line fixtures) for improved name-anchor location /
  name-crop emission and MRN extraction (anchor + digit run).
- [ ] Implement the `field_extract.py` / `name_crop.py` improvements; measure name/MRN hit rate on the
  fixture vs current. If a target can't be met, mark the limitation explicitly rather than forcing it.

## Cross-cutting: eval harness + verification

- [ ] Commit a real captured-form image fixture + ground-truth fields; add a marker eval harness
  (`.venv-paddle`) that runs fixture image → plugin OCR → per-field score (report.json/md).
- [ ] README, CHANGELOG `[Unreleased]`, base OpenSpec specs synced; `python -W error -m pytest -q`,
  `python -m policy_check --repo .` green; manually verify a real webcam capture → recognition in the
  app and record numbers in the PR.

## Completion Checklist

- [ ] All phases complete and quality gates green (Phase B/C outcomes recorded, even if a deferral)
- [ ] Ready for `/openspec-archive add-webcam-capture-quality`

## Outcome (2026-06-14)

- Phase A landed and **verified end-to-end** (`scan --image` of a sharp 8MP capture → real PaddleOCR
  plugin → batch JSON: service_date `2025-06-25`, identity `patient`, gender `female`).
- Phase B kept **opt-in, default OFF** (`document_condition.enhance()` + `SCAN_DOC_PREPROCESS`, the
  latter only active when doc-ori/UVDoc models are present locally; PDF scan path unchanged).
- Phase C committed a real captured-form fixture + regression test and documented the ceiling (MRN
  recoverable, name-crop anchor locatable, this fixture's handwritten name may stay unresolved — not
  forced).
- Phase D eval harness (`training/eval_scan.py` + tests) added during salvage; full suite 508 passed,
  policy 16/0.
- Implemented over ~8h by a copilot run that exited on premium-request quota before committing;
  salvaged and finished inline (junk artefacts dropped, work committed in phase-grouped commits,
  eval harness completed, end-to-end verified).
