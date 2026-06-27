from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ocr_from2xlsx.capture import (
    JsonRecordSource,
    decide_camera_selection,
    enumerate_cameras,
    open_camera_capture,
)
from ocr_from2xlsx.confirm_form import apply_form_state, record_to_form_state
from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT
from ocr_from2xlsx.recognition.review_flags import flagged_fields
from ocr_from2xlsx.review_nav import (
    next_flagged_key,
    option_index_for_digit,
    prev_flagged_key,
)
from ocr_from2xlsx.correction_store import default_correction_store_path
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import FormLayout, service_record_layout
from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED, confirm_name
from ocr_from2xlsx.session import ImportSession


def _wheel_scroll_units(delta: int) -> int:
    """Map a Windows mouse-wheel delta to canvas scroll units (one notch = 120).

    Wheel up (positive delta) scrolls toward the top (negative units). Small
    touchpad deltas still move one unit so the wheel always responds."""
    if not delta:
        return 0
    units = int(-delta / 120)
    if units == 0:
        return -1 if delta > 0 else 1
    return units


class _Tooltip:
    """A minimal hover tooltip: a borderless Toplevel shown under ``widget`` on <Enter>
    and destroyed on <Leave>. Used to surface keyboard accelerators / button guidance in
    the GUI without baking them into button labels (which tests assert on)."""

    def __init__(self, widget: tk.Misc, text: str) -> None:
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event: "tk.Event | None" = None) -> None:
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip, text=self.text, background="#ffffe0", relief="solid", borderwidth=1,
                justify="left", padx=6, pady=3,
            ).pack()
            self._tip = tip
        except Exception:
            self._tip = None

    def _hide(self, _event: "tk.Event | None" = None) -> None:
        tip = self._tip
        self._tip = None
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass


class ConfirmForm:
    def __init__(
        self,
        parent: tk.Misc,
        layout: FormLayout,
        on_change: Callable[[], None] | None = None,
        on_field_focused: Callable[[tk.Misc], None] | None = None,
        on_field_region: Callable[[str], None] | None = None,
    ) -> None:
        self.layout = layout
        self._on_change = on_change
        self._on_field_focused = on_field_focused
        self._on_field_region = on_field_region
        self.frame = ttk.Frame(parent)
        self.text_fields: dict[str, tk.StringVar] = {}
        self.single_choice_fields: dict[str, tk.StringVar] = {}
        self._single_choice_option_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        self.multi_choice_fields: dict[str, dict[str, tk.BooleanVar]] = {}
        # Field-title labels keyed by record_path, so recognition can flag
        # low-confidence / unfilled fields for the reviewer.
        self._field_labels: dict[str, ttk.Label] = {}
        self._field_titles: dict[str, str] = {}
        # Keyboard-first review surface (#42/#43): the ordered list of navigable
        # fields (by record_path), the focus widget per field, the current flagged
        # set + last-focused field for cycling, and per-field digit-select handlers.
        self._nav_order: list[str] = []
        self._focus_widgets: dict[str, tk.Misc] = {}
        self._flagged: dict[str, str] = {}
        self._current_focus: str | None = None
        self._single_choice_select_by_digit: dict[str, Callable[[str], bool]] = {}
        # Active-field emphasis: the focused field's title goes bold so the operator can
        # see which field is active while Ctrl+Tab-cycling, a separate channel from the
        # flagged/de-emphasis foreground colors so the two never fight.
        self._active_label_path: str | None = None
        self._label_base_font = None
        self._label_bold_font = None
        self.frame.columnconfigure(0, weight=1)

        for section_row, section in enumerate(layout.sections):
            # Keep the A/B/C prefixes (they match the paper form) but don't leak an internal
            # lowercase id like "top" into the operator UI.
            prefix = (
                f"{section.id} "
                if section.id and section.id.isalpha() and section.id.isupper() and len(section.id) <= 2
                else ""
            )
            group = ttk.LabelFrame(self.frame, text=f"{prefix}{section.title}")
            group.grid(row=section_row, column=0, sticky="ew", padx=4, pady=4)
            group.columnconfigure(1, weight=1)
            for field_row, field in enumerate(section.fields):
                title_label = ttk.Label(group, text=field.title)
                title_label.grid(row=field_row, column=0, sticky="nw", padx=(0, 8), pady=3)
                if field.record_path:
                    self._field_labels[field.record_path] = title_label
                    self._field_titles[field.record_path] = field.title
                if field.kind == "text":
                    var = tk.StringVar()
                    entry = ttk.Entry(group, textvariable=var, width=30)
                    entry.grid(
                        row=field_row, column=1, sticky="ew", pady=3
                    )
                    entry.bind("<Key>", self._mark_changed)
                    self.text_fields[field.key] = var
                    if field.record_path:
                        self._focus_widgets[field.record_path] = entry
                        self._nav_order.append(field.record_path)
                elif field.kind == "single_choice":
                    # Single-choice rendered as mutually-exclusive checkboxes (per the
                    # UI request: no radios, no "清除" button). A StringVar holds the
                    # selected code; one BooleanVar per option drives the checkbox.
                    # Clicking an option selects it (clearing the rest); clicking the
                    # selected one clears the field — replacing the clear button.
                    var = tk.StringVar(value="")
                    option_vars: dict[str, tk.BooleanVar] = {}
                    options = ttk.Frame(group)
                    options.grid(row=field_row, column=1, sticky="w", pady=3)
                    for _col in range(4):  # even, aligned option columns for ragged grids
                        options.columnconfigure(_col, uniform="opt", minsize=120)

                    def _select(code: str, _var=var, _opts=option_vars) -> None:
                        chosen = "" if _var.get() == code else code
                        _var.set(chosen)
                        for option_code, option_var in _opts.items():
                            option_var.set(option_code == chosen)
                        self._notify_change()

                    option_codes = [option.code for option in field.options]
                    option_checkboxes: list[ttk.Checkbutton] = []
                    for option_index, option in enumerate(field.options):
                        bvar = tk.BooleanVar(value=False)
                        option_vars[option.code] = bvar
                        checkbox = ttk.Checkbutton(
                            options,
                            text=option.label,
                            variable=bvar,
                            command=lambda code=option.code: _select(code),
                        )
                        checkbox.grid(
                            row=option_index // 4,
                            column=option_index % 4,
                            sticky="w",
                            padx=(0, 8),
                            pady=2,
                        )
                        option_checkboxes.append(checkbox)

                    def _digit_select(char: str, _codes=option_codes, _select=_select) -> bool:
                        index = option_index_for_digit(char, len(_codes))
                        if index is None:
                            return False
                        _select(_codes[index])
                        return True

                    # Number-key option entry is bound ONLY on this field's option
                    # checkboxes, so digits never get stolen from text entries. Bind on
                    # the checkboxes we just built (not winfo_children()) so the digit→
                    # option index never drifts if the options frame gains other widgets.
                    for checkbox in option_checkboxes:
                        checkbox.bind(
                            "<Key>",
                            lambda event, handler=_digit_select: (
                                "break" if handler(event.char) else None
                            ),
                        )
                    self.single_choice_fields[field.key] = var
                    self._single_choice_option_vars[field.key] = option_vars
                    self._single_choice_select_by_digit[field.key] = _digit_select
                    if field.record_path and option_checkboxes:
                        self._focus_widgets[field.record_path] = option_checkboxes[0]
                        self._nav_order.append(field.record_path)
                elif field.kind == "multi_choice":
                    options = ttk.Frame(group)
                    options.grid(row=field_row, column=1, sticky="w", pady=3)
                    for _col in range(4):  # even, aligned option columns for ragged grids
                        options.columnconfigure(_col, uniform="opt", minsize=120)
                    code_vars: dict[str, tk.BooleanVar] = {}
                    first_checkbox = None
                    for option_index, option in enumerate(field.options):
                        bvar = tk.BooleanVar(value=False)
                        checkbox = ttk.Checkbutton(
                            options,
                            text=option.label,
                            variable=bvar,
                            command=self._notify_change,
                        )
                        checkbox.grid(
                            row=option_index // 4,
                            column=option_index % 4,
                            sticky="w",
                            padx=(0, 8),
                            pady=2,
                        )
                        # Explicit space-toggle (deterministic + testable); "break"
                        # suppresses the native toggle so the option flips exactly once.
                        checkbox.bind(
                            "<space>",
                            lambda event, key=field.key, code=option.code: (
                                self.toggle_multi_choice_option(key, code) or "break"
                            ),
                        )
                        code_vars[option.code] = bvar
                        if first_checkbox is None:
                            first_checkbox = checkbox
                    self.multi_choice_fields[field.key] = code_vars
                    if field.record_path and first_checkbox is not None:
                        self._focus_widgets[field.record_path] = first_checkbox
                        self._nav_order.append(field.record_path)
                else:
                    raise TypeError(f"Unsupported field kind: {field.kind!r}")

    def _mark_changed(self, _event: tk.Event | None = None) -> None:
        self._notify_change()

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def set_flagged_fields(self, flagged: dict[str, str]) -> None:
        """Mark fields needing the reviewer's attention (low-confidence / empty /
        unconfirmed) and de-emphasize the rest. ``flagged`` maps record_path -> reason.
        When at least one field is flagged, high-confidence fields are greyed so the
        flagged ones stand out (#43)."""
        self._flagged = dict(flagged)
        any_flagged = bool(flagged)
        for record_path, label in self._field_labels.items():
            title = self._field_titles[record_path]
            if record_path in flagged:
                label.configure(text=f"⚠ {title}", foreground="#b00020")
            elif any_flagged:
                label.configure(text=title, foreground="#9aa0a6")
            else:
                label.configure(text=title, foreground="")

    def flagged_keys(self) -> list[str]:
        """Flagged fields in layout (navigable) order."""
        return [key for key in self._nav_order if key in self._flagged]

    def flagged_count(self) -> int:
        # Count only navigable flagged fields: flagged_fields() can fall back to a raw
        # field-id key that is not in _nav_order, and the "待確認 N" badge must match the
        # fields the reviewer can actually jump to (flagged_keys filters by _nav_order).
        return len(self.flagged_keys())

    def _focus(self, record_path: str | None) -> str | None:
        if record_path is None:
            return None
        widget = self._focus_widgets.get(record_path)
        if widget is None:
            return None
        self._current_focus = record_path
        self._set_active_label(record_path)
        try:
            widget.focus_set()
        except Exception:
            pass
        if self._on_field_focused is not None:
            try:
                self._on_field_focused(widget)
            except Exception:
                pass
        if self._on_field_region is not None:
            try:
                self._on_field_region(record_path)
            except Exception:
                pass
        return record_path

    def _ensure_label_fonts(self, label: "ttk.Label | None") -> None:
        if self._label_bold_font is not None or label is None:
            return
        import tkinter.font as tkfont

        try:
            base = tkfont.Font(font=label.cget("font"))
            bold = base.copy()
            bold.configure(weight="bold")
            self._label_base_font = base
            self._label_bold_font = bold
        except Exception:
            self._label_base_font = None
            self._label_bold_font = None

    def _set_active_label(self, record_path: str | None) -> None:
        prev = self._active_label_path
        if prev == record_path:
            return
        self._ensure_label_fonts(
            self._field_labels.get(record_path) or self._field_labels.get(prev or "")
        )
        if self._label_bold_font is None:
            self._active_label_path = record_path
            return
        prev_label = self._field_labels.get(prev or "")
        if prev_label is not None:
            try:
                prev_label.configure(font=self._label_base_font)
            except Exception:
                pass
        new_label = self._field_labels.get(record_path or "")
        if new_label is not None:
            try:
                new_label.configure(font=self._label_bold_font)
            except Exception:
                pass
        self._active_label_path = record_path

    def clear_active_label(self) -> None:
        """Revert any active-field bold (used when a record shows nothing focused, e.g. a
        clean 0-flagged record) so a stale bold title never lingers across records."""
        self._set_active_label(None)

    def focus_first_flagged(self) -> str | None:
        """Focus the first flagged field, or the first editable field if none are
        flagged. Returns the focused field's record_path (or ``None``)."""
        flagged = self.flagged_keys()
        target = flagged[0] if flagged else (self._nav_order[0] if self._nav_order else None)
        return self._focus(target)

    def focus_next_flagged(self) -> str | None:
        return self._focus(next_flagged_key(self._nav_order, self._flagged, self._current_focus))

    def focus_prev_flagged(self) -> str | None:
        return self._focus(prev_flagged_key(self._nav_order, self._flagged, self._current_focus))

    def toggle_multi_choice_option(self, field_key: str, code: str) -> None:
        """Flip one multi-choice option (the spacebar action) and notify change."""
        bvar = self.multi_choice_fields.get(field_key, {}).get(code)
        if bvar is None:
            return
        bvar.set(not bvar.get())
        self._notify_change()

    def prefill(self, state: dict[str, object]) -> None:
        for key, var in self.text_fields.items():
            value = state.get(key, "")
            var.set("" if value is None else str(value))
        for key, var in self.single_choice_fields.items():
            value = state.get(key, "")
            chosen = "" if value is None else str(value)
            var.set(chosen)
            for code, bvar in self._single_choice_option_vars.get(key, {}).items():
                bvar.set(code == chosen)
        for key, code_vars in self.multi_choice_fields.items():
            selected = state.get(key, set())
            selected_codes = set() if selected is None else set(selected)
            for code, bvar in code_vars.items():
                bvar.set(code in selected_codes)

    def collect(self) -> dict[str, object]:
        state: dict[str, object] = {}
        for key, var in self.text_fields.items():
            state[key] = var.get()
        for key, var in self.single_choice_fields.items():
            state[key] = var.get()
        for key, code_vars in self.multi_choice_fields.items():
            state[key] = {code for code, bvar in code_vars.items() if bvar.get()}
        return state


class ImageViewer:
    """A Canvas-based image viewer for the review pane (#47): drag-pan + integer-step
    wheel-zoom on a static source image (zoom remembered per session), fit-to-pane for
    live camera frames, and a text placeholder. The transform math is pure
    (image_viewer.py); this widget holds Tk state and renders. Zoom magnifies via
    ``PhotoImage.zoom`` (integer factors; no PIL dependency, matching the repo)."""

    def __init__(self, parent: tk.Misc) -> None:
        from ocr_from2xlsx.image_viewer import MIN_ZOOM

        self.canvas = tk.Canvas(parent, highlightthickness=0, background="#202020")
        self.mode = "placeholder"
        self.zoom = MIN_ZOOM
        self.origin = [0.0, 0.0]
        self._placeholder = ""
        self._image: tk.PhotoImage | None = None        # live camera frame (tk)
        self._pil_image = None                          # static source image, full resolution (PIL)
        self._fit_scale = 1.0                           # full-res px -> fit-base px (zoom == 1 fills the pane)
        self._display_image = None                      # rendered ImageTk/PhotoImage; held so Tk does not GC it
        self._image_size = (0, 0)                       # fit-base size; the zoom/pan math works in this space
        self._view_size = (1, 1)
        self._drag_anchor: tuple[int, int] | None = None
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)
        self.canvas.bind("<Configure>", self._on_configure)

    def set_zoom(self, zoom: float) -> None:
        from ocr_from2xlsx.image_viewer import clamp_zoom

        self.zoom = clamp_zoom(zoom)
        # Re-clamp the origin to the new zoom (a smaller zoom has a larger valid window),
        # then redraw — so zooming out from a panned position can't leave a dark edge gap.
        self.pan_to(self.origin[0], self.origin[1])

    def pan_to(self, origin_x: float, origin_y: float) -> None:
        from ocr_from2xlsx.image_viewer import clamp_origin

        image_w, image_h = self._image_size
        view_w, view_h = self._view_size
        self.origin = [
            clamp_origin(origin_x, image_w, view_w, self.zoom),
            clamp_origin(origin_y, image_h, view_h, self.zoom),
        ]
        self._redraw()

    def show_image(self, pil_image) -> None:
        # #57: hold the FULL-RESOLUTION PIL image and render the visible window with a
        # LANCZOS crop-resize in _redraw, so the fit view is crisp and zooming reveals real
        # detail. The old path (tk.PhotoImage.subsample to fit + .zoom to magnify) was
        # nearest-neighbour on an already-decimated image — blocky — and could not load JPG.
        self.mode = "static"
        self._pil_image = pil_image
        self._image = None
        self._refresh_view_size()  # computes _fit_scale + _image_size from the pane + image
        self.pan_to(self.origin[0], self.origin[1])  # re-clamp + redraw at session zoom

    def show_frame(self, image: "tk.PhotoImage") -> None:
        self.mode = "live"
        self._image = image
        self._image_size = (image.width(), image.height())
        self._redraw()

    def show_placeholder(self, text: str) -> None:
        self.mode = "placeholder"
        self._image = None
        self._pil_image = None
        self._display_image = None
        self._placeholder = text
        try:
            self.canvas.delete("all")
            self.canvas.create_text(8, 8, anchor="nw", fill="#dddddd", text=text)
        except tk.TclError:
            pass

    def get(self, _start: str = "1.0", _end: str = "end") -> str:
        # Mirrors the old tk.Text preview's text accessor for tests / placeholder checks.
        return self._placeholder if self.mode == "placeholder" else ""

    def reset_view(self) -> None:
        """Fit the whole source image (zoom 1, origin top-left) — the neutral overview a
        clean record returns to so the operator isn't left zoomed into a prior field."""
        from ocr_from2xlsx.image_viewer import MIN_ZOOM

        if self.mode != "static" or self._pil_image is None:
            return
        self.zoom = MIN_ZOOM
        self._refresh_view_size()
        self.pan_to(0.0, 0.0)

    def frame_region(self, band: tuple[float, float, float, float]) -> None:
        from ocr_from2xlsx.image_viewer import clamp_zoom

        if self.mode != "static" or self._pil_image is None:
            return
        image_w, image_h = self._image_size
        self._refresh_view_size()
        view_w, view_h = self._view_size
        x0, y0, x1, y1 = band
        band_w = max(1.0, (x1 - x0) * image_w)
        band_h = max(1.0, (y1 - y0) * image_h)
        # Snap to an integer zoom (floor) so it equals the integer render factor in
        # _redraw — otherwise clamp_origin's window (view/zoom) disagrees with the
        # rendered factor and a dark gap shows past the image edge.
        self.zoom = clamp_zoom(float(int(min(view_w / band_w, view_h / band_h))))
        cx = (x0 + x1) / 2 * image_w
        cy = (y0 + y1) / 2 * image_h
        self.pan_to(cx - view_w / self.zoom / 2, cy - view_h / self.zoom / 2)

    def _refresh_view_size(self) -> None:
        try:
            self.canvas.update_idletasks()
            self._view_size = (max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        except tk.TclError:
            pass
        # Recompute the fit-base size whenever the pane size is known, so zoom==1 fills the
        # current pane and the pan/clamp math (which works in fit-base space) stays correct
        # even after the operator drags the splitter (#57).
        if self.mode == "static" and self._pil_image is not None:
            image_w, image_h = self._pil_image.size
            view_w, view_h = self._view_size
            if image_w > 0 and image_h > 0:
                self._fit_scale = min(view_w / image_w, view_h / image_h)
                self._image_size = (
                    max(1, round(image_w * self._fit_scale)),
                    max(1, round(image_h * self._fit_scale)),
                )

    def _on_configure(self, _event: "tk.Event") -> None:
        # Pane resized (splitter dragged): re-fit + redraw the static image so it tracks.
        if self.mode == "static" and self._pil_image is not None:
            self.pan_to(self.origin[0], self.origin[1])

    def _on_wheel(self, event: "tk.Event") -> str:
        from ocr_from2xlsx.image_viewer import anchored_origin, clamp_zoom

        if self.mode != "static" or self._pil_image is None:
            return "break"
        old = self.zoom
        new = clamp_zoom(old + (1.0 if event.delta > 0 else -1.0))
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
        try:
            if self.mode == "live":
                if self._image is None:
                    return
                self.canvas.delete("all")
                self._display_image = self._image
                self.canvas.create_image(0, 0, anchor="nw", image=self._image)
                return
            if self.mode != "static" or self._pil_image is None:
                return
            from PIL import Image, ImageTk

            view_w, view_h = self._view_size
            factor = max(1, int(round(self.zoom)))
            fit_scale = self._fit_scale or 0.0
            if fit_scale <= 0:
                return
            ox, oy = self.origin  # fit-base-space top-left of the visible window
            win_w = view_w / factor
            win_h = view_h / factor
            image_w, image_h = self._pil_image.size
            # Visible window mapped from fit-base space to full-res source px (clamped to image).
            sx0 = max(0.0, min(float(image_w), ox / fit_scale))
            sy0 = max(0.0, min(float(image_h), oy / fit_scale))
            sx1 = max(0.0, min(float(image_w), (ox + win_w) / fit_scale))
            sy1 = max(0.0, min(float(image_h), (oy + win_h) / fit_scale))
            if sx1 - sx0 < 1 or sy1 - sy0 < 1:
                return
            crop = self._pil_image.crop((int(sx0), int(sy0), round(sx1), round(sy1)))
            # Render the visible crop at canvas resolution (display scale = fit_scale * factor):
            # output is ~pane-sized at any zoom — bounded memory, LANCZOS instead of pixel-replication.
            display_scale = fit_scale * factor
            out_w = max(1, round(crop.width * display_scale))
            out_h = max(1, round(crop.height * display_scale))
            resampler = getattr(Image, "Resampling", Image).LANCZOS
            display = crop.resize((out_w, out_h), resampler)
            self._display_image = ImageTk.PhotoImage(display)  # hold a ref so Tk does not GC it
            # The crop's top-left on the canvas: (its fit-space pos - origin) * factor.
            draw_x = round((sx0 * fit_scale - ox) * factor)
            draw_y = round((sy0 * fit_scale - oy) * factor)
            self.canvas.delete("all")
            self.canvas.create_image(draw_x, draw_y, anchor="nw", image=self._display_image)
        except tk.TclError:
            pass
        except Exception:
            pass


class ReviewApp(tk.Tk):
    _PREVIEW_PLACEHOLDER = (
        "攝影機或圖片預覽區\n"
        "請按『選擇攝影機』開始連續掃描，或用『匯入資料夾批次』/『匯入 JSON』載入既有資料。"
    )
    _CAMERA_POLL_INTERVAL_MS = 33
    _CAMERA_RETRY_INTERVAL_MS = 100
    _CAMERA_FAILURE_LIMIT = 3
    _camera_capture: object | None = None
    _camera_after_id: str | None = None
    _camera_failure_count: int = 0
    _camera_index: int | None = None
    _preview_rotation: int = 0
    _preview_zoom: float = 1.0
    _autocapture_active: bool = False
    _autocapture_detector: object | None = None
    _autocapture_output_dir: object | None = None
    _autocapture_prev_gray: object | None = None
    _autocapture_baseline_gray: object | None = None
    _autocapture_need_baseline: bool = False
    _autocapture_baseline_samples: list | None = None
    _splash_closed: bool = False
    _status_var: object | None = None
    _status_log_path: object | None = None
    # Class defaults so the toolbar state machine / guards can read these on the headless
    # __new__ test harness without tripping tk.Tk.__getattr__ recursion; __init__ sets the
    # real instance values.
    session: object | None = None
    records: object = ()
    written_indices: object = frozenset()
    current_index: int = -1
    _controls: object | None = None  # set to a dict in _build_ui; default for headless getattr
    _autocapture_state_var: object | None = None
    _autocapture_banner: object | None = None
    # Colored record badge (#45); class-level default so headless ReviewApp.__new__
    # instances (no Tk) resolve it via getattr without tripping tk.Tk.__getattr__ recursion.
    _badge_label: object | None = None

    @staticmethod
    def _runtime_base_dir() -> Path:
        import os

        home = os.environ.get("OCR_FROM2XLSX_HOME")
        return Path(home) if home else Path.home() / ".ocr_from2xlsx"

    @classmethod
    def _default_status_log_path(cls) -> Path:
        return cls._runtime_base_dir() / "app.log"

    @classmethod
    def _config_path(cls) -> Path:
        return cls._runtime_base_dir() / "config.json"

    @classmethod
    def _load_preview_rotation(cls) -> int:
        import json

        try:
            data = json.loads(cls._config_path().read_text(encoding="utf-8"))
            return int(data.get("preview_rotation", 0)) % 360
        except Exception:
            return 0

    def _save_preview_rotation(self) -> None:
        import json

        try:
            path = self._config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"preview_rotation": self._preview_rotation}), encoding="utf-8"
            )
        except OSError:
            pass

    def __init__(self) -> None:
        super().__init__()
        self.title("OCR from Service Record to XLSX")
        self.geometry("1200x720")
        self.layout = service_record_layout()
        self.records: list[Record] = []
        self.current_index = -1
        self.session: ImportSession | None = None
        self.loaded_json_path: Path | None = None
        self.correction_store_path: Path | None = None
        self.editing = False
        self.written_indices: set[int] = set()
        self._written_rows: dict[int, int] = {}
        self._blocked_indices: set[int] = set()
        self._pending_count: int = 0
        self._progress_text: str = ""
        self._badge_state: str = "pending"
        self._preview_image: tk.PhotoImage | None = None
        self._camera_capture = None
        self._camera_after_id: str | None = None
        self._camera_failure_count = 0
        self._camera_index = None
        self._preview_rotation = self._load_preview_rotation()
        self._preview_zoom = 1.0
        self._autocapture_active = False
        self._autocapture_detector = None
        self._autocapture_output_dir = None
        self._autocapture_prev_gray = None
        self._autocapture_baseline_gray = None
        self._autocapture_need_baseline = False
        self._autocapture_stills: list[Path] = []
        self._autocapture_baseline_samples: list = []
        self._splash_closed = False
        self._status_log: list[str] = []
        self._status_var = None
        self._status_log_path = self._default_status_log_path()
        self.fields: dict[str, tk.StringVar] = {}
        self._build_ui()
        self._update_toolbar_states()  # initial: disable buttons whose prerequisites are unmet
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        # State-machine controls: key -> list of "set enabled" callables. A key can drive both
        # a toolbar button AND a menu entry; _update_toolbar_states toggles all of them (#56).
        self._controls = {}

        def _register(key, setter) -> None:
            if key is not None:
                self._controls.setdefault(key, []).append(setter)

        def _menu_item(menu, label, command, key=None) -> None:
            menu.add_command(label=label, command=command)
            _register(
                key,
                lambda enabled, m=menu, lbl=label: m.entryconfig(
                    lbl, state="normal" if enabled else "disabled"
                ),
            )

        # --- Menu bar: 檔案 / 掃描 / 編輯 / 檢視 / 說明 — actions are categorised here so the
        # toolbar can stay down to the five most-used buttons (#56).
        menubar = tk.Menu(self, tearoff=0)

        file_menu = tk.Menu(menubar, tearoff=0)
        _menu_item(file_menu, "開新報表（選 XLSX 模板）", self._choose_template, "choose_template")
        _menu_item(file_menu, "匯入 JSON", self._load_json, "load_json")
        _menu_item(file_menu, "匯入資料夾批次", self._import_folder_batch, "import_folder_batch")
        file_menu.add_separator()
        file_menu.add_command(label="結束", command=self._on_close)
        menubar.add_cascade(label="檔案(F)", menu=file_menu, underline=3)

        scan_menu = tk.Menu(menubar, tearoff=0)
        _menu_item(scan_menu, "選擇攝影機", self._choose_camera, "choose_camera")
        _menu_item(scan_menu, "擷取並辨識", self._capture_and_recognize, "capture_recognize")
        scan_menu.add_separator()
        _menu_item(scan_menu, "連續拍照", self._start_continuous_capture, "start_continuous")
        _menu_item(scan_menu, "結束連拍並辨識", self._finish_continuous_capture, "complete_recognize")
        _menu_item(scan_menu, "連拍刪除上一張", self._undo_last_continuous_capture, "undo_last")
        _menu_item(scan_menu, "取消連拍", self._cancel_continuous_capture, "cancel_continuous")
        _menu_item(scan_menu, "重設空桌基準", self._reset_baseline, "reset_baseline")
        scan_menu.add_separator()
        scan_menu.add_command(label="校正透視（去除照片傾斜）…", command=self._calibrate_dewarp)
        menubar.add_cascade(label="掃描(S)", menu=scan_menu, underline=3)

        edit_menu = tk.Menu(menubar, tearoff=0)
        _menu_item(edit_menu, "上一筆", self._previous_record, "prev_record")
        _menu_item(edit_menu, "下一筆", self._next_record, "next_record")
        edit_menu.add_separator()
        _menu_item(edit_menu, "確認並寫入", self._confirm_current, "confirm")
        _menu_item(edit_menu, "強制寫入", self._force_write, "force")
        menubar.add_cascade(label="編輯(E)", menu=edit_menu, underline=3)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="放大", command=self._zoom_in_static)
        view_menu.add_command(label="縮小", command=self._zoom_out_static)
        view_menu.add_command(label="符合視窗", command=self._reset_static_view)
        view_menu.add_separator()
        view_menu.add_command(label="旋轉", command=self._rotate_preview)
        self._view_menu = view_menu
        self._rotate_menu_index = view_menu.index("end")  # the 旋轉 entry; label shows the angle
        menubar.add_cascade(label="檢視(V)", menu=view_menu, underline=3)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="快捷鍵", command=self._show_shortcut_help)
        menubar.add_cascade(label="說明(H)", menu=help_menu, underline=3)

        self.config(menu=menubar)
        self._update_rotate_button()  # reflect carried-over rotation in the 檢視 menu label

        # --- Slim toolbar: only the five most-used actions (#56) --------------------------
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=8)

        def _btn(text: str, command, key: str | None = None):
            button = ttk.Button(toolbar, text=text, command=command)
            button.pack(side=tk.LEFT, padx=4)
            _register(
                key,
                lambda enabled, b=button: b.configure(state="normal" if enabled else "disabled"),
            )
            return button

        _btn("開新報表", self._choose_template, "choose_template")
        _btn("匯入資料夾", self._import_folder_batch, "import_folder_batch")
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(8, 4))
        prev_btn = _btn("上一筆", self._previous_record, "prev_record")
        next_btn = _btn("下一筆", self._next_record, "next_record")
        confirm_btn = _btn("確認並寫入", self._confirm_current, "confirm")
        # Hover hints on the keyboard-driven actions (#48), since labels are now sparse.
        _Tooltip(prev_btn, "PgUp / Ctrl+←：上一筆")
        _Tooltip(next_btn, "PgDn / Ctrl+→：下一筆")
        _Tooltip(confirm_btn, "Enter / Ctrl+Enter：驗證必填欄位後寫入；缺漏會被擋下")

        # Persistent continuous-capture state banner — separate from the one-shot footer so
        # rotate/zoom/retry messages can't clobber the operator's "which state am I in?" cue.
        # Empty (thin strip) when not scanning; coloured + text while a session is live (#cc-01).
        self._autocapture_state_var = tk.StringVar(value="")
        self._autocapture_banner = tk.Label(
            self, textvariable=self._autocapture_state_var, anchor="w",
            background="#f3f3f3", foreground="#202124",
        )
        self._autocapture_banner.pack(side=tk.TOP, fill=tk.X, padx=8)

        # Footer: latest status on the left; batch/record progress + badge on the right (#45).
        footer = ttk.Frame(self)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self._status_var = tk.StringVar(
            value="請先按『選擇模板 XLSX』，再按『選擇攝影機』開始掃描。"
        )
        ttk.Label(footer, textvariable=self._status_var, anchor="w", relief="sunken").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        # Right-side group, packed right-to-left so the visual L→R is: progress (batch) |
        # badge (record) | 待確認 (record). A separator divides batch- from record-scope (#45).
        # Exception-first review (#43): how many fields on this record still need a human.
        self._pending_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self._pending_var, anchor="e", relief="sunken").pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        # Colored per-record status badge (#45): 已寫入/被擋下/待處理 read at a glance via
        # background color, not identical grey text. tk.Label honors bg across themes.
        self._badge_var = tk.StringVar(value="")
        self._badge_label = tk.Label(
            footer, textvariable=self._badge_var, anchor="e", relief="sunken", padx=6
        )
        self._badge_label.pack(side=tk.RIGHT, padx=(8, 0))
        # Persistent batch progress baseline (#45): always show a count, even before load.
        self._progress_var = tk.StringVar(value="尚未載入資料")
        ttk.Label(footer, textvariable=self._progress_var, anchor="e", relief="sunken").pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Separator(footer, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=4)

        # Two maximized panes: webcam/source preview on the left, the review form on the right.
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.preview = ImageViewer(body)
        self._show_placeholder_preview()
        body.add(self.preview.canvas, weight=1)

        form = ttk.Frame(body)
        body.add(form, weight=1)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(1, weight=1)

        canvas = tk.Canvas(form, highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(form, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        self._form_canvas = canvas
        self.confirm_form = ConfirmForm(
            canvas,
            self.layout,
            on_change=self._mark_editing,
            on_field_focused=self._scroll_form_widget_into_view,
            on_field_region=self._frame_field_region,
        )
        canvas_window = canvas.create_window((0, 0), window=self.confirm_form.frame, anchor="nw")
        self.confirm_form.frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(canvas_window, width=event.width),
        )

        def _on_mousewheel(event: "tk.Event") -> str:
            canvas.yview_scroll(_wheel_scroll_units(int(event.delta)), "units")
            return "break"

        # Bind the wheel on the canvas AND every form widget: child widgets cover the
        # canvas, so without per-widget binds the wheel does nothing over the options.
        canvas.bind("<MouseWheel>", _on_mousewheel)
        self._bind_mousewheel_recursive(self.confirm_form.frame, _on_mousewheel)

        self.fields = {
            "record_id": tk.StringVar(),
            "service_date": self.confirm_form.text_fields["service_date"],
            "identity": self.confirm_form.single_choice_fields["identity"],
            "name": self.confirm_form.text_fields["name"],
            "medical_record_no": self.confirm_form.text_fields["medical_record_no"],
            "gender": self.confirm_form.single_choice_fields["gender"],
        }

        self._init_camera()
        self._bind_review_shortcuts()

    def _show_shortcut_help(self) -> None:
        messagebox.showinfo(
            "鍵盤快捷鍵",
            "Enter / Ctrl+Enter　確認並寫入\n"
            "F2 / Ctrl+Shift+Enter　強制寫入\n"
            "PgDn / PgUp（或 Ctrl+→ / Ctrl+←）　下一筆 / 上一筆\n"
            "Esc　取消本筆編輯\n"
            "Ctrl+Tab / Ctrl+Shift+Tab　跳下一個 / 上一個待確認欄位\n"
            "數字鍵 1–N　選擇單選欄選項；空白鍵　切換多選欄",
        )

    def _calibrate_dewarp(self) -> None:
        """Mark the form's 4 corners once on a representative capture (fixed-camera setup)
        so the recognition dewarp can flatten every photo (#59). The auto-detector can't
        find a light form on a light desk, so the operator marks the corners on the
        high-res view where the faint paper edge is visible. Saves normalized corners to
        the runtime calibration file; recognition uses it when OCR_VLM_DEWARP is enabled."""
        from PIL import Image, ImageTk

        from ocr_from2xlsx.recognition.document_detect import save_calibration

        path = filedialog.askopenfilename(
            title="選擇一張代表性的表單照片來校正透視",
            filetypes=[("影像檔", "*.png *.jpg *.jpeg *.bmp"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            pil = Image.open(path)
            pil.load()
            pil = pil.convert("RGB")
        except Exception as exc:
            messagebox.showerror("校正透視", f"無法開啟影像：{exc}")
            return

        win = tk.Toplevel(self)
        win.title("校正透視")
        iw, ih = pil.size
        scale = min(900 / iw, 700 / ih, 1.0)
        disp_w, disp_h = max(1, int(iw * scale)), max(1, int(ih * scale))
        photo = ImageTk.PhotoImage(pil.resize((disp_w, disp_h)))
        labels = ["左上", "右上", "右下", "左下"]
        info = tk.StringVar(value=f"依序點選表單四角 — 第 1 角：{labels[0]}")
        ttk.Label(win, textvariable=info, anchor="w").pack(fill=tk.X, padx=8, pady=(8, 0))
        canvas = tk.Canvas(win, width=disp_w, height=disp_h, highlightthickness=0)
        canvas.pack(padx=8, pady=8)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas._photo = photo  # keep a reference so Tk does not GC it
        points: list[tuple[float, float]] = []

        def _redraw_base() -> None:
            canvas.delete("all")
            canvas.create_image(0, 0, anchor="nw", image=photo)

        def _on_click(event: "tk.Event") -> None:
            if len(points) >= 4:
                return
            ex = min(max(int(event.x), 0), disp_w)
            ey = min(max(int(event.y), 0), disp_h)
            points.append((ex / disp_w, ey / disp_h))
            canvas.create_oval(ex - 5, ey - 5, ex + 5, ey + 5, outline="#ff2d2d", width=2)
            canvas.create_text(ex + 8, ey - 8, text=str(len(points)), fill="#ff2d2d", anchor="w")
            if len(points) < 4:
                info.set(f"依序點選表單四角 — 第 {len(points) + 1} 角：{labels[len(points)]}")
            else:
                info.set("四角已標記，可按『儲存校正』；或『清除重點』重來。")
                save_btn.configure(state="normal")

        def _clear() -> None:
            points.clear()
            _redraw_base()
            info.set(f"依序點選表單四角 — 第 1 角：{labels[0]}")
            save_btn.configure(state="disabled")

        def _save() -> None:
            if len(points) != 4:
                return
            try:
                saved = save_calibration(points)
            except Exception as exc:
                messagebox.showerror("校正透視", f"儲存失敗：{exc}")
                return
            messagebox.showinfo(
                "校正透視",
                f"已儲存校正至：\n{saved}\n\n之後辨識若設定 OCR_VLM_DEWARP=1，將以此四角把表單攤平。",
            )
            win.destroy()

        canvas.bind("<Button-1>", _on_click)
        buttons = ttk.Frame(win)
        buttons.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(buttons, text="清除重點", command=_clear).pack(side=tk.LEFT)
        ttk.Button(buttons, text="取消", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 6))
        save_btn = ttk.Button(buttons, text="儲存校正", command=_save, state="disabled")
        save_btn.pack(side=tk.RIGHT)

    def _bind_review_shortcuts(self) -> None:
        # Keyboard-first review (#42): window-level shortcuts fire over any focused
        # field. Single-line ttk.Entry does not consume <Return>, so confirm-on-Enter
        # is safe; number-key option entry is bound per single-choice field, not here.
        self.bind("<Return>", self._on_confirm_key)
        self.bind("<KP_Enter>", self._on_confirm_key)
        self.bind("<Control-Return>", self._on_confirm_key)
        self.bind("<F2>", self._on_force_key)
        self.bind("<Control-Shift-Return>", self._on_force_key)
        self.bind("<Next>", self._on_next_record_key)        # PgDn
        self.bind("<Prior>", self._on_prev_record_key)       # PgUp
        self.bind("<Control-Right>", self._on_next_record_key)
        self.bind("<Control-Left>", self._on_prev_record_key)
        self.bind("<Escape>", self._on_cancel_key)
        self.bind("<Control-Tab>", self._on_next_flagged_key)
        # NOTE: Ctrl+Shift+Tab may be intercepted by the OS tab-switcher on macOS/GNOME;
        # the app targets Windows, where it reaches Tk.
        self.bind("<Control-Shift-Tab>", self._on_prev_flagged_key)

    def _on_confirm_key(self, _event: "tk.Event | None" = None) -> str:
        self._confirm_current()
        return "break"

    def _on_force_key(self, _event: "tk.Event | None" = None) -> str:
        self._force_write()
        return "break"

    def _on_next_record_key(self, _event: "tk.Event | None" = None) -> str:
        self._next_record()
        return "break"

    def _on_prev_record_key(self, _event: "tk.Event | None" = None) -> str:
        self._previous_record()
        return "break"

    def _on_cancel_key(self, _event: "tk.Event | None" = None) -> str:
        self._cancel_edit()
        return "break"

    def _on_next_flagged_key(self, _event: "tk.Event | None" = None) -> str:
        self.confirm_form.focus_next_flagged()
        return "break"

    def _on_prev_flagged_key(self, _event: "tk.Event | None" = None) -> str:
        self.confirm_form.focus_prev_flagged()
        return "break"

    def _cancel_edit(self) -> None:
        # Esc discards in-form edits. Restore values in place rather than repainting the
        # whole record (image re-frame, focus jump): a one-field undo should not yank the
        # operator out of their current context.
        if self.current_index < 0 or self.current_index >= len(self.records):
            self.editing = False
            return
        if not self.editing:
            # Nothing to undo; use Esc as a safe "recenter" to the first field needing
            # attention (no-op on a clean record) rather than a dead key (#43).
            if self.confirm_form.flagged_count() > 0:
                self.confirm_form.focus_first_flagged()
            return
        record = self.records[self.current_index]
        self.confirm_form.prefill(record_to_form_state(self.layout, record))
        self.confirm_form.set_flagged_fields(
            flagged_fields(list(record.ocr.warnings), SERVICE_RECORD_V1_LAYOUT)
        )
        self._update_pending_count()
        self.editing = False
        self._push_status("已還原本筆")

    def _frame_field_region(self, record_path: str) -> None:
        # On field focus, frame the source-image viewer to that field's section band (#47).
        from ocr_from2xlsx.image_viewer import field_region

        viewer = getattr(self, "preview", None)
        if viewer is None or getattr(viewer, "mode", None) != "static":
            return
        band = field_region(record_path)
        if band is not None:
            try:
                viewer.frame_region(band)
            except Exception:
                pass

    def _scroll_form_widget_into_view(self, widget: "tk.Misc") -> None:
        canvas = getattr(self, "_form_canvas", None)
        if canvas is None:
            return
        try:
            canvas.update_idletasks()
            offset = widget.winfo_rooty() - self.confirm_form.frame.winfo_rooty()
            total = self.confirm_form.frame.winfo_height()
            if total > 0:
                canvas.yview_moveto(max(0.0, min(1.0, offset / total)))
        except tk.TclError:
            pass

    def _update_pending_count(self) -> None:
        count = self.confirm_form.flagged_count()
        self._pending_count = count
        pending_var = getattr(self, "_pending_var", None)
        if pending_var is not None:
            try:
                pending_var.set(f"待確認 {count}（Ctrl+Tab 跳轉）" if count else "本筆已確認 ✓")
            except Exception:
                pass

    def _update_progress(self) -> None:
        total = len(self.records)
        if total == 0:
            text = "尚未載入資料"
        else:
            written = len(self.written_indices)
            text = f"已寫入 {written} / 共 {total}"
            row = getattr(self, "_written_rows", {}).get(self.current_index)
            if row is not None:
                text += f"　第 {row} 列"
        self._progress_text = text
        progress_var = getattr(self, "_progress_var", None)
        if progress_var is not None:
            try:
                progress_var.set(text)
            except Exception:
                pass

    def _update_badge(self) -> None:
        from ocr_from2xlsx.review_workflow import record_badge_state

        # No current record (cold start / just-picked template / empty load): blank the badge
        # rather than show a misleading 待處理 chip or a stale colored one from a prior batch.
        if not self.records or not (0 <= self.current_index < len(self.records)):
            self._badge_state = "pending"
            badge_var = getattr(self, "_badge_var", None)
            if badge_var is not None:
                try:
                    badge_var.set("")
                except Exception:
                    pass
            badge_label = getattr(self, "_badge_label", None)
            if badge_label is not None:
                try:
                    badge_label.configure(background="#e8eaed", foreground="#202124")
                except Exception:
                    pass
            return

        state = record_badge_state(
            self.current_index, self.written_indices, getattr(self, "_blocked_indices", set())
        )
        self._badge_state = state
        # (text, background, foreground) per state so 成功/被擋下/待處理 differ at a glance.
        styles = {
            "written": ("✓ 已寫入", "#1e7d34", "#ffffff"),
            "blocked": ("⛔ 被擋下", "#b00020", "#ffffff"),
            "pending": ("• 待處理", "#e8eaed", "#202124"),
        }
        text, bg, fg = styles[state]
        badge_var = getattr(self, "_badge_var", None)
        if badge_var is not None:
            try:
                badge_var.set(text)
            except Exception:
                pass
        badge_label = getattr(self, "_badge_label", None)
        if badge_label is not None:
            try:
                badge_label.configure(background=bg, foreground=fg)
            except Exception:
                pass

    def _focus_name_field(self) -> None:
        # Route through ConfirmForm._focus so the active-label bold, _current_focus and the
        # source-image re-frame all track the name field, then place the caret at the end.
        focus = getattr(self.confirm_form, "_focus", None)
        if not callable(focus):
            return
        try:
            focus("name")
        except Exception:
            return
        widget = getattr(self.confirm_form, "_focus_widgets", {}).get("name")
        if widget is not None:
            try:
                widget.icursor("end")
            except Exception:
                pass

    @staticmethod
    def _bind_mousewheel_recursive(widget: tk.Misc, handler) -> None:
        widget.bind("<MouseWheel>", handler)
        for child in widget.winfo_children():
            ReviewApp._bind_mousewheel_recursive(child, handler)

    def _choose_template(self) -> None:
        template = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not template:
            return
        output_dir = filedialog.askdirectory(title="選擇輸出資料夾")
        if not output_dir:
            return
        working = Path(output_dir) / "匯入中.xlsx"
        try:
            if self.session:
                self.session.close()
            self.session = ImportSession.start(template, working)
        except (OSError, ValueError) as exc:
            messagebox.showerror("無法建立工作檔", str(exc))
            return
        self.written_indices = set()
        self._written_rows = {}
        self._blocked_indices = set()
        self._push_status(f"工作檔: {working}")
        self._update_toolbar_states()  # template ready → write buttons can enable
        # New working file → reset the persistent corner so it does not show the old
        # batch's "已寫入 X / 列號" or a stale badge (#45).
        self._update_progress()
        self._update_badge()

    def _load_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            records = list(JsonRecordSource(path).records())
        except (OSError, ValueError) as exc:
            messagebox.showerror("無法載入 JSON", str(exc))
            return
        self._set_loaded_records(records, Path(path))

    def _set_loaded_records(self, records: list[Record], json_path: Path) -> None:
        self.records = records
        self.loaded_json_path = json_path
        self.correction_store_path = default_correction_store_path(self.loaded_json_path)
        self.current_index = -1
        self.editing = False
        self.written_indices = set()
        self._push_status(f"已載入 {len(self.records)} 筆 JSON")
        if self.records:
            self._next_record()
        else:
            self._show_placeholder_preview()
            self._update_progress()  # show the 尚未載入資料 baseline, not a blank corner (#45)
            self._update_badge()     # and blank the badge (no stale chip from a prior batch)
        self._update_toolbar_states()

    def _has_live_camera_preview(self) -> bool:
        return self._camera_capture is not None or self._camera_after_id is not None

    def _clear_inactive_camera_selection(self) -> None:
        if not self._has_live_camera_preview():
            self._camera_index = None

    def _capture_and_recognize(self) -> None:
        from ocr_from2xlsx.capture import (
            DEFAULT_MIN_SHARPNESS,
            CameraDependencyError,
            capture_still,
            require_camera_support,
        )

        if self.editing:
            messagebox.showerror("尚未保存", "目前資料已修改，請先使用「確認並寫入」或「強制寫入」。")
            return
        restore_camera_index = self._camera_index
        restore_live_preview = self._has_live_camera_preview()
        if restore_camera_index is None:
            try:
                require_camera_support()
            except CameraDependencyError as exc:
                self._clear_inactive_camera_selection()
                messagebox.showerror(
                "擷取並辨識",
                f"攝影機功能尚未安裝，請聯絡系統管理員。\n（技術細節：{exc}）",
            )
                return
            self._clear_inactive_camera_selection()
            messagebox.showwarning("擷取並辨識", "請先選擇可用的攝影機。")
            return
        self._paint_busy("擷取中…請稍候")  # legible feedback before the blocking capture freeze
        self._stop_camera()
        try:
            result = capture_still(
                restore_camera_index,
                min_sharpness=DEFAULT_MIN_SHARPNESS,
            )
        except CameraDependencyError as exc:
            self._clear_inactive_camera_selection()
            messagebox.showerror(
                "擷取並辨識",
                f"攝影機功能尚未安裝，請聯絡系統管理員。\n（技術細節：{exc}）",
            )
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("擷取並辨識", f"擷取失敗：{exc}")
            if restore_live_preview:
                self._start_camera(restore_camera_index)
            return
        if result is None:
            self._clear_inactive_camera_selection()
            messagebox.showwarning("擷取並辨識", "找不到可用的攝影機。")
            return
        if not result.passed:
            messagebox.showwarning(
                "擷取並辨識",
                f"畫面太模糊（清晰度 {result.sharpness:.0f}）。請調整對焦/光線/距離後重試。",
            )
            if restore_live_preview:
                self._start_camera(restore_camera_index)
            return
        self._play_shutter()  # same moment-of-capture cue as continuous mode
        self._flash_preview()
        self._recognize_capture(
            result.frame,
            restore_live_preview=restore_live_preview,
            restore_index=restore_camera_index,
        )

    def _recognize_capture(
        self,
        frame: object,
        *,
        restore_live_preview: bool = False,
        restore_index: int | None = None,
    ) -> None:
        import cv2

        from ocr_from2xlsx.cli import _resolve_template
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.plugin_backend import scan_doc_preprocess_env_overrides
        from ocr_from2xlsx.scan import next_output_artifact_path, prepare_records_from_images

        def restore() -> None:
            if restore_live_preview and restore_index is not None:
                self._start_camera(restore_index)

        selected_dir = filedialog.askdirectory(title="選擇辨識輸出資料夾")
        if not selected_dir:
            restore()
            return
        output_dir = Path(selected_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = next_output_artifact_path(output_dir, "scan-capture.png")
        if self._preview_rotation:
            from ocr_from2xlsx.capture import rotate_frame

            frame = rotate_frame(frame, self._preview_rotation)
        if not cv2.imwrite(str(image_path), frame):
            messagebox.showerror("擷取並辨識", f"無法寫入擷取影像：{image_path}")
            restore()
            return
        env_overrides = scan_doc_preprocess_env_overrides()

        def prepare(report, on_progress, should_cancel):
            report("辨識中，請稍候…首次辨識需載入模型，可能需要數十秒。")
            backend = self._resolve_recognition_backend(image_path, env_overrides)
            template = _resolve_template("service_record.v1")
            batch = prepare_records_from_images(
                [image_path], output_dir, template, backend, should_cancel=should_cancel
            )
            json_path = next_output_artifact_path(output_dir, "scan-prepared.json")
            dump_batch(batch, json_path)
            return list(JsonRecordSource(json_path).records()), json_path

        self._run_recognition_async(
            prepare,
            message="辨識中，請稍候…",
            on_records=lambda records, json_path: self._set_loaded_records(records, json_path),
            empty_msg="辨識結果沒有任何紀錄。",
            on_aborted=restore,
            error_title="擷取並辨識",
            error_message=lambda exc: f"辨識失敗：{exc}",
        )

    def _resolve_recognition_backend(self, roster_path, env_overrides):
        # Default to the PaddleOCR plugin: ~50x faster than the local VLM and it actually
        # reads the structured fields (MRN / checkboxes / identity); the handwritten name is
        # a human-confirm step either way. The vision VLM (qwen3-vl) is opt-in via
        # OCR_BACKEND=vision — on CPU/AMD it is ~9 min/photo and weak on handwriting (#60/#61).
        # OCR_BACKEND=plugin forces the plugin (surfacing an error if it is not installed).
        from ocr_from2xlsx.ocr_plugin import PluginUnavailableError
        from ocr_from2xlsx.recognition.factory import vision_config_from_env
        from ocr_from2xlsx.recognition.vlm_server import ensure_server, vision_runtime_available

        backend_choice = os.environ.get("OCR_BACKEND", "").strip().lower()

        def _vision():
            from ocr_from2xlsx.cli import _build_vision_backend

            vlm_host = vision_config_from_env()[0]
            ensure_server(vlm_host)
            return _build_vision_backend(roster_path)

        def _plugin():
            from ocr_from2xlsx.plugin_backend import PluginOcrBackend

            if env_overrides is None:
                return PluginOcrBackend.resolve()
            return PluginOcrBackend.resolve(env_overrides=env_overrides)

        if backend_choice == "vision":
            return _vision()
        try:
            return _plugin()
        except PluginUnavailableError:
            if backend_choice == "plugin":
                raise  # explicitly requested -> surface the install hint
            # Default path: fall back to the bundled VLM only when the plugin isn't installed.
            if vision_runtime_available(vision_config_from_env()[0]):
                return _vision()
            raise

    def _import_folder_batch(self) -> None:
        from ocr_from2xlsx.cli import _resolve_template
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.plugin_backend import scan_doc_preprocess_env_overrides
        from ocr_from2xlsx.scan import next_output_artifact_path, prepare_records_from_folder

        input_dir = filedialog.askdirectory(title="選擇含圖片/PDF 的資料夾")
        if not input_dir:
            return
        selected_out = filedialog.askdirectory(title="選擇辨識輸出資料夾")
        if not selected_out:
            return
        output_dir = Path(selected_out)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = next_output_artifact_path(output_dir, "batch-prepared.json")

        def prepare(report, on_progress, should_cancel):
            report("批次辨識中…啟動辨識服務 / 載入模型（首次較久）…")
            backend = self._resolve_recognition_backend(
                json_path, scan_doc_preprocess_env_overrides()
            )
            template = _resolve_template("service_record.v1")
            batch = prepare_records_from_folder(
                Path(input_dir), output_dir, template, backend,
                on_progress=on_progress, should_cancel=should_cancel,
            )
            dump_batch(batch, json_path)
            return list(JsonRecordSource(json_path).records()), json_path

        def on_records(records, json_path_):
            self._set_loaded_records(records, json_path_)
            self._push_status(f"批次辨識完成：{len(records)} 筆，請逐筆確認後寫入。")

        self._run_recognition_async(
            prepare,
            message="批次辨識中…",
            on_records=on_records,
            empty_msg="所選資料夾沒有圖片或 PDF，或沒有可辨識內容。",
            error_title="批次辨識失敗",
        )

    def _open_processing_modal(self, message: str, *, on_cancel=None):
        # Modal "processing" indicator shown while recognition runs on a WORKER thread. The
        # indeterminate progressbar animates because the Tk event loop stays free (the heavy
        # work is off-thread), so the operator sees the app is alive and Cancel works. Returns
        # None when there is no real Tk root (unit-test fixtures), so callers stay testable.
        try:
            modal = tk.Toplevel(self)
        except Exception:
            return None
        try:
            modal.title("處理中")
            modal.transient(self)
            modal.resizable(False, False)
            label = ttk.Label(modal, text=message, padding=(24, 24, 24, 8), justify="center")
            label.pack()
            modal._message_label = label
            bar = ttk.Progressbar(modal, mode="indeterminate", length=260)
            bar.pack(padx=24, pady=(0, 8))
            bar.start(12)
            modal._progress_bar = bar
            if on_cancel is not None:
                ttk.Button(modal, text="取消", command=on_cancel).pack(pady=(0, 16))
                modal.protocol("WM_DELETE_WINDOW", on_cancel)
            modal.update_idletasks()
            modal.grab_set()  # global input lock; the Cancel button inside stays usable
            modal.update()
        except Exception:
            pass
        return modal

    def _set_modal_message(self, modal, message: str) -> None:
        if modal is None:
            return
        try:
            modal._message_label.configure(text=message)
            modal.update()
        except Exception:
            pass

    def _close_processing_modal(self, modal) -> None:
        if modal is None:
            return
        try:
            bar = getattr(modal, "_progress_bar", None)
            if bar is not None:
                bar.stop()
            modal.grab_release()
            modal.destroy()
        except Exception:
            pass

    # Real app runs recognition off the Tk main thread; tests set this False to run inline
    # (synchronously) since the headless harness has no Tk event loop to marshal back to.
    _recognition_threaded: bool = True

    def _run_recognition_async(
        self, prepare, *, message, on_records, empty_msg, on_aborted=None,
        on_empty=None, error_title="辨識失敗", error_message=None,
    ) -> None:
        # Run recognition off the Tk main thread so the UI stays responsive (no white/ghosted
        # "Not Responding" window that reads as a crash). ``prepare(report, on_progress,
        # should_cancel)`` does ensure_server + backend + prepare_records + dump on the worker
        # and returns (records, json_path); ALL Tk work is marshalled back via self.after.
        inline = not getattr(self, "_recognition_threaded", True)
        cancel = threading.Event()
        modal = self._open_processing_modal(message, on_cancel=None if inline else cancel.set)

        def report(text: str) -> None:
            if inline:
                self._set_modal_message(modal, text)
            else:
                self.after(0, lambda t=text: self._set_modal_message(modal, t))

        def on_progress(done: int, total: int, name: str) -> None:
            report(f"{message}　{done}/{total}\n{name}")

        state: dict = {}

        def run_prepare() -> None:
            try:
                state["ok"] = prepare(report, on_progress, cancel.is_set)
            except Exception as exc:  # noqa: BLE001 - surface to the user on the main thread
                state["err"] = exc

        def finish() -> None:
            self._close_processing_modal(modal)
            if "err" in state:
                err = state["err"]
                msg = error_message(err) if error_message else f"{err}\n（已擷取的影像保留，可再次重試。）"
                messagebox.showerror(error_title, msg)
                if on_aborted is not None:
                    on_aborted()
                return
            records, json_path = state["ok"]
            if cancel.is_set():
                self._push_status("已取消辨識（已擷取的影像保留，可再次重試）。")
                if on_aborted is not None:
                    on_aborted()
                return
            if not records:
                messagebox.showwarning("辨識", empty_msg)
                if on_empty is not None:
                    on_empty()
                elif on_aborted is not None:
                    on_aborted()
                return
            on_records(records, json_path)

        if inline:
            run_prepare()
            finish()
            return

        def worker() -> None:
            run_prepare()
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True, name="recognition").start()

    def _next_record(self) -> None:
        if not self.records:
            messagebox.showerror("缺少資料", "請先載入 JSON 資料。")
            return
        if self.editing:
            messagebox.showerror("尚未保存", "目前資料已修改，請先使用「確認並寫入」或「強制寫入」。")
            return
        self.editing = False
        if self.current_index < 0:
            self.current_index = 0
        else:
            self.current_index = min(self.current_index + 1, len(self.records))
        if self.current_index >= len(self.records):
            messagebox.showinfo("完成", "沒有更多資料。")
            return
        self._show_record(self.records[self.current_index])

    def _previous_record(self) -> None:
        if not self.records:
            messagebox.showerror("缺少資料", "請先載入 JSON 資料。")
            return
        if self.editing:
            messagebox.showerror("尚未保存", "目前資料已修改，請先使用「確認並寫入」或「強制寫入」。")
            return
        if self.current_index >= len(self.records):
            self.current_index = len(self.records) - 1
        elif self.current_index <= 0:
            self.current_index = 0
        else:
            self.current_index -= 1
        self._show_record(self.records[self.current_index])

    def _confirm_current(self) -> None:
        if not self.session:
            messagebox.showerror("缺少工作檔", "請先選擇模板 XLSX。")
            return
        if self.current_index < 0 or self.current_index >= len(self.records):
            messagebox.showerror("缺少資料", "請先載入 JSON 資料。")
            return
        overwrite_row = self._overwrite_row_for_confirm()
        if overwrite_row is False:
            return
        record = self.records[self.current_index]
        self._apply_form_to_record(record)
        # Data-integrity guard (#46): 確認並寫入 sends human_confirmed=True, which clears the
        # name.unconfirmed flag — so a reflexive confirm with the name still blank would write
        # an empty name and silently mark it confirmed. Refuse it here; 強制寫入 stays the override.
        if NAME_UNCONFIRMED in record.ocr.warnings and not record.name.strip():
            messagebox.showwarning(
                "姓名未填",
                "此筆姓名待確認且目前為空。請先填入姓名再「確認並寫入」；"
                "若確定要留空，請改用「強制寫入」。",
            )
            self._focus_name_field()
            return
        human_confirmed = self._needs_name_confirmation(record)
        try:
            result = self.session.accept_scan(
                record, human_confirmed=True, overwrite_row=overwrite_row
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("寫入失敗", str(exc))
            return
        self._push_status(f"{result.record_id}: {result.status} row={result.row_number} blockers={result.blockers}")
        if result.status == "blocked":
            self._blocked_indices.add(self.current_index)
            self._update_badge()
            messagebox.showwarning(
                "未寫入工作檔",
                "此筆未寫入，因為有缺少或不合法的必填欄位：\n\n"
                + "\n".join(result.blockers)
                + "\n\n請在右側補齊後再按「確認並寫入」，或改用「強制寫入」。",
            )
            return
        if result.status in {"forced", "written"}:
            if human_confirmed:
                self._persist_confirmed_name_after_write(record)
            self.written_indices.add(self.current_index)
            self._written_rows[self.current_index] = result.row_number
            self._blocked_indices.discard(self.current_index)
            self.editing = False
            working = getattr(getattr(self.session, "writer", None), "working_path", "")
            self._push_status(f"已寫入工作檔 {working} 第 {result.row_number} 列")
            if overwrite_row is None:
                self._next_record()
            else:
                # Overwrite stays on the corrected record (no advance) so the operator
                # can verify the fix in place.
                self._update_progress()
                self._update_badge()

    def _overwrite_row_for_confirm(self, forced: bool = False) -> int | None | bool:
        """Decide the write target when (re-)confirming the current record (#48):
        ``None`` to append normally; the row number to overwrite an already-written
        record after a confirmation; ``False`` if the operator declined (caller returns).
        ``forced`` tailors the prompt so the operator knows whether validation will run
        (確認並寫入) or be skipped (強制寫入). Defaults the dialog to *No* so a reflexive
        Enter cancels rather than silently overwriting a written row."""
        if self.current_index not in self.written_indices:
            return None
        row = self._written_rows.get(self.current_index)
        if forced:
            prompt = f"強制覆寫第 {row} 列：將跳過必填檢查，可能寫入不完整資料。確定？"
        else:
            prompt = f"將以驗證後的內容覆寫第 {row} 列。確定？"
        if row is None or not messagebox.askyesno("覆寫確認", prompt, default=messagebox.NO):
            messagebox.showinfo("提示", "目前資料已寫入，請切換下一筆。")
            return False
        return row

    def _force_write(self) -> None:
        if not self.session:
            messagebox.showerror("缺少工作檔", "請先選擇模板 XLSX。")
            return
        if self.current_index < 0 or self.current_index >= len(self.records):
            messagebox.showerror("缺少資料", "請先載入 JSON 資料。")
            return
        overwrite_row = self._overwrite_row_for_confirm(forced=True)
        if overwrite_row is False:
            return
        record = self.records[self.current_index]
        self._apply_form_to_record(record)
        human_confirmed = self._needs_name_confirmation(record)
        try:
            result = self.session.accept_scan(
                record, force=True, human_confirmed=True, overwrite_row=overwrite_row
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("寫入失敗", str(exc))
            return
        self._push_status(f"{result.record_id}: {result.status} row={result.row_number} blockers={result.blockers}")
        if result.status == "blocked":
            self._blocked_indices.add(self.current_index)
            self._update_badge()
            messagebox.showwarning(
                "強制寫入仍被擋下",
                "此筆即使強制寫入仍無法寫入（有不可寫入的問題）：\n\n"
                + "\n".join(result.blockers)
                + "\n\n請更正後再寫入。",
            )
            return
        if result.status in {"forced", "written"}:
            if human_confirmed:
                self._persist_confirmed_name_after_write(record)
            self.written_indices.add(self.current_index)
            self._written_rows[self.current_index] = result.row_number
            self._blocked_indices.discard(self.current_index)
            self.editing = False
            working = getattr(getattr(self.session, "writer", None), "working_path", "")
            self._push_status(f"已寫入工作檔 {working} 第 {result.row_number} 列")
            self._update_progress()
            self._update_badge()
            # 強制寫入 can write a row that still fails validation; make that visible after
            # the fact (no extra gate, so the F2 / no-advance flow is unchanged) (#48).
            if result.blockers:
                messagebox.showwarning(
                    "已強制寫入（含缺漏）",
                    f"此筆已強制寫入第 {result.row_number} 列，但仍有未通過的欄位：\n\n"
                    + "\n".join(result.blockers)
                    + "\n\n如為誤覆寫，請更正後重新寫入。",
                )

    def _show_record(self, record: Record) -> None:
        self.fields["record_id"].set(record.record_id)
        self.confirm_form.prefill(record_to_form_state(self.layout, record))
        self.confirm_form.set_flagged_fields(
            flagged_fields(list(record.ocr.warnings), SERVICE_RECORD_V1_LAYOUT)
        )
        self._show_source_image(record)
        self.editing = False
        self._update_toolbar_states()
        self._update_pending_count()
        self._update_progress()
        self._update_badge()
        # Only grab focus + re-frame the scan when there is something to confirm. A clean
        # (0-flagged) record clears any stale active-field bold and resets the scan to a full
        # overview, so the operator can glance and hit Enter — instead of the caret being
        # yanked into the first field or the image staying zoomed into a prior field (#43).
        if self.confirm_form.flagged_count() > 0:
            self.confirm_form.focus_first_flagged()
        else:
            clear_active = getattr(self.confirm_form, "clear_active_label", None)
            if callable(clear_active):
                clear_active()
            reset_view = getattr(self.preview, "reset_view", None)
            if callable(reset_view):
                try:
                    reset_view()
                except Exception:
                    pass

    def _apply_form_to_record(self, record: Record) -> None:
        record.record_id = self.fields["record_id"].get()
        apply_form_state(self.layout, record, self.confirm_form.collect())
        record.review.edited_by_user = True

    def _needs_name_confirmation(self, record: Record) -> bool:
        if NAME_UNCONFIRMED not in record.ocr.warnings:
            return False
        final_name = record.name.strip()
        if not final_name:
            return False
        record.name = final_name
        return True

    def _persist_confirmed_name(self, record: Record) -> None:
        final_name = record.name.strip()
        if not final_name:
            return
        store_path = self.correction_store_path
        if store_path is None and self.loaded_json_path is not None:
            store_path = default_correction_store_path(self.loaded_json_path)
            self.correction_store_path = store_path
        if store_path is None:
            return
        confirm_name(
            store_path=store_path,
            record_id=record.record_id,
            final_value=final_name,
            ocr_raw=record.ocr.raw_text or "",
        )
        record.name = final_name

    def _persist_confirmed_name_after_write(self, record: Record) -> None:
        try:
            self._persist_confirmed_name(record)
        except (OSError, ValueError) as exc:
            messagebox.showerror("寫入失敗", str(exc))

    def _mark_editing(self, _event: tk.Event | None = None) -> None:
        self.editing = True

    def _init_camera(self) -> None:
        try:
            indices = enumerate_cameras()
        except Exception:
            self._clear_inactive_camera_selection()
            self._show_placeholder_preview()
            return

        decision = decide_camera_selection(indices)
        if not decision or decision[0] == "none":
            self._clear_inactive_camera_selection()
            self._show_placeholder_preview()
            return
        if decision[0] == "auto":
            self.after(0, lambda index=int(decision[1]): self._start_camera(index))
            return
        self.after(0, lambda indices=list(decision[1]): self._choose_camera(indices))

    def _choose_camera(self, indices: list[int] | None = None) -> None:
        if indices is None:
            try:
                indices = enumerate_cameras()
            except Exception:
                indices = []

        decision = decide_camera_selection(indices)
        if not decision or decision[0] == "none":
            self._clear_inactive_camera_selection()
            self._push_status("找不到攝影機")
            # Loud, actionable guidance (the most common real cause is a busy camera): the
            # operator opened Windows 相機 to "check" the webcam, which holds it exclusively.
            messagebox.showwarning(
                "找不到攝影機",
                "找不到可用的攝影機。請依序確認：\n\n"
                "1. 是否有其他程式正在使用鏡頭——特別是 Windows「相機」、Teams、Zoom。"
                "鏡頭被占用時本程式也會「找不到」，請先關閉它們再試。\n"
                "2. USB 連接是否正常（重新插拔一次）。\n"
                "3. 目前僅掃描裝置編號 0–4。",
            )
            return
        if decision[0] == "auto":
            self._start_camera(int(decision[1]))
            return

        index = self._ask_camera(list(decision[1]))
        if index is None:
            self._clear_inactive_camera_selection()
            return
        self._start_camera(index)

    def _ask_camera(self, indices: list[int]) -> int | None:
        if not indices:
            return None

        dialog = tk.Toplevel(self)
        dialog.title("選擇攝影機")
        dialog.transient(self)

        ttk.Label(dialog, text="偵測到多支攝影機，請選擇：").pack(padx=12, pady=(12, 4))
        listbox = tk.Listbox(dialog, height=min(6, len(indices)))
        for index in indices:
            listbox.insert(tk.END, f"攝影機 {index}")
        listbox.selection_set(0)
        listbox.activate(0)
        listbox.pack(padx=12, pady=4, fill=tk.BOTH, expand=True)

        chosen: dict[str, int | None] = {"value": None}

        def _confirm() -> None:
            selection = listbox.curselection()
            if selection:
                chosen["value"] = indices[selection[0]]
            dialog.destroy()

        ttk.Button(dialog, text="連接", command=_confirm).pack(padx=12, pady=(4, 12))
        dialog.grab_set()
        listbox.focus_set()
        self.wait_window(dialog)
        return chosen["value"]

    def _start_camera(self, index: int) -> None:
        self._stop_camera()
        try:
            capture = open_camera_capture(index)
        except Exception:
            self._clear_inactive_camera_selection()
            self._push_status("攝影機啟動失敗")
            self._show_placeholder_preview()
            return
        if capture is None:
            self._clear_inactive_camera_selection()
            self._push_status(f"無法開啟攝影機 {index}")
            self._show_placeholder_preview()
            return
        self._camera_capture = capture
        self._camera_failure_count = 0
        self._camera_index = index
        self._push_status(f"攝影機已連接（裝置 #{index}）")
        self._camera_after_id = self.after(0, self._poll_camera_frame)

    def _poll_camera_frame(self) -> None:
        capture = self._camera_capture
        if capture is None:
            return
        try:
            import cv2

            ok, frame = capture.read()
            if not ok or frame is None:
                self._retry_camera_preview("攝影機畫面連續讀取失敗，已停止預覽")
                return

            if self._autocapture_active and self._observe_autocapture_frame(frame):
                return

            if self._preview_rotation:
                from ocr_from2xlsx.capture import rotate_frame

                frame = rotate_frame(frame, self._preview_rotation)
            frame = self._zoom_crop(frame)

            self.preview.canvas.update_idletasks()
            target_width = self.preview.canvas.winfo_width()
            target_height = self.preview.canvas.winfo_height()
            if target_width > 1 and target_height > 1:
                height, width = frame.shape[:2]
                scale = min(target_width / width, target_height / height)
                # Downscale large frames to fit, and upscale a zoomed crop to fill the pane.
                if scale > 0 and abs(scale - 1.0) > 0.01:
                    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                    frame = cv2.resize(
                        frame,
                        (max(1, int(width * scale)), max(1, int(height * scale))),
                        interpolation=interpolation,
                    )

            success, buffer = cv2.imencode(".ppm", frame)
            if not success:
                self._retry_camera_preview("攝影機畫面連續編碼失敗，已停止預覽")
                return

            image = tk.PhotoImage(data=bytes(buffer))
            self._preview_image = image
            self.preview.show_frame(image)  # live frame: fit-to-pane, no pan/zoom
            self._camera_failure_count = 0
            self._dismiss_splash()  # first real frame drawn — safe to drop the boot splash
        except Exception:
            self._fail_camera_preview("攝影機預覽失敗，已停止預覽")
            return

        self._camera_after_id = self.after(
            self._CAMERA_POLL_INTERVAL_MS, self._poll_camera_frame
        )

    def _stop_camera(self) -> None:
        after_id = self._camera_after_id
        self._camera_after_id = None
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass

        capture = self._camera_capture
        self._camera_capture = None
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass
        self._camera_failure_count = 0

    def _retry_camera_preview(self, message: str) -> None:
        self._camera_failure_count += 1
        if self._camera_failure_count < self._CAMERA_FAILURE_LIMIT:
            self._camera_after_id = self.after(
                self._CAMERA_RETRY_INTERVAL_MS, self._poll_camera_frame
            )
            return
        self._fail_camera_preview(message, disconnect=True)

    def _fail_camera_preview(self, message: str, *, disconnect: bool = False) -> None:
        self._show_placeholder_preview()
        if disconnect:
            # A read failure mid-session = the camera was unplugged / hung. Keep the selected
            # index so the operator can one-click reconnect via「選擇攝影機」/擷取 instead of
            # being told「請先選擇可用的攝影機」; if a continuous session was live, pause it (#cam-disconnect).
            self._push_status("攝影機連線中斷，請確認 USB 連接後按「選擇攝影機」重試。")
            if getattr(self, "_autocapture_active", False):
                self._autocapture_active = False
                self._update_toolbar_states()
                self._set_autocapture_state(
                    "⚠ 攝影機連線中斷，連拍已暫停 → 接回攝影機後請重新『連續拍照』", tone="warn"
                )
            return
        self._push_status(message)
        self._clear_inactive_camera_selection()

    def _show_placeholder_preview(self) -> None:
        self._stop_camera()
        self._preview_image = None
        self.preview.show_placeholder(self._PREVIEW_PLACEHOLDER)

    def _dismiss_splash(self) -> None:
        if self._splash_closed:
            return
        self._splash_closed = True
        _close_boot_splash()

    def _show_source_image(self, record: Record) -> None:
        try:
            relative_path = record.source.preprocessed_image_path
            if not relative_path or self.loaded_json_path is None:
                self._show_placeholder_preview()
                return

            image_path = self.loaded_json_path.parent / relative_path
            if not image_path.is_file():
                self._show_placeholder_preview()
                return

            # Load the full-resolution source via Pillow (any format incl. JPG) and let the
            # viewer render it with a LANCZOS crop-resize (#57). The old tk.PhotoImage +
            # subsample path was nearest-neighbour, only loaded PNG, and lost detail on zoom.
            from PIL import Image

            pil_image = Image.open(image_path)
            pil_image.load()
            if pil_image.mode not in ("RGB", "L"):
                pil_image = pil_image.convert("RGB")

            self._stop_camera()
            self._preview_image = pil_image  # keep a reference alongside the viewer's
            self.preview.show_image(pil_image)  # static: drag-pan + wheel-zoom (integer steps)
        except Exception:
            self._show_placeholder_preview()

    def _push_status(self, message: str) -> None:
        log = getattr(self, "_status_log", None)
        if log is None:
            log = self._status_log = []
        log.append(message)
        if self._status_var is not None:
            try:
                self._status_var.set(message)
            except Exception:
                pass
        self._append_status_log_file(message)

    def _paint_busy(self, message: str) -> None:
        # Show an in-progress message AND force it to paint BEFORE the main thread blocks on
        # a synchronous capture/recognition — a plain status set does not repaint mid-freeze.
        # _status_var is None on the headless test harness; skip the Tk pump there.
        self._push_status(message)
        if self._status_var is not None:
            try:
                self.update_idletasks()
            except Exception:
                pass

    def _update_toolbar_states(self) -> None:
        # Advertise the workflow by enabling only the buttons valid in the current state — so
        # the operator can't press 完成辨識/取消連拍 before 連續拍照, or 確認並寫入 with no
        # template/record, and doesn't have to learn the order by being scolded by dialogs.
        controls = getattr(self, "_controls", None)
        if not controls:
            return
        active = bool(getattr(self, "_autocapture_active", False))
        has_stills = bool(getattr(self, "_autocapture_stills", None))
        has_session = getattr(self, "session", None) is not None
        records = getattr(self, "records", ()) or ()
        written = getattr(self, "written_indices", frozenset()) or frozenset()
        idx = getattr(self, "current_index", -1)
        valid_record = 0 <= idx < len(records)

        def _set(key: str, enabled: bool) -> None:
            for setter in controls.get(key, ()):
                try:
                    setter(enabled)
                except Exception:
                    pass

        # Continuous-capture cluster: 連續拍照 starts a session; the rest only apply during one
        # (完成辨識 stays usable when a camera-interrupt left stills to recognize).
        _set("start_continuous", not active)
        _set("complete_recognize", active or has_stills)
        _set("undo_last", active and has_stills)
        _set("cancel_continuous", active)
        _set("reset_baseline", active)
        # Buttons unrelated to scanning are disabled while a continuous session is live, so a
        # stray click can't hijack or abandon it.
        for key in (
            "capture_recognize", "import_folder_batch", "choose_camera",
            "load_json", "choose_template",
        ):
            _set(key, not active)
        # Write buttons need a working file (template) AND a current, not-yet-written record.
        write_ok = has_session and valid_record and idx not in written
        _set("confirm", write_ok)
        _set("force", write_ok)
        _set("prev_record", bool(records))
        _set("next_record", bool(records))

    def _set_autocapture_state(self, text: str, *, tone: str = "active") -> None:
        # Drive the persistent continuous-capture banner (separate from the transient footer).
        # tone picks the colour: active (scanning), warn (paused/interrupted); "" clears it.
        var = getattr(self, "_autocapture_state_var", None)
        if var is None:
            return
        try:
            var.set(text)
        except Exception:
            pass
        banner = getattr(self, "_autocapture_banner", None)
        if banner is not None:
            palette = {
                "active": ("#fff4ce", "#5f4b00"),
                "warn": ("#fde7e9", "#a4262c"),
                "": ("#f3f3f3", "#202124"),
            }
            bg, fg = palette.get(tone if text else "", palette[""])
            try:
                banner.configure(background=bg, foreground=fg)
            except Exception:
                pass

    def _append_status_log_file(self, message: str) -> None:
        path = self._status_log_path
        if path is None:
            return
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        except OSError:
            pass

    def _update_rotate_button(self) -> None:
        # Reflect the current (session-persisted) rotation in the 檢視 menu 旋轉 label so the
        # carried-over state is visible at launch, not only in a one-shot status line (#56).
        angle = getattr(self, "_preview_rotation", 0)
        text = "旋轉" if not angle else f"旋轉 {angle}°"
        menu = getattr(self, "_view_menu", None)
        index = getattr(self, "_rotate_menu_index", None)
        if menu is None or index is None:
            return
        try:
            menu.entryconfig(index, label=text)
        except Exception:
            pass

    def _rotate_preview(self) -> None:
        self._preview_rotation = (self._preview_rotation + 90) % 360
        self._save_preview_rotation()
        self._update_rotate_button()
        self._push_status(f"預覽旋轉 {self._preview_rotation}°（已記住，下次啟動沿用）")

    def _zoom_preview(self, factor: float) -> None:
        self._preview_zoom = min(8.0, max(1.0, self._preview_zoom * factor))
        self._push_status(f"預覽縮放 {self._preview_zoom:.2f}×")

    @staticmethod
    def _shutter_sound_path() -> Path | None:
        # app.py lives in src/ocr_from2xlsx/, and the PyInstaller spec bundles the wav
        # under ocr_from2xlsx/assets/, so this resolves for both source runs and the exe.
        path = Path(__file__).resolve().parent / "assets" / "shutter.wav"
        return path if path.is_file() else None

    @staticmethod
    def _imwrite_unicode(path: Path, frame: object) -> bool:
        """Write an image to a possibly non-ASCII path. cv2.imwrite silently fails on
        non-ASCII (e.g. CJK) paths on Windows; imencode + write_bytes does not."""
        import cv2

        try:
            ok, buf = cv2.imencode(".png", frame)
            if not ok:
                return False
            Path(path).write_bytes(buf.tobytes())
            return True
        except Exception:
            return False

    def _play_shutter(self) -> None:
        try:
            import winsound
        except Exception:
            return  # non-Windows / no audio module: silent no-op
        path = self._shutter_sound_path()
        try:
            if path is not None and path.is_file():
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    def _start_continuous_capture(self) -> None:
        from ocr_from2xlsx.autocapture import AutoCaptureConfig, AutoCaptureDetector
        from ocr_from2xlsx.capture import CameraDependencyError, require_camera_support

        if self._autocapture_active:
            return
        if self.editing:
            messagebox.showerror(
                "尚未保存", "目前資料已修改，請先使用「確認並寫入」或「強制寫入」。"
            )
            return
        if self._camera_index is None:
            try:
                require_camera_support()
            except CameraDependencyError as exc:
                self._clear_inactive_camera_selection()
                messagebox.showerror(
                    "連續拍照",
                    f"攝影機功能尚未安裝，請聯絡系統管理員。\n（技術細節：{exc}）",
                )
                return
            self._clear_inactive_camera_selection()
            messagebox.showwarning("連續拍照", "請先選擇可用的攝影機。")
            return
        # Don't let a stray 連續拍照 silently abandon an in-progress correction batch (#TB-03).
        records = self.records or ()
        written = self.written_indices or frozenset()
        if records and len(written) < len(records):
            remaining = len(records) - len(written)
            if not messagebox.askokcancel(
                "連續拍照",
                f"目前還有 {remaining} 筆校正未寫入（共 {len(records)} 筆，已寫入 {len(written)} 筆）。"
                "開始連續拍照會離開目前校正，確定要開始？",
            ):
                return
        # Warn about a missing template up front, before the slow scan/OCR (#scan-no-template).
        if self.session is None and not messagebox.askokcancel(
            "尚未選擇模板",
            "尚未選擇模板 XLSX，辨識後將無法寫入工作檔。是否仍要繼續擷取？",
        ):
            return
        selected_dir = filedialog.askdirectory(title="選擇辨識輸出資料夾")
        if not selected_dir:
            return
        if not messagebox.askokcancel("連續拍照", "請清空桌面，確定後擷取『空桌基準』。"):
            return
        output_dir = Path(selected_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._autocapture_output_dir = output_dir
        self._autocapture_stills = []
        self._autocapture_prev_gray = None
        self._autocapture_baseline_gray = None
        self._autocapture_need_baseline = True
        self._autocapture_baseline_samples = []
        self._autocapture_detector = AutoCaptureDetector(AutoCaptureConfig.from_env())
        self._autocapture_active = True
        self._update_toolbar_states()
        self._set_autocapture_state("● 連續拍照中：擷取空桌基準中…請保持桌面淨空")
        self._push_status("連續拍照：擷取空桌基準中…請保持桌面淨空。")
        if not self._has_live_camera_preview():
            self._start_camera(self._camera_index)

    def _cancel_continuous_capture(self) -> None:
        if not self._autocapture_active:
            self._push_status("尚未開始連續拍照；沒有可取消的連拍。")
            return
        restore = self._has_live_camera_preview()
        self._stop_camera()
        self._autocapture_active = False
        self._update_toolbar_states()
        self._set_autocapture_state("")
        count = len(self._autocapture_stills)
        self._push_status(f"已取消連續拍照（保留 {count} 張於輸出資料夾，未辨識）。")
        if restore:
            self._start_camera(self._camera_index)

    def _undo_last_continuous_capture(self) -> None:
        if not self._autocapture_active or not self._autocapture_stills:
            self._push_status("沒有可復原的擷取。")
            return
        last = self._autocapture_stills.pop()
        try:
            Path(last).unlink()
        except OSError:
            pass
        # Re-arm so the SAME form can be re-shot in place — undo usually means "that shot was
        # bad, retake". Without this the detector stays DISARMED and never retakes (#cc-07).
        detector = self._autocapture_detector
        if detector is not None:
            try:
                detector.set_baseline()
            except Exception:
                pass
        self._autocapture_prev_gray = None
        self._update_toolbar_states()
        self._push_status(
            f"已復原上一張，對準同一表單將自動重拍｜已擷取 {len(self._autocapture_stills)} 張"
        )

    def _reset_baseline(self) -> None:
        if not self._autocapture_active:
            self._push_status("尚未開始連續拍照。")
            return
        if not messagebox.askokcancel("重設空桌基準", "請清空桌面，確定後重抓『空桌基準』。"):
            return
        self._autocapture_need_baseline = True
        self._autocapture_prev_gray = None
        self._autocapture_baseline_samples = []
        self._set_autocapture_state("● 連續拍照中：重新擷取空桌基準中…請保持桌面淨空")
        self._push_status("連續拍照：重新擷取空桌基準中…請保持桌面淨空。")

    def _observe_autocapture_frame(self, frame: object) -> bool:
        """Feed one preview frame to the detector. Returns True when it took over the
        camera (a capture/restart happened) so the poll loop should stop for this tick."""
        import numpy as np
        from ocr_from2xlsx.autocapture import (
            CAPTURE,
            REARMED,
            FrameMetrics,
            mean_normalized_diff,
            to_metric_gray,
        )
        from ocr_from2xlsx.capture import measure_sharpness

        roi = self._autocapture_detector.config.roi_fraction
        gray = to_metric_gray(frame, roi_fraction=roi)
        if self._autocapture_need_baseline:
            cfg = self._autocapture_detector.config
            samples = self._autocapture_baseline_samples
            if samples and mean_normalized_diff(gray, samples[-1]) >= cfg.motion_thresh:
                samples.clear()  # moved → restart the stable run
            samples.append(gray)
            self._autocapture_prev_gray = gray
            need = cfg.baseline_stable_frames
            if len(samples) >= need:
                self._autocapture_baseline_gray = np.mean(np.stack(samples[-need:]), axis=0)
                self._autocapture_baseline_samples = []
                self._autocapture_need_baseline = False
                self._autocapture_detector.set_baseline()
                self._set_autocapture_state("● 連續拍照中：空桌基準完成，請放上第一張表單")
                self._play_shutter()  # distinct positive signal that the baseline locked (#cc-05)
                self._flash_preview()
                self._push_status("連續拍照：已設定空桌基準｜請放上表單…")
            else:
                self._set_autocapture_state(
                    f"● 連續拍照中：等待空桌基準（{len(samples)}/{need}）請保持桌面淨空"
                )
                self._push_status(
                    f"連續拍照：擷取空桌基準中…（{len(samples)}/{need}）請保持桌面淨空。"
                )
            return False
        motion = mean_normalized_diff(gray, self._autocapture_prev_gray)
        diff_from_baseline = mean_normalized_diff(gray, self._autocapture_baseline_gray)
        self._autocapture_prev_gray = gray
        try:
            sharpness = measure_sharpness(frame)
        except Exception:
            sharpness = 0.0
        action = self._autocapture_detector.observe(
            FrameMetrics(
                motion=motion, diff_from_baseline=diff_from_baseline, sharpness=sharpness
            )
        )
        if action == CAPTURE:
            return self._perform_autocapture()
        if action == REARMED:
            self._set_autocapture_state(
                f"● 連續拍照中：已擷取 {len(self._autocapture_stills)} 張，請放上下一張"
            )
            self._push_status(
                f"連續拍照中｜已擷取 {len(self._autocapture_stills)} 張｜請放上下一張…"
            )
        return False

    def _perform_autocapture(self) -> bool:
        from ocr_from2xlsx.autocapture import STALLED
        from ocr_from2xlsx.capture import DEFAULT_MIN_SHARPNESS, capture_still, rotate_frame
        from ocr_from2xlsx.scan import next_output_artifact_path

        index = self._camera_index
        self._stop_camera()
        self._paint_busy("拍攝中…請勿移動")  # legible feedback during the synchronous capture
        result = None
        try:
            result = capture_still(index, min_sharpness=DEFAULT_MIN_SHARPNESS)
        except Exception as exc:  # noqa: BLE001 - surface and keep the session recoverable
            self._push_status(f"連續拍照擷取失敗：{exc}")
        if result is None:
            self._autocapture_active = False
            self._update_toolbar_states()
            self._set_autocapture_state(
                "⚠ 相機中斷，連拍已停 → 請按【完成辨識】辨識或【取消連拍】放棄", tone="warn"
            )
            self._push_status(
                f"連續拍照：相機中斷，已擷取 {len(self._autocapture_stills)} 張；"
                "可按『完成辨識』辨識，或『取消連拍』放棄。"
            )
            return True
        if not result.passed:
            outcome = self._autocapture_detector.note_failed_capture()
            if outcome == STALLED:
                self._set_autocapture_state(
                    "⏸ 已暫停：連續多張太模糊 → 請按【重設空桌基準】恢復", tone="warn"
                )
                self._push_status(
                    f"連續拍照：連續多張太模糊（清晰度 {result.sharpness:.0f}），已暫停；"
                    "請調整對焦/光線後按『重設空桌基準』。"
                )
            else:
                self._push_status(
                    f"連續拍照：太模糊（清晰度 {result.sharpness:.0f}），自動重試…"
                )
            self._start_camera(index)
            return True

        frame = result.frame
        if self._preview_rotation:
            frame = rotate_frame(frame, self._preview_rotation)
        output_dir = self._autocapture_output_dir
        image_path = next_output_artifact_path(output_dir, "scan-capture.png")
        if not self._imwrite_unicode(image_path, frame):
            outcome = self._autocapture_detector.note_failed_capture()
            if outcome == STALLED:
                self._push_status(
                    f"連續拍照：連續無法寫入影像（{image_path}），已暫停；"
                    "請檢查輸出資料夾後按『重設空桌基準』。"
                )
            else:
                self._push_status(
                    f"連續拍照：無法寫入擷取影像 {image_path}，自動重試…"
                )
            self._start_camera(index)
            return True
        self._autocapture_stills.append(image_path)
        # Baseline stays the empty desk; reset only the motion reference after the reopen.
        self._autocapture_prev_gray = None
        self._autocapture_detector.mark_captured()
        self._play_shutter()
        self._flash_preview()
        self._set_autocapture_state(
            f"● 連續拍照中：已擷取 {len(self._autocapture_stills)} 張，請拿開換下一張"
        )
        self._push_status(
            f"連續拍照中｜已擷取 {len(self._autocapture_stills)} 張｜請拿開換下一張…"
        )
        self._start_camera(index)
        return True

    def _finish_continuous_capture(self) -> None:
        from ocr_from2xlsx.cli import _resolve_template
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.plugin_backend import scan_doc_preprocess_env_overrides
        from ocr_from2xlsx.scan import next_output_artifact_path, prepare_records_from_images

        stills = list(self._autocapture_stills)
        if not self._autocapture_active and not stills:
            self._push_status("尚未開始連續拍照；請先按『連續拍照』。")
            return
        self._stop_camera()
        self._autocapture_active = False
        self._update_toolbar_states()
        self._set_autocapture_state("")
        if not stills:
            messagebox.showwarning("連續拍照", "尚未擷取任何影像，沒有可辨識的內容。")
            return
        json_path = next_output_artifact_path(self._autocapture_output_dir, "scan-prepared.json")
        output_dir = self._autocapture_output_dir

        def prepare(report, on_progress, should_cancel):
            report("結束連拍並辨識中…啟動辨識服務 / 載入模型（首次較久）…")
            backend = self._resolve_recognition_backend(
                json_path, scan_doc_preprocess_env_overrides()
            )
            template = _resolve_template("service_record.v1")
            batch = prepare_records_from_images(
                stills, output_dir, template, backend,
                on_progress=on_progress, should_cancel=should_cancel,
            )
            dump_batch(batch, json_path)
            return list(JsonRecordSource(json_path).records()), json_path

        def on_records(records, json_path_):
            self._autocapture_stills = []  # consumed only on success; kept for retry otherwise
            messagebox.showinfo("辨識完成", f"已辨識 {len(records)} 筆，進入逐張人工校正。")
            self._set_loaded_records(records, json_path_)
            self._push_status(f"連續拍照完成：{len(records)} 筆，請逐筆確認後寫入。")

        self._run_recognition_async(
            prepare,
            message="結束連拍並辨識中…",
            on_records=on_records,
            empty_msg="辨識結果沒有任何紀錄，沒有可辨識的內容。",
            on_empty=lambda: setattr(self, "_autocapture_stills", []),
            error_title="批次辨識失敗",
        )

    def _flash_preview(self) -> None:
        # Flash the viewer canvas green on capture. self.preview is an ImageViewer (#47),
        # not a tk widget, so drive its .canvas. The broad try/except also absorbs headless
        # test harnesses that never set .preview (would trip tk.Tk.__getattr__ recursion).
        try:
            canvas = self.preview.canvas
            canvas.configure(background="#d0ffd0")
            canvas.after(120, lambda: canvas.configure(background="white"))
        except Exception:
            pass

    def _zoom_in_static(self) -> None:
        # Correction-mode buttons drive the static source-image viewer (#47), matching the
        # mouse-wheel step, so zoom is discoverable without knowing about the wheel.
        self.preview.set_zoom(self.preview.zoom + 1)

    def _zoom_out_static(self) -> None:
        self.preview.set_zoom(self.preview.zoom - 1)

    def _reset_static_view(self) -> None:
        self.preview.reset_view()

    def _zoom_crop(self, frame: object):
        # Zoom by cropping a centered region (then the fit-resize scales it up to the pane).
        if self._preview_zoom <= 1.0:
            return frame
        height, width = frame.shape[:2]
        crop_w = max(1, int(width / self._preview_zoom))
        crop_h = max(1, int(height / self._preview_zoom))
        x0 = (width - crop_w) // 2
        y0 = (height - crop_h) // 2
        return frame[y0:y0 + crop_h, x0:x0 + crop_w]

    def _on_close(self) -> None:
        self._dismiss_splash()
        self._stop_camera()
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass
        # Force-kill the process: cv2/DirectShow leaves non-daemon capture threads that
        # otherwise keep this (and the one-file bootloader parent) alive after the window
        # closes — the zombie that holds the camera and locks the exe. Closing the window
        # always routes through here (WM_DELETE_WINDOW), so exit hard once teardown is done.
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(0)


def _close_boot_splash() -> None:
    # Close the PyInstaller native splash (frozen exe only); a no-op when not bundled.
    try:
        import pyi_splash  # type: ignore
    except Exception:
        return
    try:
        pyi_splash.close()
    except Exception:
        pass


def run_app() -> int:
    app = ReviewApp()
    # Heavy startup (cv2 load, camera enumeration) happens in __init__ while the native
    # boot splash is still up. The Tk window only maps once mainloop starts, so dismiss the
    # splash a moment after that — never during __init__, which would leave a blank gap.
    app.after(500, app._dismiss_splash)
    app.mainloop()
    # Force a clean process exit. cv2/DirectShow leaves non-daemon capture threads that
    # otherwise keep the (frozen one-file) process — and its bootloader parent — alive after
    # the window closes, holding the camera and the exe file (zombie processes).
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)
