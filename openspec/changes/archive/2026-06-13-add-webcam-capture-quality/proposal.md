# Proposal: Webcam capture quality + recognition bridge

**Change ID:** `add-webcam-capture-quality`
**Created:** 2026-06-13
**Status:** Archived

---

## Archived Outcome

Made the webcam a usable scan input. Empirical demos established the root cause of webcam-recognition
failure was capture quality (resolution + focus), not missing CV: autofocus + the camera's native max
resolution + lighting took OCR raw_text from 25 to 1324 chars. Delivered:

- **Phase A** — `capture.py` sharpness measure + gate + `capture_still` (autofocus, negotiated native
  max resolution), a still-image → OCR bridge (`scan.py`), a `scan` CLI, and the app
  "擷取並辨識" button; plugin runs under the resolved interpreter (`__PYTHON__`) with project-root /
  dist-bundle resolution. Verified end-to-end: a sharp 8MP capture recognized service_date
  `2025-06-25`, identity `patient`, gender `female`.
- **Phase B** — opt-in OpenCV `enhance()` and a `SCAN_DOC_PREPROCESS`-gated PaddleOCR
  orientation/unwarp hook, default OFF and only active when the doc-ori/UVDoc models are present
  locally; the PDF scan path is unchanged.
- **Phase C** — a real captured-form fixture + regression test; `field_extract` returns `name_anchor`
  metadata. Documented ceiling: MRN recoverable, name-crop anchor locatable, the fixture's handwritten
  name may stay unresolved (not forced).
- **Phase D** — `training/eval_scan.py` field-accuracy harness as the measure-then-decide basis.

Marks stay best-effort (template registration deferred); auto-shutter / live guidance deferred.
Accepted behavior is captured in `openspec/specs/record-preparation/spec.md`.

## Notes

Implemented over ~8h by a copilot run that exited on premium-request quota before committing; salvaged
and finished inline (junk artefacts dropped, phase-grouped commits, eval harness completed, end-to-end
verified, 508 passed / policy 16-0).

Design: `docs/superpowers/specs/2026-06-13-webcam-capture-quality-design.md`.
Plan: `docs/superpowers/plans/2026-06-13-webcam-capture-quality.md`.
