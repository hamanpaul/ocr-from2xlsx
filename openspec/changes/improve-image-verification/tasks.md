# Implementation Tasks: Image-verification viewer

**Change ID:** `improve-image-verification`

All implementation uses TDD with fail-first tests before production code. Phase 1 (pure transform +
field→region resolution) is the foundation and lands first; the Canvas viewer and its app wiring build on it.
The `tk.Text` preview is migrated to a Canvas viewer together with the camera/placeholder paths.

## Phase 1: Pure pan/zoom transform + field→region resolution (no Tk)

- [ ] 1.1 Fail-first tests for `image_viewer` pure helpers: `clamp_zoom(z, min, max)`; `zoom_at(point, old,
  new, pan)` keeps the cursor point fixed while zooming; `clamp_pan(pan, image_size, view_size, zoom)` keeps
  the image within bounds; `field_region(record_path)` resolves a field to its section `band`
  (`SERVICE_RECORD_V1_LAYOUT` + `band_pixels`) or `None` when unknown; the name field resolves to its
  `name_crop` when present.
- [ ] 1.2 Implement `src/ocr_from2xlsx/image_viewer.py` with those pure functions (no Tk/cv2; geometry via
  `recognition.layout.band_pixels`).

**Quality Gate:** transform + region tests pass with no Tk.

## Phase 2: Canvas viewer widget (drag-pan + wheel-zoom + remembered zoom)

- [ ] 2.1 Fail-first real-Tk tests (skip on `tk.TclError`): a viewer loads an image; wheel events zoom about
  the cursor (zoom clamped); drag events pan within bounds; the session zoom is remembered across image
  swaps; `frame_region(box)` scrolls/zooms so the given image box is visible.
- [ ] 2.2 Implement the Canvas viewer (in `app.py` or a small widget class): render one image with a
  (zoom, pan) transform driven by the Phase-1 helpers; bind `<MouseWheel>` to zoom-at-cursor and
  `<ButtonPress-1>`/`<B1-Motion>` to pan; keep a session zoom; `frame_region(box)`.

**Quality Gate:** viewer pan/zoom/frame tests pass under real Tk and skip cleanly headless.

## Phase 3: Migrate the review/camera/placeholder rendering to the viewer

- [ ] 3.1 Fail-first tests: `_show_source_image` renders the source page in the viewer (pan/zoom available);
  `_show_placeholder_preview` shows the placeholder; the live-camera frame path renders fit-to-pane through
  the viewer; the existing camera/preview tests (`test_app_navigation`, `test_capture*`) stay green.
- [ ] 3.2 Replace the `tk.Text` preview with the Canvas viewer in `_build_ui`; route
  `_poll_camera_frame` (fit-to-pane), `_show_source_image` (pannable/zoomable), and
  `_show_placeholder_preview` through it; preserve the zombie-safe teardown and rotation handling.

**Quality Gate:** review + camera + placeholder render correctly; existing preview tests green.

## Phase 4: Field→region framing on focus

- [ ] 4.1 Fail-first tests: focusing a field frames the viewer to that field's region — section `band` for
  most fields, `name_crop` for the name — and a field with no known region leaves the view unchanged.
- [ ] 4.2 Wire the field-focus callback (the #42/#43 `on_field_focused` surface) to
  `viewer.frame_region(field_region(record_path))`; no-op when the region is unknown or no source image is
  loaded.

**Quality Gate:** field→region framing tests green.

## Phase 5: Integration, docs & verification

- [ ] 5.1 CHANGELOG `[Unreleased]` entry for #47; README image-verification note (pan/wheel-zoom, remembered
  zoom, click-field-to-frame). No new CLI subcommand → CLI help unchanged.
- [ ] 5.2 `python -W error -m pytest -q` and `python -m policy_check --repo .` green.
- [ ] 5.3 Manual verify on a real display: load a record with a source image → pan/drag, wheel-zoom, zoom
  remembered; focus fields → viewer frames each field's area; live camera still previews. Record in the PR.
- [ ] 5.4 Base OpenSpec spec (`openspec/specs/record-confirmation/spec.md`) synced on archive.

**Quality Gate:** full suite + policy green; live webcam + review verified; docs synced.

## Completion Checklist

- [ ] All phases complete and quality gates green
- [ ] CHANGELOG `[Unreleased]`, README, and PR-template checklist done
- [ ] Ready for `/openspec-archive improve-image-verification`
