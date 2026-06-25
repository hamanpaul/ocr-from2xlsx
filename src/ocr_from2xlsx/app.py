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


class ConfirmForm:
    def __init__(
        self,
        parent: tk.Misc,
        layout: FormLayout,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.layout = layout
        self._on_change = on_change
        self.frame = ttk.Frame(parent)
        self.text_fields: dict[str, tk.StringVar] = {}
        self.single_choice_fields: dict[str, tk.StringVar] = {}
        self._single_choice_option_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        self.multi_choice_fields: dict[str, dict[str, tk.BooleanVar]] = {}
        # Field-title labels keyed by record_path, so recognition can flag
        # low-confidence / unfilled fields for the reviewer.
        self._field_labels: dict[str, ttk.Label] = {}
        self._field_titles: dict[str, str] = {}
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

                    for option_index, option in enumerate(field.options):
                        bvar = tk.BooleanVar(value=False)
                        option_vars[option.code] = bvar
                        ttk.Checkbutton(
                            options,
                            text=option.label,
                            variable=bvar,
                            command=lambda code=option.code: _select(code),
                        ).grid(
                            row=option_index // 4,
                            column=option_index % 4,
                            sticky="w",
                            padx=(0, 8),
                            pady=2,
                        )
                    self.single_choice_fields[field.key] = var
                    self._single_choice_option_vars[field.key] = option_vars
                elif field.kind == "multi_choice":
                    options = ttk.Frame(group)
                    options.grid(row=field_row, column=1, sticky="w", pady=3)
                    code_vars: dict[str, tk.BooleanVar] = {}
                    for option_index, option in enumerate(field.options):
                        bvar = tk.BooleanVar(value=False)
                        ttk.Checkbutton(
                            options,
                            text=option.label,
                            variable=bvar,
                            command=self._notify_change,
                        ).grid(
                            row=option_index // 4,
                            column=option_index % 4,
                            sticky="w",
                            padx=(0, 8),
                            pady=2,
                        )
                        code_vars[option.code] = bvar
                    self.multi_choice_fields[field.key] = code_vars
                else:
                    raise TypeError(f"Unsupported field kind: {field.kind!r}")

    def _mark_changed(self, _event: tk.Event | None = None) -> None:
        self._notify_change()

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def set_flagged_fields(self, flagged: dict[str, str]) -> None:
        """Mark fields needing the reviewer's attention (low-confidence / empty /
        unconfirmed) and clear marks on the rest. ``flagged`` maps record_path -> reason."""
        for record_path, label in self._field_labels.items():
            title = self._field_titles[record_path]
            if record_path in flagged:
                label.configure(text=f"⚠ {title}", foreground="#b00020")
            else:
                label.configure(text=title, foreground="")

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
    _toolbar_buttons: object | None = None

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
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=8)

        # Toolbar grouped by workflow phase — 設定 → 掃描 → 校正 — with a small caption per
        # group and vertical separators, so the operator can see where to start instead of
        # facing one undifferentiated 17-button row. View controls are pushed to the right.
        def _group(label: str) -> None:
            ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(6, 4))
            ttk.Label(toolbar, text=label, foreground="#5f6368").pack(side=tk.LEFT, padx=(0, 4))

        self._toolbar_buttons = {}

        def _btn(text: str, command, key: str | None = None) -> None:
            button = ttk.Button(toolbar, text=text, command=command)
            button.pack(side=tk.LEFT, padx=4)
            if key is not None:
                self._toolbar_buttons[key] = button

        # 設定（先做）
        ttk.Label(toolbar, text="設定", foreground="#5f6368").pack(side=tk.LEFT, padx=(0, 4))
        _btn("選擇模板 XLSX", self._choose_template, "choose_template")
        _btn("匯入 JSON", self._load_json, "load_json")
        _btn("選擇攝影機", self._choose_camera, "choose_camera")
        # 掃描
        _group("掃描")
        _btn("擷取並辨識", self._capture_and_recognize, "capture_recognize")
        _btn("連續拍照", self._start_continuous_capture, "start_continuous")
        _btn("完成辨識", self._finish_continuous_capture, "complete_recognize")
        _btn("復原上一張", self._undo_last_continuous_capture, "undo_last")
        _btn("取消連拍", self._cancel_continuous_capture, "cancel_continuous")
        _btn("重設空桌基準", self._reset_baseline, "reset_baseline")
        _btn("匯入資料夾批次", self._import_folder_batch, "import_folder_batch")
        # 校正
        _group("校正")
        _btn("上一筆", self._previous_record, "prev_record")
        _btn("下一筆", self._next_record, "next_record")
        _btn("確認並寫入", self._confirm_current, "confirm")
        _btn("強制寫入", self._force_write, "force")
        # 預覽（靠右，與寫入/掃描動作分開）
        ttk.Button(toolbar, text="縮小", command=lambda: self._zoom_preview(1 / 1.25)).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(toolbar, text="放大", command=lambda: self._zoom_preview(1.25)).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(toolbar, text="旋轉", command=self._rotate_preview).pack(side=tk.RIGHT, padx=4)

        # Footer status bar: shows only the latest status; full history goes to the log file.
        self._status_var = tk.StringVar(
            value="請先按『選擇模板 XLSX』，再按『選擇攝影機』開始掃描。"
        )
        ttk.Label(self, textvariable=self._status_var, anchor="w", relief="sunken").pack(
            side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8)
        )

        # Two maximized panes: webcam/source preview on the left, the review form on the right.
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.preview = tk.Text(body, width=60, wrap="word")
        self._show_placeholder_preview()
        body.add(self.preview, weight=1)

        form = ttk.Frame(body)
        body.add(form, weight=1)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(0, weight=1)

        canvas = tk.Canvas(form, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(form, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        self.confirm_form = ConfirmForm(canvas, self.layout, on_change=self._mark_editing)
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
        self._push_status(f"工作檔: {working}")
        self._update_toolbar_states()  # template ready → write buttons can enable

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
                messagebox.showerror("擷取並辨識", str(exc))
                return
            self._clear_inactive_camera_selection()
            messagebox.showwarning("擷取並辨識", "請先選擇可用的攝影機。")
            return
        should_restore_preview = restore_live_preview
        self._paint_busy("擷取中…請稍候")  # legible feedback before the blocking capture freeze
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
            self._play_shutter()  # same moment-of-capture cue as continuous mode
            self._flash_preview()
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
        if self.current_index in self.written_indices:
            messagebox.showinfo("提示", "目前資料已寫入，請切換下一筆。")
            return
        record = self.records[self.current_index]
        self._apply_form_to_record(record)
        human_confirmed = self._needs_name_confirmation(record)
        try:
            result = self.session.accept_scan(record, human_confirmed=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("寫入失敗", str(exc))
            return
        self._push_status(f"{result.record_id}: {result.status} row={result.row_number} blockers={result.blockers}")
        if result.status == "blocked":
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
            self.editing = False
            working = getattr(getattr(self.session, "writer", None), "working_path", "")
            self._push_status(f"已寫入工作檔 {working} 第 {result.row_number} 列")
            self._next_record()

    def _force_write(self) -> None:
        if not self.session:
            messagebox.showerror("缺少工作檔", "請先選擇模板 XLSX。")
            return
        if self.current_index < 0 or self.current_index >= len(self.records):
            messagebox.showerror("缺少資料", "請先載入 JSON 資料。")
            return
        if self.current_index in self.written_indices:
            messagebox.showinfo("提示", "目前資料已寫入，請切換下一筆。")
            return
        record = self.records[self.current_index]
        self._apply_form_to_record(record)
        human_confirmed = self._needs_name_confirmation(record)
        try:
            result = self.session.accept_scan(record, force=True, human_confirmed=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("寫入失敗", str(exc))
            return
        self._push_status(f"{result.record_id}: {result.status} row={result.row_number} blockers={result.blockers}")
        if result.status in {"forced", "written"}:
            if human_confirmed:
                self._persist_confirmed_name_after_write(record)
            self.written_indices.add(self.current_index)
            self.editing = False

    def _show_record(self, record: Record) -> None:
        self.fields["record_id"].set(record.record_id)
        self.confirm_form.prefill(record_to_form_state(self.layout, record))
        self.confirm_form.set_flagged_fields(
            flagged_fields(list(record.ocr.warnings), SERVICE_RECORD_V1_LAYOUT)
        )
        self._show_source_image(record)
        self.editing = False
        self._update_toolbar_states()

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

            self.preview.update_idletasks()
            target_width = self.preview.winfo_width()
            target_height = self.preview.winfo_height()
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
            self.preview.configure(state="normal")
            self.preview.delete("1.0", tk.END)
            self.preview.image_create("1.0", image=image)
            self.preview.configure(state="disabled")
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
        self.preview.configure(state="normal")
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", self._PREVIEW_PLACEHOLDER)
        self.preview.configure(state="disabled")

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
            self.preview.update_idletasks()
            target_width = self.preview.winfo_width()
            target_height = self.preview.winfo_height()
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
            self.preview.configure(state="normal")
            self.preview.delete("1.0", tk.END)
            self.preview.image_create("1.0", image=image)
            self.preview.configure(state="disabled")
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
        btns = getattr(self, "_toolbar_buttons", None)
        if not btns:
            return
        active = bool(getattr(self, "_autocapture_active", False))
        has_stills = bool(getattr(self, "_autocapture_stills", None))
        has_session = getattr(self, "session", None) is not None
        records = getattr(self, "records", ()) or ()
        written = getattr(self, "written_indices", frozenset()) or frozenset()
        idx = getattr(self, "current_index", -1)
        valid_record = 0 <= idx < len(records)

        def _set(key: str, enabled: bool) -> None:
            button = btns.get(key)
            if button is not None:
                try:
                    button.configure(state="normal" if enabled else "disabled")
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
                messagebox.showerror("連續拍照", str(exc))
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
                self._push_status("連續拍照：已設定空桌基準｜請放上表單…")
            else:
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
            self._push_status(
                f"連續拍照：相機中斷，已擷取 {len(self._autocapture_stills)} 張；"
                "可按『完成辨識』辨識，或『取消連拍』放棄。"
            )
            return True
        if not result.passed:
            outcome = self._autocapture_detector.note_failed_capture()
            if outcome == STALLED:
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
        if not stills:
            messagebox.showwarning("連續拍照", "尚未擷取任何影像，沒有可辨識的內容。")
            return
        json_path = next_output_artifact_path(self._autocapture_output_dir, "scan-prepared.json")
        modal = self._open_processing_modal("批次辨識中…")
        try:
            backend = self._resolve_recognition_backend(
                json_path, scan_doc_preprocess_env_overrides()
            )
            template = _resolve_template("service_record.v1")

            def _progress(done: int, total: int, name: str) -> None:
                self._set_modal_message(modal, f"批次辨識中… {done}/{total}\n{name}")

            batch = prepare_records_from_images(
                stills, self._autocapture_output_dir, template, backend, on_progress=_progress
            )
            dump_batch(batch, json_path)
        except Exception as exc:  # noqa: BLE001 - keep the stills for a retry
            self._close_processing_modal(modal)
            messagebox.showerror(
                "批次辨識失敗", f"{exc}\n（已擷取的影像保留，可再次按『完成辨識』重試。）"
            )
            return
        else:
            self._close_processing_modal(modal)
        records = list(JsonRecordSource(json_path).records())
        if not records:
            self._autocapture_stills = []
            messagebox.showwarning("沒有可辨識的影像", "辨識結果沒有任何紀錄。")
            return
        self._autocapture_stills = []  # consumed
        messagebox.showinfo("辨識完成", f"已辨識 {len(records)} 筆，進入逐張人工校正。")
        self._set_loaded_records(records, json_path)
        self._push_status(f"連續拍照完成：{len(records)} 筆，請逐筆確認後寫入。")

    def _flash_preview(self) -> None:
        try:
            self.preview.configure(background="#d0ffd0")
            self.preview.after(120, lambda: self.preview.configure(background="white"))
        except Exception:
            pass

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
