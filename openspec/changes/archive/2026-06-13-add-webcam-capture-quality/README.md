# add-webcam-capture-quality

Make the webcam a usable scan input. Empirical demos showed the recognition failure was capture
quality (resolution + focus), not missing CV: enabling autofocus, pulling the camera's native max
resolution, and good lighting took OCR raw_text from 25 to 1324 chars and recognized
service_date/identity/gender. v1: a reusable capture-quality core (autofocus + negotiated native max
resolution + a Laplacian sharpness gate that rejects blurry frames and prompts a retake), a
webcam/image → existing OCR plugin → `service_record.v1` JSON → app form-fill bridge (app
"capture & recognize" button + CLI), an optional conditioning layer (PaddleOCR orientation/unwarp +
OpenCV enhancement, gated and adopted only if an eval harness shows it helps), and handwritten
name-crop + MRN recognition improvements measured on a real captured-form fixture. Marks stay
best-effort (template registration deferred); auto-shutter / live guidance deferred.

Design: `docs/superpowers/specs/2026-06-13-webcam-capture-quality-design.md`.
