# add-form-registration

Make webcam/scanned service-record recognition accurate by registering the captured image to the
canonical template before geometric checkbox classification, and by extracting the full form rather
than only 5 identity fields. The 125-box `template_boxes.json` and the synthetic-trained
`mark_model.json` already exist but only work on aligned input; handheld webcam frames are
unregistered, so geometry fails and `field_extract` falls back to fragile OCR-text heuristics for
identity/gender (inconsistent between captures) and never extracts the A/B/C service checkboxes.

This change adds `registration.py` (auto ORB→homography alignment to a blank-form canonical reference,
plus a manual 4-corner warp fallback), wires it into the plugin scan path, and extends `field_extract`
to map all 125 classified boxes through `form_layout.selection_to_record` into a complete
`service_record.v1`. A Phase 0 precision smoke gates the work (overlay the 125 boxes on a registered
real capture and measure post-registration mark hit rate) before building the loop. Mark-model
accuracy on real handwriting is measured; if synthetic marks don't generalize, the existing
harvest_corrections + retrain (eval-gate) path is used. The warm-plugin speed work is a separate
sub-project.

Design: `docs/superpowers/specs/2026-06-14-form-registration-checkbox-design.md`. Tracks GitHub #22.
