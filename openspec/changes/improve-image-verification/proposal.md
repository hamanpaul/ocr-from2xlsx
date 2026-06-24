# Proposal: Image-verification viewer — pan, wheel-zoom, field↔region linking

**Change ID:** `improve-image-verification`
**Created:** 2026-06-24
**Status:** Draft
**Issues:** #47 (影像驗證升級：拖曳平移＋滾輪縮放、記住縮放；欄位↔版面區塊連動框選)

---

## Problem Statement

When verifying a recognized record against its source page, the operator must read each field's value off the
image. Today the preview is a `tk.Text` widget with an embedded image (`image_create`) and only supports
center-crop "放大/縮小" and whole-image "旋轉":

- **No pan, no wheel-zoom.** The reviewer cannot drag to pan or scroll-wheel to zoom into a specific area; the
  only zoom is a center crop, so off-center fields (most of them) cannot be inspected closely.
- **No field↔region link.** There is no "click the field → the image frames/zooms the matching area"; the
  reviewer hunts for each field's location in the full page by eye, every record.

This is the slowest part of careful verification, especially for dense forms. Affected: the
cancer-resource-center operator reviewing scanned service-records.

## Proposed Solution

Replace the `tk.Text` preview with a **Canvas-based image viewer** for the review (static source image) path:

- **Drag-to-pan + wheel-zoom**, with the zoom level remembered for the session, so the reviewer can move and
  magnify freely instead of only center-cropping.
- **Field↔region framing (advanced):** when a field is focused (reusing the keyboard-first focus surface from
  #42/#43), the viewer frames / zooms to that field's region on the source image. The region geometry reuses
  the recognition layout's per-section `band` fractions (`SERVICE_RECORD_V1_LAYOUT` + `band_pixels`), so a
  focused field scrolls the image to its section band; the name field reuses its existing `name_crop` when
  present.

The live-camera preview keeps its current fit-to-pane rendering (per-frame pan/zoom is unnecessary and costly
on the Tk main thread); pan/zoom/link apply to the static review image. The viewer is a focused, testable
widget; the pure logic (pan/zoom transform math, field→region resolution) is unit-tested without Tk.

## Scope

### In Scope
- A Canvas-based review-image viewer supporting drag-to-pan and mouse-wheel zoom, remembering the session
  zoom, replacing the `tk.Text` image preview for the static source-image path.
- Field→region framing: focusing a field scrolls/zooms the viewer to that field's section `band` (or the
  name field's `name_crop`), reusing the recognition layout geometry and the #42/#43 focus surface.
- Pure helpers for the pan/zoom transform and field→region resolution, unit-tested without Tk.
- Keeping the live-camera preview and placeholder rendering working through the new viewer (fit-to-pane for
  live frames).

### Out of Scope
- Per-frame pan/zoom of the live camera feed.
- Auto edge-crop / de-skew / perspective correction / super-resolution of the source image.
- Per-field (sub-section) geometry beyond the existing section `band` granularity (and `name_crop`).
- Annotation / drawing on the image; OCR re-run from the viewer.
- The keyboard-first focus surface itself (#42/#43) and the mid-tier workflow items (#44/#45/#46/#48).

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `src/ocr_from2xlsx/image_viewer.py` | Yes (new) | Pure pan/zoom transform helpers (clamped zoom, pan offset, image→canvas mapping) and field→region resolution (record_path → section band via `SERVICE_RECORD_V1_LAYOUT`, name → `name_crop`). No Tk. |
| `src/ocr_from2xlsx/app.py` (`ReviewApp`) | Yes | Replace the `tk.Text` preview with a Canvas viewer for the static review image: drag-pan, wheel-zoom, remembered session zoom; route `_show_source_image` / `_show_placeholder_preview` / live-frame rendering through it (live = fit-to-pane); on field focus, frame the field's region. |
| `recognition/layout.py` (`band`, `band_pixels`) | No (reuse) | Section band geometry reused for field→region framing. |
| `record.ocr.name_crop` | No (reuse) | Name field framing reuses the existing crop. |
| Recognition / capture / write path | No | Capture still writes images as today; only the review rendering changes. |

## Architecture Considerations

Follows the repo's "pure logic + thin Tk wrapper" pattern: the transform math (zoom clamp, pan bounds,
image-point ↔ canvas-point mapping) and field→region resolution are pure functions unit-tested without Tk,
mirroring `_wheel_scroll_units` / `decide_camera_selection` / `band_pixels`. The Canvas viewer is a focused
widget that renders a single image with a (zoom, pan) transform; the live-camera path reuses the existing
fit-to-pane scaling (drawing to the Canvas instead of the Text). Field→region framing reuses the recognition
layout's section `band` (0..1 fractions scaled by `band_pixels`) and the focus surface added in #42/#43, so it
composes with the keyboard-first review rather than duplicating geometry. Replacing the `tk.Text` preview
touches `_poll_camera_frame`, `_show_source_image`, and `_show_placeholder_preview`, so those are migrated
together and covered by the existing camera/preview tests.

## Success Criteria

- [ ] The review image viewer supports drag-to-pan and mouse-wheel zoom, and remembers the zoom for the
  session; the old center-crop-only limitation is gone.
- [ ] Focusing a field frames/zooms the viewer to that field's region (section band; name → name crop),
  reusing the recognition layout geometry and the #42/#43 focus surface.
- [ ] The live-camera preview and placeholder still render correctly through the new viewer (live =
  fit-to-pane).
- [ ] Pan/zoom transform + field→region resolution have Tk-free unit tests; viewer wiring has real-Tk tests
  that skip cleanly with no display; the existing camera/preview tests stay green.
- [ ] `python -W error -m pytest -q` and `python -m policy_check --repo .` green; CHANGELOG + `record-confirmation`
  base spec synced on archive.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Replacing the `tk.Text` preview breaks live-camera rendering or the zombie-safe teardown | Med | High | Migrate `_poll_camera_frame`/`_show_source_image`/`_show_placeholder_preview` together; keep the existing fit-to-pane scaling and teardown; rely on the existing camera/preview tests + a manual webcam run. |
| Field→region framing imprecise (section band, not per-field) | High | Low | Scope the link to section-band granularity (+ `name_crop`); document it as "frames the field's area," not a tight per-field box; it still beats hunting the whole page. |
| Wheel-zoom / pan math off (image jumps, escapes bounds) | Med | Med | Pure, unit-tested transform with clamped zoom and pan bounds; zoom anchored at the cursor. |
| Canvas image scaling performance on large source pages | Low | Low | Downscale to a display copy as the current preview does; zoom works on the display copy. |
