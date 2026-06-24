from __future__ import annotations

import os
import sys
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
            group = ttk.LabelFrame(self.frame, text=f"{section.id} {section.title}")
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
        self._image: tk.PhotoImage | None = None
        self._display_image: tk.PhotoImage | None = None
        self._image_size = (0, 0)
        self._view_size = (1, 1)
        self._drag_anchor: tuple[int, int] | None = None
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)

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

    def frame_region(self, band: tuple[float, float, float, float]) -> None:
        from ocr_from2xlsx.image_viewer import clamp_zoom

        if self.mode != "static" or self._image is None:
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

    def _on_wheel(self, event: "tk.Event") -> str:
        from ocr_from2xlsx.image_viewer import anchored_origin, clamp_zoom

        if self.mode != "static" or self._image is None:
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
        if self._image is None:
            return
        try:
            self.canvas.delete("all")
            if self.mode == "live":
                self._display_image = self._image
                self.canvas.create_image(0, 0, anchor="nw", image=self._image)
                return
            factor = max(1, int(round(self.zoom)))
            display = self._image if factor == 1 else self._image.zoom(factor, factor)
            self._display_image = display  # hold a reference so Tk does not GC it
            self.canvas.create_image(
                int(-self.origin[0] * factor),
                int(-self.origin[1] * factor),
                anchor="nw",
                image=display,
            )
        except tk.TclError:
            pass


class ReviewApp(tk.Tk):
    _PREVIEW_PLACEHOLDER = "攝影機或圖片預覽區\n第一版可用 JSON 模擬連續掃描。"
    _CAMERA_POLL_INTERVAL_MS = 33
    _CAMERA_RETRY_INTERVAL_MS = 100
    _CAMERA_FAILURE_LIMIT = 3
    _camera_capture: object | None = None
    _camera_after_id: str | None = None
    _camera_failure_count: int = 0
    _camera_index: int | None = None
    _preview_rotation: int = 0
    _preview_zoom: float = 1.0
    _splash_closed: bool = False
    _status_var: object | None = None
    _status_log_path: object | None = None
    # Name-correction aids (#46); class-level defaults so headless ReviewApp.__new__
    # instances (no Tk) resolve them without tripping tk.Tk.__getattr__ recursion.
    _name_crop_label: object | None = None
    _roster_listbox: object | None = None
    # Same guard for the colored badge label + mode indicator widgets (UX pass): code
    # reads these via getattr on headless instances, so they need class-level defaults.
    _badge_label: object | None = None
    _mode_toggle: object | None = None
    _mode_var: object | None = None
    # Mode-gated shortcuts read this on headless instances, so it needs a class default
    # to avoid the tk.Tk.__getattr__ recursion; __init__/_set_review_mode set the instance.
    _review_mode: str = "correction"

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
        self._splash_closed = False
        self._status_log: list[str] = []
        self._status_var = None
        self._status_log_path = self._default_status_log_path()
        self.fields: dict[str, tk.StringVar] = {}
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(toolbar, text="選擇模板 XLSX", command=self._choose_template).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="匯入 JSON", command=self._load_json).pack(side=tk.LEFT, padx=4)
        # Mode-specific toolbar buttons (#44): scan-station vs. correction controls are
        # shown/hidden by review mode so correction is uncluttered and mis-clicks (e.g.
        # 擷取並辨識 mid-review) are impossible. Setup buttons + the toggle stay visible.
        self._mode_buttons: dict[str, ttk.Button] = {}
        button_specs: dict[str, tuple[str, object]] = {
            "prev_record": ("上一筆", self._previous_record),
            "next_record": ("下一筆", self._next_record),
            "confirm": ("確認並寫入", self._confirm_current),
            "force_write": ("強制寫入", self._force_write),
            "choose_camera": ("選擇攝影機", self._choose_camera),
            "capture_recognize": ("擷取並辨識", self._capture_and_recognize),
            "import_folder_batch": ("匯入資料夾批次", self._import_folder_batch),
            "rotate": ("旋轉", self._rotate_preview),
            "zoom_in": ("放大", lambda: self._zoom_preview(1.25)),
            "zoom_out": ("縮小", lambda: self._zoom_preview(1 / 1.25)),
        }
        for key, (label, command) in button_specs.items():
            self._mode_buttons[key] = ttk.Button(toolbar, text=label, command=command)
        # Toggle names the action it performs (next mode), so the operator can tell the
        # current mode from the button alone (#44); _set_review_mode keeps its text in sync.
        self._mode_toggle = ttk.Button(toolbar, command=self._toggle_review_mode)
        self._mode_toggle.pack(side=tk.LEFT, padx=4)
        self._review_mode = "correction"
        self._set_review_mode("correction")

        # Discoverability (#42): a persistent 快捷鍵 cheat-sheet button (right edge, out of
        # the way of the #44 decluttering) + hover tooltips that also clarify 確認 vs 強制
        # 寫入 (#48), without changing the button labels existing tests assert on.
        ttk.Button(toolbar, text="快捷鍵", command=self._show_shortcut_help).pack(
            side=tk.RIGHT, padx=4
        )
        button_tooltips = {
            "confirm": "Enter / Ctrl+Enter：驗證必填欄位後寫入；缺漏會被擋下",
            "force_write": "F2 / Ctrl+Shift+Enter：跳過必填檢查強制寫入，可能寫入不完整資料",
            "prev_record": "PgUp / Ctrl+←：上一筆",
            "next_record": "PgDn / Ctrl+→：下一筆",
        }
        for key, hint in button_tooltips.items():
            _Tooltip(self._mode_buttons[key], hint)

        # Footer status bar: shows only the latest status; full history goes to the log file.
        footer = ttk.Frame(self)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        # Persistent mode indicator (#44): which mode the operator is in, at a glance.
        self._mode_var = tk.StringVar(value="模式：校正")
        ttk.Label(footer, textvariable=self._mode_var, anchor="w", relief="sunken").pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._status_var = tk.StringVar(value="就緒")
        ttk.Label(footer, textvariable=self._status_var, anchor="w", relief="sunken").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        # Exception-first review (#43): how many fields on this record still need a human.
        self._pending_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self._pending_var, anchor="e", relief="sunken").pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        # Persistent batch progress baseline (#45): always show a count, even before load.
        self._progress_var = tk.StringVar(value="尚未載入資料")
        ttk.Label(footer, textvariable=self._progress_var, anchor="e", relief="sunken").pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        # Colored per-record status badge (#45): 已寫入/被擋下/待處理 read at a glance via
        # background color, not identical grey text. tk.Label honors bg across themes.
        self._badge_var = tk.StringVar(value="")
        self._badge_label = tk.Label(
            footer, textvariable=self._badge_var, anchor="e", relief="sunken", padx=6
        )
        self._badge_label.pack(side=tk.RIGHT, padx=(8, 0))

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

        # Name-correction aids (#46): a zoomed name crop + selectable roster candidates,
        # pinned above the scrollable form (the most-corrected field gets the most help).
        name_aids = ttk.LabelFrame(form, text="姓名校正")
        name_aids.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        name_aids.columnconfigure(1, weight=1)
        self._name_crop_label = ttk.Label(name_aids, text="（無姓名裁圖）", anchor="center")
        self._name_crop_label.grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self._roster_listbox = tk.Listbox(name_aids, height=4, exportselection=False)
        self._roster_listbox.grid(row=0, column=1, padx=6, pady=4, sticky="ew")
        # Browse vs. commit (#46): arrow keys / single clicks only move the highlight;
        # Enter or double-click commits the candidate. Avoids overwriting the name field
        # the instant focus lands on the list or an arrow is pressed.
        self._roster_listbox.bind("<Return>", self._on_roster_commit)
        self._roster_listbox.bind("<Double-Button-1>", self._on_roster_commit)

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

    def _set_review_mode(self, mode: str) -> None:
        from ocr_from2xlsx.review_workflow import (
            correction_mode_controls,
            scan_mode_controls,
        )

        self._review_mode = mode
        visible = set(
            correction_mode_controls() if mode == "correction" else scan_mode_controls()
        )
        for key, button in self._mode_buttons.items():
            if key in visible:
                button.pack(side=tk.LEFT, padx=4)
            else:
                button.pack_forget()
        # Reflect the current mode on the toggle button + footer (#44). getattr-guarded
        # because _set_review_mode runs once during _build_ui before the footer exists.
        label = "校正" if mode == "correction" else "掃描"
        toggle = getattr(self, "_mode_toggle", None)
        if toggle is not None:
            try:
                toggle.configure(
                    text="切換到掃描站 (F4)" if mode == "correction" else "切換到校正 (F4)"
                )
            except Exception:
                pass
        mode_var = getattr(self, "_mode_var", None)
        if mode_var is not None:
            try:
                mode_var.set(f"模式：{label}")
            except Exception:
                pass

    def _toggle_review_mode(self) -> None:
        self._set_review_mode("scan" if self._review_mode == "correction" else "correction")

    def _show_shortcut_help(self) -> None:
        messagebox.showinfo(
            "鍵盤快捷鍵",
            "Enter / Ctrl+Enter　確認並寫入\n"
            "F2 / Ctrl+Shift+Enter　強制寫入\n"
            "PgDn / PgUp（或 Ctrl+→ / Ctrl+←）　下一筆 / 上一筆\n"
            "Esc　取消本筆編輯\n"
            "Ctrl+Tab / Ctrl+Shift+Tab　跳下一個 / 上一個待確認欄位\n"
            "數字鍵 1–N　選擇單選欄選項；空白鍵　切換多選欄\n"
            "F4　切換 掃描 / 校正 模式\n"
            "F8　跳到姓名候選清單（方向鍵選、Enter 套用）",
        )

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
        # Mode switching from the keyboard (#44): a keyboard-first station should not need
        # the mouse to flip 掃描<->校正. F4 chosen to avoid colliding with Return (Ctrl+M).
        self.bind("<F4>", self._on_toggle_mode_key)
        # Jump into the name roster (#46) so candidates are reachable without the mouse.
        self.bind("<F8>", self._on_focus_roster_key)

    def _correction_active(self) -> bool:
        # Correction-action shortcuts only fire in correction mode (#44); scan mode swallows
        # them so a stray Enter/F2/PgDn during capture can't write or navigate records.
        return getattr(self, "_review_mode", "correction") == "correction"

    def _on_confirm_key(self, _event: "tk.Event | None" = None) -> str:
        if self._correction_active():
            self._confirm_current()
        return "break"

    def _on_force_key(self, _event: "tk.Event | None" = None) -> str:
        if self._correction_active():
            self._force_write()
        return "break"

    def _on_next_record_key(self, _event: "tk.Event | None" = None) -> str:
        if self._correction_active():
            self._next_record()
        return "break"

    def _on_prev_record_key(self, _event: "tk.Event | None" = None) -> str:
        if self._correction_active():
            self._previous_record()
        return "break"

    def _on_toggle_mode_key(self, _event: "tk.Event | None" = None) -> str:
        self._toggle_review_mode()
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
        # whole record (image re-frame, roster rebuild, focus jump): a one-field undo
        # should not yank the operator out of their current context.
        if self.current_index < 0 or self.current_index >= len(self.records):
            self.editing = False
            return
        if not self.editing:
            self._push_status("無可取消的編輯")
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
                pending_var.set(f"待確認 {count}" if count else "")
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

    def _roster_candidates_for(self, record: Record) -> list[str]:
        # Confirmed-name roster (from the correction store) ranked against this record's
        # current name, for the selectable suggestions beside the name field (#46).
        from ocr_from2xlsx.correction_store import roster_from_store
        from ocr_from2xlsx.review_workflow import rank_roster_candidates

        store = self.correction_store_path
        if store is None:
            return []
        try:
            roster = roster_from_store(store)
        except (OSError, ValueError):
            return []
        return rank_roster_candidates(record.name, roster)

    def _apply_roster_choice(self, name: str) -> None:
        # Fill the name field from a roster pick and clear the unconfirmed-name marker (#46).
        chosen = (name or "").strip()
        if not chosen:
            return
        self.fields["name"].set(chosen)
        if 0 <= self.current_index < len(self.records):
            record = self.records[self.current_index]
            record.ocr.warnings = [w for w in record.ocr.warnings if w != NAME_UNCONFIRMED]
            # Name no longer unconfirmed: refresh the ⚠/grey marks and the "待確認 N" count
            # so they reflect the pick immediately (#46), mirroring _show_record.
            self.confirm_form.set_flagged_fields(
                flagged_fields(list(record.ocr.warnings), SERVICE_RECORD_V1_LAYOUT)
            )
            self._update_pending_count()
        self.editing = True
        # Return focus to the name field so the operator can keep typing / advance, instead
        # of leaving focus trapped on the listbox where arrows would re-browse candidates.
        self._focus_name_field()

    def _focus_name_field(self) -> None:
        focus_widgets = getattr(self.confirm_form, "_focus_widgets", None)
        if not isinstance(focus_widgets, dict):
            return
        widget = focus_widgets.get("name")
        if widget is None:
            return
        try:
            widget.focus_set()
            widget.icursor("end")
        except Exception:
            pass

    def _on_roster_commit(self, _event: "tk.Event | None" = None) -> str:
        listbox = self._roster_listbox
        if listbox is None:
            return "break"
        try:
            selection = listbox.curselection()
            index = selection[0] if selection else listbox.index(tk.ACTIVE)
            self._apply_roster_choice(listbox.get(index))
        except tk.TclError:
            pass
        return "break"  # stop Return from also firing the window-level 確認並寫入

    def _on_focus_roster_key(self, _event: "tk.Event | None" = None) -> str:
        # F8 moves the keyboard into the roster so pure-keyboard operators can reach the
        # candidates; arrows browse, Enter commits, then focus returns to the name field (#46).
        listbox = self._roster_listbox
        if listbox is None:
            return "break"
        try:
            if listbox.size() > 0:
                listbox.focus_set()
                listbox.activate(0)
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(0)
        except Exception:
            pass
        return "break"

    def _update_name_aids(self, record: Record) -> None:
        # Populate the roster suggestions and the zoomed name-crop preview (#46).
        listbox = self._roster_listbox
        if listbox is not None:
            try:
                listbox.delete(0, tk.END)
                for candidate in self._roster_candidates_for(record):
                    listbox.insert(tk.END, candidate)
            except tk.TclError:
                pass
        self._show_name_crop(record)

    def _show_name_crop(self, record: Record) -> None:
        label = self._name_crop_label
        if label is None:
            return
        try:
            relative = record.ocr.name_crop
            if not relative or self.loaded_json_path is None:
                label.configure(image="", text="（無姓名裁圖）")
                self._name_crop_image = None
                return
            crop_path = self.loaded_json_path.parent / relative
            if crop_path.suffix.lower() != ".png" or not crop_path.is_file():
                label.configure(image="", text="（無姓名裁圖）")
                self._name_crop_image = None
                return
            image = tk.PhotoImage(file=str(crop_path))
            if image.width() < 240:
                image = image.zoom(2, 2)  # enlarge small crops so handwriting is legible
            self._name_crop_image = image
            label.configure(image=image, text="")
        except Exception:
            try:
                label.configure(image="", text="（無姓名裁圖）")
            except tk.TclError:
                pass
            self._name_crop_image = None

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
                messagebox.showerror("擷取並辨識", str(exc))
                return
            self._clear_inactive_camera_selection()
            messagebox.showwarning("擷取並辨識", "請先選擇可用的攝影機。")
            return
        should_restore_preview = restore_live_preview
        self._stop_camera()
        try:
            result = capture_still(
                restore_camera_index,
                min_sharpness=DEFAULT_MIN_SHARPNESS,
            )
            if result is None:
                should_restore_preview = False
                self._clear_inactive_camera_selection()
                messagebox.showwarning("擷取並辨識", "找不到可用的攝影機。")
                return
            if not result.passed:
                messagebox.showwarning(
                    "擷取並辨識",
                    f"畫面太模糊（清晰度 {result.sharpness:.0f}）。請調整對焦/光線/距離後重試。",
                )
                return
            recognized = self._recognize_capture(result.frame)
            should_restore_preview = restore_live_preview and not recognized
        except CameraDependencyError as exc:
            should_restore_preview = False
            self._clear_inactive_camera_selection()
            messagebox.showerror("擷取並辨識", str(exc))
        except Exception as exc:
            messagebox.showerror("擷取並辨識", f"辨識失敗：{exc}")
        finally:
            if should_restore_preview:
                if restore_camera_index is None:
                    self._init_camera()
                else:
                    self._start_camera(restore_camera_index)

    def _recognize_capture(self, frame: object) -> bool:
        import cv2

        from ocr_from2xlsx.cli import _resolve_template
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.plugin_backend import (
            PluginOcrBackend,
            scan_doc_preprocess_env_overrides,
        )
        from ocr_from2xlsx.scan import next_output_artifact_path, prepare_records_from_images

        selected_dir = filedialog.askdirectory(title="選擇辨識輸出資料夾")
        if not selected_dir:
            return False
        output_dir = Path(selected_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = next_output_artifact_path(output_dir, "scan-capture.png")
        if self._preview_rotation:
            from ocr_from2xlsx.capture import rotate_frame

            frame = rotate_frame(frame, self._preview_rotation)
        if not cv2.imwrite(str(image_path), frame):
            raise OSError(f"無法寫入擷取影像：{image_path}")
        env_overrides = scan_doc_preprocess_env_overrides()
        modal = self._open_processing_modal(
            "辨識中，請稍候…\n首次辨識需載入模型，可能需要數十秒。"
        )
        try:
            try:
                backend = self._resolve_recognition_backend(image_path, env_overrides)
            except Exception as exc:
                raise RuntimeError(
                    "找不到可用的 OCR plugin。請先建置 plugin bundle："
                    "python build/build_paddle_plugin.py（產生 dist/plugins/paddleocr）。"
                ) from exc
            template = _resolve_template("service_record.v1")
            batch = prepare_records_from_images([image_path], output_dir, template, backend)
            json_path = next_output_artifact_path(output_dir, "scan-prepared.json")
            dump_batch(batch, json_path)
        finally:
            self._close_processing_modal(modal)
        records = list(JsonRecordSource(json_path).records())
        if not records:
            raise ValueError("辨識結果沒有任何紀錄。")
        self._set_loaded_records(records, json_path)
        return True

    def _resolve_recognition_backend(self, roster_path, env_overrides):
        # Shared by single-capture and batch import: default to the local vision
        # backend when a bundled/running VLM is available; fall back to the plugin.
        from ocr_from2xlsx.recognition.factory import vision_config_from_env
        from ocr_from2xlsx.recognition.vlm_server import ensure_server, vision_runtime_available

        vlm_host = vision_config_from_env()[0]
        backend_choice = os.environ.get("OCR_BACKEND", "").strip().lower()
        if backend_choice == "vision" or (
            backend_choice != "plugin" and vision_runtime_available(vlm_host)
        ):
            from ocr_from2xlsx.cli import _build_vision_backend

            ensure_server(vlm_host)
            return _build_vision_backend(roster_path)
        from ocr_from2xlsx.plugin_backend import PluginOcrBackend

        if env_overrides is None:
            return PluginOcrBackend.resolve()
        return PluginOcrBackend.resolve(env_overrides=env_overrides)

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
        modal = self._open_processing_modal("批次辨識中…")
        try:
            backend = self._resolve_recognition_backend(
                json_path, scan_doc_preprocess_env_overrides()
            )
            template = _resolve_template("service_record.v1")

            def _progress(done: int, total: int, name: str) -> None:
                self._set_modal_message(modal, f"批次辨識中… {done}/{total}\n{name}")

            batch = prepare_records_from_folder(
                Path(input_dir), output_dir, template, backend, on_progress=_progress
            )
            dump_batch(batch, json_path)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the user
            self._close_processing_modal(modal)
            messagebox.showerror("批次辨識失敗", str(exc))
            return
        else:
            self._close_processing_modal(modal)
        records = list(JsonRecordSource(json_path).records())
        if not records:
            messagebox.showwarning("沒有可辨識的檔案", "所選資料夾沒有圖片或 PDF。")
            return
        self._set_loaded_records(records, json_path)
        self._push_status(f"批次辨識完成：{len(records)} 筆，請逐筆確認後寫入。")

    def _open_processing_modal(self, message: str):
        # Global modal "processing" indicator during the blocking OCR call. Defensive: returns
        # None when there is no real Tk root (e.g. unit-test fixtures), so callers stay testable.
        try:
            modal = tk.Toplevel(self)
        except Exception:
            return None
        try:
            modal.title("處理中")
            modal.transient(self)
            modal.resizable(False, False)
            label = ttk.Label(modal, text=message, padding=24, justify="center")
            label.pack()
            modal._message_label = label
            modal.update_idletasks()
            modal.grab_set()  # global input lock while recognizing
            modal.update()  # force a draw before the blocking OCR call
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
            modal.grab_release()
            modal.destroy()
        except Exception:
            pass

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
        self._update_pending_count()
        self._update_progress()
        self._update_badge()
        self._update_name_aids(record)
        # Only grab focus + re-frame the scan when there is something to confirm. A clean
        # (0-flagged) record stays at a neutral overview so the operator can glance and hit
        # Enter, instead of the caret being yanked into the first field (#43).
        if self.confirm_form.flagged_count() > 0:
            self.confirm_form.focus_first_flagged()

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
        self._fail_camera_preview(message)

    def _fail_camera_preview(self, message: str) -> None:
        self._push_status(message)
        self._show_placeholder_preview()
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
            if image_path.suffix.lower() != ".png" or not image_path.is_file():
                self._show_placeholder_preview()
                return

            image = tk.PhotoImage(file=str(image_path))
            self.preview.canvas.update_idletasks()
            target_width = self.preview.canvas.winfo_width()
            target_height = self.preview.canvas.winfo_height()
            if target_width <= 1:
                target_width = 360
            if target_height <= 1:
                target_height = 640

            scale_x = max(1, (image.width() + target_width - 1) // target_width)
            scale_y = max(1, (image.height() + target_height - 1) // target_height)
            scale = max(scale_x, scale_y)
            if scale > 1:
                image = image.subsample(scale, scale)

            self._stop_camera()
            self._preview_image = image
            self.preview.show_image(image)  # static: drag-pan + wheel-zoom, remembered zoom
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

    def _rotate_preview(self) -> None:
        self._preview_rotation = (self._preview_rotation + 90) % 360
        self._save_preview_rotation()
        self._push_status(f"預覽旋轉 {self._preview_rotation}°（已記住，下次啟動沿用）")

    def _zoom_preview(self, factor: float) -> None:
        self._preview_zoom = min(8.0, max(1.0, self._preview_zoom * factor))
        self._push_status(f"預覽縮放 {self._preview_zoom:.2f}×")

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
