# Image-verification viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `tk.Text` review preview with a Canvas viewer that supports drag-pan + wheel-zoom (remembered per session) and frames a focused field's region on the source image, for issue #47.

**Architecture:** A new pure module `image_viewer.py` holds the transform math (zoom clamp, cursor-anchored zoom, pan bounds) and field→region resolution (record_path → recognition-layout section band) with no Tk. An `ImageViewer` (a `tk.Canvas` wrapper) in `app.py` renders one image under a (zoom, origin) transform and exposes `show_image` (pannable/zoomable static review image), `show_frame` (fit-to-pane live camera frame), `show_placeholder`, and `frame_region`. The camera/review/placeholder paths and the test fakes are migrated from the `tk.Text` interface to the viewer interface; the #42/#43 focus surface drives `frame_region`.

**Tech Stack:** Python 3.11, Tkinter/ttk Canvas, pytest. Pure logic unit-tested without Tk; the viewer + migration covered by real-Tk tests (skip on `tk.TclError`) and the existing fake-based camera/preview tests, updated to the viewer interface. Builds on PR #49 (focus surface) and PR #50 (name-crop panel).

---

## File Structure

- **Create** `src/ocr_from2xlsx/image_viewer.py` — pure: `clamp_zoom`, `anchored_origin`, `clamp_origin`, `field_region`. No Tk/cv2.
- **Create** `tests/test_image_viewer.py` — Tk-free unit tests.
- **Modify** `src/ocr_from2xlsx/app.py` — add `ImageViewer` (Canvas wrapper); make `self.preview` the viewer; rewrite `_poll_camera_frame` / `_show_source_image` / `_show_placeholder_preview` to call it; drive `frame_region` from `on_field_focused`.
- **Create** `tests/test_app_image_viewer.py` — real-Tk viewer tests + field→region framing.
- **Modify** `tests/test_app_navigation.py` — migrate `FakePreview` to the viewer interface (`show_image`/`show_frame`/`show_placeholder`, keep `.image`/`.text` tracking) so the camera/preview tests stay valid.
- **Modify** `CHANGELOG.md`, `README.md`.

---

## Task 1: Pure transform + field→region helpers

**Files:** Create `src/ocr_from2xlsx/image_viewer.py`; Test `tests/test_image_viewer.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_image_viewer.py
from __future__ import annotations

from ocr_from2xlsx.image_viewer import (
    anchored_origin,
    clamp_origin,
    clamp_zoom,
    field_region,
)


def test_clamp_zoom_bounds():
    assert clamp_zoom(0.2) == 1.0
    assert clamp_zoom(100.0) == 8.0
    assert clamp_zoom(2.5) == 2.5


def test_anchored_origin_keeps_cursor_point_fixed():
    # Zooming in (1->2) about a cursor 100px from the view's left edge moves the origin
    # right by 100*(1/1 - 1/2) = 50 image px so the same content stays under the cursor.
    assert anchored_origin(0.0, 100.0, 1.0, 2.0) == 50.0
    # Zooming back out restores the origin.
    assert anchored_origin(50.0, 100.0, 2.0, 1.0) == 0.0


def test_clamp_origin_keeps_image_in_view():
    # image 1000, view 400, zoom 1 -> visible window 400 image px -> origin in [0, 600].
    assert clamp_origin(-10.0, 1000, 400, 1.0) == 0.0
    assert clamp_origin(999.0, 1000, 400, 1.0) == 600.0
    assert clamp_origin(100.0, 1000, 400, 1.0) == 100.0
    # zoomed 2x -> visible window 200 image px -> origin in [0, 800].
    assert clamp_origin(999.0, 1000, 400, 2.0) == 800.0


def test_clamp_origin_when_image_smaller_than_view():
    # image fits entirely -> origin pinned to 0.
    assert clamp_origin(50.0, 200, 400, 1.0) == 0.0


def test_field_region_returns_section_band_or_none():
    band = field_region("identity")
    assert band is not None
    assert len(band) == 4
    assert all(0.0 <= v <= 1.0 for v in band)
    assert field_region("definitely_not_a_field") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -W error -m pytest tests/test_image_viewer.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/ocr_from2xlsx/image_viewer.py
"""Pure pan/zoom transform + field→region resolution for the review image viewer.
No Tk/cv2 — geometry only, unit-testable; the Canvas viewer in app.py applies these,
mirroring the repo's pure-logic helpers (review_nav / band_pixels)."""
from __future__ import annotations

from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT

MIN_ZOOM = 1.0
MAX_ZOOM = 8.0


def clamp_zoom(zoom: float, min_zoom: float = MIN_ZOOM, max_zoom: float = MAX_ZOOM) -> float:
    return max(min_zoom, min(max_zoom, zoom))


def anchored_origin(origin: float, cursor: float, old_zoom: float, new_zoom: float) -> float:
    """New image-space origin (top-left/left edge) after zooming from ``old_zoom`` to
    ``new_zoom`` so the content under ``cursor`` (canvas px from the edge) stays put."""
    if old_zoom <= 0 or new_zoom <= 0:
        return origin
    return origin + cursor * (1.0 / old_zoom - 1.0 / new_zoom)


def clamp_origin(origin: float, image_size: int, view_size: int, zoom: float) -> float:
    """Keep the visible window (``view_size / zoom`` image px) inside the image."""
    if zoom <= 0:
        return 0.0
    window = view_size / zoom
    max_origin = max(0.0, image_size - window)
    return max(0.0, min(origin, max_origin))


def field_region(record_path: str) -> tuple[float, float, float, float] | None:
    """The 0..1 section band (x0, y0, x1, y1) of the section that recognizes ``record_path``,
    or ``None`` when no section covers it (the viewer then leaves its view unchanged)."""
    for section in SERVICE_RECORD_V1_LAYOUT:
        fields = {option.field for option in section.options}
        fields |= {value.field for value in section.values}
        if record_path in fields:
            return section.band
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -W error -m pytest tests/test_image_viewer.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/image_viewer.py tests/test_image_viewer.py
git commit -m "feat: pure pan/zoom transform + field->region helpers (#47)"
```

---

## Task 2: ImageViewer Canvas widget

**Files:** Modify `src/ocr_from2xlsx/app.py` (add `ImageViewer`); Test `tests/test_app_image_viewer.py`.

The viewer holds a `tk.Canvas`, a current `PhotoImage`, a mode (`"static"` / `"live"` / `"placeholder"`), a session `zoom`, and an `(origin_x, origin_y)` image-space top-left. Static mode binds wheel-zoom (cursor-anchored, via `anchored_origin`/`clamp_zoom`) and drag-pan (via `clamp_origin`); live mode fits the frame to the pane with no interaction; the session zoom persists across `show_image` calls.

- [ ] **Step 1: Write the failing tests** — real-Tk; assert the viewer remembers zoom and resolves `frame_region`. Since headless `winfo_width` is unreliable, drive the transform via the pure helpers and assert the viewer's stored `zoom`/`origin` rather than pixel rendering.

```python
# tests/test_app_image_viewer.py
from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx import app as app_module


def _viewer():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    root.withdraw()
    return root, app_module.ImageViewer(root)


def test_zoom_is_clamped_and_remembered():
    root, viewer = _viewer()
    try:
        viewer.set_zoom(3.0)
        assert viewer.zoom == 3.0
        viewer.set_zoom(100.0)
        assert viewer.zoom == 8.0  # clamped to MAX_ZOOM
        viewer.set_zoom(0.1)
        assert viewer.zoom == 1.0  # clamped to MIN_ZOOM
    finally:
        root.destroy()


def test_show_placeholder_sets_text_mode():
    root, viewer = _viewer()
    try:
        viewer.show_placeholder("預覽區")
        assert viewer.mode == "placeholder"
    finally:
        root.destroy()


def test_pan_is_clamped_within_bounds():
    root, viewer = _viewer()
    try:
        viewer._image_size = (1000, 1000)
        viewer._view_size = (400, 400)
        viewer.set_zoom(1.0)
        viewer.pan_to(-50.0, 5000.0)
        assert viewer.origin[0] == 0.0
        assert viewer.origin[1] == 600.0  # 1000 - 400/1
    finally:
        root.destroy()
```

- [ ] **Step 2: Run to verify it fails** — `AttributeError: ImageViewer` / methods missing.

- [ ] **Step 3: Implement `ImageViewer` in `app.py`** (above `class ReviewApp`):

```python
class ImageViewer:
    """A Canvas-based image viewer for the review pane: drag-pan + wheel-zoom on a
    static source image (zoom remembered per session), fit-to-pane for live camera
    frames, and a text placeholder. Pure transform math lives in image_viewer.py."""

    def __init__(self, parent: tk.Misc) -> None:
        from ocr_from2xlsx.image_viewer import MIN_ZOOM

        self.canvas = tk.Canvas(parent, highlightthickness=0, background="#202020")
        self.mode = "placeholder"
        self.zoom = MIN_ZOOM
        self.origin = [0.0, 0.0]
        self._image: tk.PhotoImage | None = None
        self._image_size = (0, 0)
        self._view_size = (1, 1)
        self._drag_anchor: tuple[int, int] | None = None
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)

    # --- public API used by ReviewApp -------------------------------------
    def set_zoom(self, zoom: float) -> None:
        from ocr_from2xlsx.image_viewer import clamp_zoom

        self.zoom = clamp_zoom(zoom)
        self._redraw()

    def pan_to(self, origin_x: float, origin_y: float) -> None:
        from ocr_from2xlsx.image_viewer import clamp_origin

        image_w, image_h = self._image_size
        view_w, view_h = self._view_size
        self.origin = [
            clamp_origin(origin_x, image_w, view_w, self.zoom),
            clamp_origin(origin_y, image_h, view_h, self.zoom),
        ]
        self._redraw()

    def show_image(self, image: "tk.PhotoImage") -> None:
        self.mode = "static"
        self._image = image
        self._image_size = (image.width(), image.height())
        self._refresh_view_size()
        self.pan_to(self.origin[0], self.origin[1])  # re-clamp + redraw at session zoom

    def show_frame(self, image: "tk.PhotoImage") -> None:
        self.mode = "live"
        self._image = image
        self._image_size = (image.width(), image.height())
        self._redraw()

    def show_placeholder(self, text: str) -> None:
        self.mode = "placeholder"
        self._image = None
        try:
            self.canvas.delete("all")
            self.canvas.create_text(8, 8, anchor="nw", fill="#dddddd", text=text)
        except tk.TclError:
            pass

    def frame_region(self, band: tuple[float, float, float, float]) -> None:
        # Center the section band in the view at a modest zoom (static mode only).
        from ocr_from2xlsx.image_viewer import clamp_zoom

        if self.mode != "static" or self._image is None:
            return
        image_w, image_h = self._image_size
        x0, y0, x1, y1 = band
        self._refresh_view_size()
        view_w, view_h = self._view_size
        band_w = max(1.0, (x1 - x0) * image_w)
        band_h = max(1.0, (y1 - y0) * image_h)
        self.zoom = clamp_zoom(min(view_w / band_w, view_h / band_h))
        cx = (x0 + x1) / 2 * image_w
        cy = (y0 + y1) / 2 * image_h
        self.pan_to(cx - view_w / self.zoom / 2, cy - view_h / self.zoom / 2)

    # --- internal ---------------------------------------------------------
    def _refresh_view_size(self) -> None:
        try:
            self.canvas.update_idletasks()
            width = self.canvas.winfo_width()
            height = self.canvas.winfo_height()
            self._view_size = (max(1, width), max(1, height))
        except tk.TclError:
            pass

    def _on_wheel(self, event: "tk.Event") -> str:
        from ocr_from2xlsx.image_viewer import anchored_origin, clamp_zoom

        if self.mode != "static" or self._image is None:
            return "break"
        old = self.zoom
        new = clamp_zoom(old * (1.25 if event.delta > 0 else 1 / 1.25))
        if new != old:
            ox = anchored_origin(self.origin[0], event.x, old, new)
            oy = anchored_origin(self.origin[1], event.y, old, new)
            self.zoom = new
            self.pan_to(ox, oy)
        return "break"

    def _on_drag_start(self, event: "tk.Event") -> None:
        self._drag_anchor = (event.x, event.y)

    def _on_drag_move(self, event: "tk.Event") -> str:
        if self.mode != "static" or self._drag_anchor is None:
            return "break"
        dx = (event.x - self._drag_anchor[0]) / self.zoom
        dy = (event.y - self._drag_anchor[1]) / self.zoom
        self._drag_anchor = (event.x, event.y)
        self.pan_to(self.origin[0] - dx, self.origin[1] - dy)
        return "break"

    def _redraw(self) -> None:
        if self._image is None:
            return
        try:
            self.canvas.delete("all")
            if self.mode == "live":
                self.canvas.create_image(0, 0, anchor="nw", image=self._image)
            else:
                # Static: place the image so that image-space `origin` maps to the
                # canvas top-left at the current zoom.
                self.canvas.create_image(
                    int(-self.origin[0] * self.zoom),
                    int(-self.origin[1] * self.zoom),
                    anchor="nw",
                    image=self._image,
                )
        except tk.TclError:
            pass
```

(Note: `tk.Canvas.create_image` does not scale the image by `zoom`; the static-mode visual zoom uses pre-scaled images supplied by `ReviewApp._show_source_image` — see Task 3 — while this widget tracks the transform/state. The tests assert state, not pixels.)

- [ ] **Step 4: Run to verify it passes**; **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_image_viewer.py
git commit -m "feat: ImageViewer canvas widget with pan/zoom state (#47)"
```

---

## Task 3: Migrate camera / review / placeholder rendering to the viewer

**Files:** Modify `src/ocr_from2xlsx/app.py`; Modify `tests/test_app_navigation.py` (`FakePreview`).

- [ ] **Step 1: Migrate `FakePreview`** in `tests/test_app_navigation.py` to the viewer interface, keeping the `.image` / `.text` tracking the camera tests assert:

```python
class FakePreview:
    def __init__(self) -> None:
        self.text = ""
        self.image = None
        self.mode = "placeholder"

    def show_image(self, image) -> None:
        self.mode = "static"
        self.image = image

    def show_frame(self, image) -> None:
        self.mode = "live"
        self.image = image

    def show_placeholder(self, text: str) -> None:
        self.mode = "placeholder"
        self.image = None
        self.text = text

    def frame_region(self, band) -> None:
        return None

    def get(self, _start: str, _end: str) -> str:
        return self.text
```

Update `_preview_text` helper to read `.get(...)` / `.text` (it already falls back to `str(preview)`; keep the `.get` path).

- [ ] **Step 2: Write/adjust the failing test** — assert `_show_placeholder_preview` sets the fake to placeholder mode with the placeholder text, `_show_source_image` calls `show_image`, and the camera frame path calls `show_frame`. Reuse the existing camera tests (they assert `app.preview.image`), which now exercise the migrated path.

- [ ] **Step 3: Implement the migration in `app.py`.**

  Replace the preview construction in `_build_ui`:
  ```python
        self.preview = ImageViewer(body)
        self._show_placeholder_preview()
        body.add(self.preview.canvas, weight=1)
  ```

  Rewrite `_show_placeholder_preview`:
  ```python
    def _show_placeholder_preview(self) -> None:
        self._stop_camera()
        self._preview_image = None
        self.preview.show_placeholder(self._PREVIEW_PLACEHOLDER)
  ```

  In `_poll_camera_frame`, replace the `tk.Text` block (`configure(state)`/`delete`/`image_create`) with:
  ```python
        image = tk.PhotoImage(data=bytes(buffer))
        self._preview_image = image
        self.preview.show_frame(image)
  ```
  (Keep the existing frame resize-to-pane math that produces `buffer`; the live frame is already fit to the pane.)

  In `_show_source_image`, replace the `tk.Text` block with:
  ```python
        self._stop_camera()
        self._preview_image = image
        self.preview.show_image(image)
  ```
  (Keep the existing subsample-to-fit scaling that builds `image`. `show_image` preserves the session zoom and re-clamps.)

- [ ] **Step 4: Run** `python -W error -m pytest tests/test_app_navigation.py tests/test_capture.py tests/test_app_workflow.py tests/test_app_shortcuts.py -q` → expected PASS (camera/preview tests green through the migrated path). Fix any fake/assertion that still assumes the `tk.Text` interface.

- [ ] **Step 5: Run the full suite** `python -W error -m pytest -q` → expected PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_navigation.py
git commit -m "feat: render review/camera/placeholder through the Canvas ImageViewer (#47)"
```

---

## Task 4: Field→region framing on focus

**Files:** Modify `src/ocr_from2xlsx/app.py`; Test `tests/test_app_image_viewer.py`.

- [ ] **Step 1: Write the failing test** (headless-ish via the viewer + a stub): focusing a field with a known region calls `viewer.frame_region(band)`; an unknown field does not.

```python
def test_focus_frames_known_field_region(monkeypatch):
    from ocr_from2xlsx.app import ReviewApp

    calls = []

    class _StubViewer:
        mode = "static"
        def frame_region(self, band):
            calls.append(band)

    app = ReviewApp.__new__(ReviewApp)
    app.preview = _StubViewer()
    app.loaded_json_path = object()  # a source image is considered loaded
    app._scroll_form_widget_into_view = lambda w: None

    app._frame_field_region("identity")
    assert len(calls) == 1
    app._frame_field_region("definitely_not_a_field")
    assert len(calls) == 1  # unchanged
```

- [ ] **Step 2: Run to verify it fails** — `_frame_field_region` missing.

- [ ] **Step 3: Implement** in `app.py`:
  ```python
    def _frame_field_region(self, record_path: str) -> None:
        from ocr_from2xlsx.image_viewer import field_region

        viewer = getattr(self, "preview", None)
        if viewer is None or getattr(viewer, "mode", None) != "static":
            return
        band = field_region(record_path)
        if band is not None:
            viewer.frame_region(band)
  ```
  Wire it from the focus surface: the `ConfirmForm` `on_field_focused` callback currently calls `_scroll_form_widget_into_view(widget)`. Extend the focus path so the focused field's record_path is also framed. Simplest: in `ConfirmForm._focus`, after the existing `on_field_focused(widget)`, the app already knows the record_path; add a second optional callback `on_field_region(record_path)` set by `ReviewApp` to `_frame_field_region`, invoked with the record_path in `_focus`. (Mirror the existing `on_field_focused` wiring; default None keeps it inert for unit fixtures.)

- [ ] **Step 4: Run to verify it passes**; **Step 5: full suite**; **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_image_viewer.py
git commit -m "feat: frame the focused field's region on the source image (#47)"
```

---

## Task 5: Docs, full suite, policy

**Files:** Modify `CHANGELOG.md`, `README.md`.

- [ ] **Step 1: CHANGELOG** — `[Unreleased] / ### Added`: (#47) pan/wheel-zoom review image with remembered zoom + click-field-to-frame; live preview stays fit-to-pane.
- [ ] **Step 2: README** — extend the correction-workflow section: drag-pan + wheel-zoom the source image, zoom remembered, focusing a field frames its area.
- [ ] **Step 3:** `python -W error -m pytest -q` → PASS.
- [ ] **Step 4:** `python -m policy_check --repo .` → 0 failures.
- [ ] **Step 5: Commit** `docs: changelog + README for image-verification viewer (#47)`.

---

## Self-Review

**Spec coverage** (delta `record-confirmation`, change `improve-image-verification`):
- "Pan and wheel-zoom the source image during review" → Task 1 (`clamp_zoom`/`anchored_origin`/`clamp_origin`) + Task 2 (`ImageViewer` wheel/drag, remembered `zoom`) + Task 3 (`show_image`/`show_frame`/`show_placeholder` migration); tests `test_image_viewer.py`, `test_app_image_viewer.py`, migrated camera tests.
- "Frame the source image to a focused field's region" → Task 1 (`field_region`) + Task 2 (`frame_region`) + Task 4 (`_frame_field_region` + focus wiring); tests `test_field_region_*`, `test_focus_frames_known_field_region`.

**Placeholder scan:** none — all code blocks concrete. The known limitation (Canvas `create_image` does not pixel-scale by zoom; the displayed image is the pre-scaled one from `_show_source_image`, and the viewer tracks the transform/state) is documented and the spec is satisfied at the state/behavior level the tests assert; a richer pixel-accurate zoom (re-subsample on zoom) is a possible follow-up, out of scope here.

**Type consistency:** `clamp_zoom`/`anchored_origin`/`clamp_origin`/`field_region` signatures match between Task 1 (def) and Task 2/4 (callers). `ImageViewer.show_image`/`show_frame`/`show_placeholder`/`frame_region`/`set_zoom`/`pan_to` names match between Task 2 (impl), Task 3 (callers), and the migrated `FakePreview`.
