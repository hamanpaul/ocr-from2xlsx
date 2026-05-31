from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ocr_from2xlsx.capture import JsonRecordSource
from ocr_from2xlsx.correction_store import default_correction_store_path
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import FormLayout
from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED, confirm_name
from ocr_from2xlsx.session import ImportSession


class ConfirmForm:
    def __init__(self, parent: tk.Misc, layout: FormLayout) -> None:
        self.layout = layout
        self.frame = ttk.Frame(parent)
        self.text_fields: dict[str, tk.StringVar] = {}
        self.single_choice_fields: dict[str, tk.StringVar] = {}
        self.multi_choice_fields: dict[str, dict[str, tk.BooleanVar]] = {}
        self.frame.columnconfigure(0, weight=1)

        for section_row, section in enumerate(layout.sections):
            group = ttk.LabelFrame(self.frame, text=f"{section.id} {section.title}")
            group.grid(row=section_row, column=0, sticky="ew", padx=4, pady=4)
            group.columnconfigure(1, weight=1)
            for field_row, field in enumerate(section.fields):
                ttk.Label(group, text=field.title).grid(
                    row=field_row, column=0, sticky="nw", padx=(0, 8), pady=3
                )
                if field.kind == "text":
                    var = tk.StringVar()
                    ttk.Entry(group, textvariable=var, width=30).grid(
                        row=field_row, column=1, sticky="ew", pady=3
                    )
                    self.text_fields[field.key] = var
                elif field.kind == "single_choice":
                    var = tk.StringVar(value="")
                    options = ttk.Frame(group)
                    options.grid(row=field_row, column=1, sticky="w", pady=3)
                    for option_index, option in enumerate(field.options):
                        ttk.Radiobutton(
                            options,
                            text=option.label,
                            value=option.code,
                            variable=var,
                        ).grid(
                            row=option_index // 4,
                            column=option_index % 4,
                            sticky="w",
                            padx=(0, 8),
                            pady=2,
                        )
                    self.single_choice_fields[field.key] = var
                elif field.kind == "multi_choice":
                    options = ttk.Frame(group)
                    options.grid(row=field_row, column=1, sticky="w", pady=3)
                    code_vars: dict[str, tk.BooleanVar] = {}
                    for option_index, option in enumerate(field.options):
                        bvar = tk.BooleanVar(value=False)
                        ttk.Checkbutton(options, text=option.label, variable=bvar).grid(
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

    def prefill(self, state: dict[str, object]) -> None:
        for key, var in self.text_fields.items():
            value = state.get(key, "")
            var.set("" if value is None else str(value))
        for key, var in self.single_choice_fields.items():
            value = state.get(key, "")
            var.set("" if value is None else str(value))
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
    def __init__(self) -> None:
        super().__init__()
        self.title("OCR from Service Record to XLSX")
        self.geometry("1200x720")
        self.records: list[Record] = []
        self.current_index = -1
        self.session: ImportSession | None = None
        self.loaded_json_path: Path | None = None
        self.correction_store_path: Path | None = None
        self.editing = False
        self.written_indices: set[int] = set()
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
        ttk.Button(toolbar, text="下一張 / 確認目前資料", command=self._next_record).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="強制寫入", command=self._force_write).pack(side=tk.LEFT, padx=4)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.preview = tk.Text(body, width=35)
        self.preview.insert("1.0", "攝影機或圖片預覽區\n第一版可用 JSON 模擬連續掃描。")
        self.preview.configure(state="disabled")
        body.add(self.preview)

        form = ttk.Frame(body)
        body.add(form)
        form.columnconfigure(1, weight=1)
        for row, key in enumerate(
            ["record_id", "service_date", "identity", "name", "medical_record_no", "gender"]
        ):
            ttk.Label(form, text=key).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            entry = ttk.Entry(form, textvariable=var, width=40)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            entry.bind("<Key>", self._mark_editing)
            self.fields[key] = var

        status_frame = ttk.Frame(body)
        body.add(status_frame)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        self.status_list = tk.Listbox(status_frame, width=50)
        self.status_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.status_list.configure(yscrollcommand=scrollbar.set)

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

    def _load_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            self.records = list(JsonRecordSource(path).records())
        except (OSError, ValueError) as exc:
            messagebox.showerror("無法載入 JSON", str(exc))
            return
        self.loaded_json_path = Path(path)
        self.correction_store_path = default_correction_store_path(self.loaded_json_path)
        self.current_index = -1
        self.editing = False
        self.written_indices = set()
        self._push_status(f"已載入 {len(self.records)} 筆 JSON")
        self._next_record()

    def _next_record(self) -> None:
        if not self.records:
            messagebox.showerror("缺少資料", "請先載入 JSON 資料。")
            return
        if self.editing:
            messagebox.showerror("尚未保存", "目前資料已修改，請先使用「強制寫入」。")
            return
        if self.session and self.current_index >= 0:
            if self.current_index not in self.written_indices:
                current = self.records[self.current_index]
                try:
                    human_confirmed = self._needs_name_confirmation(current)
                    if human_confirmed:
                        result = self.session.accept_scan(current, human_confirmed=True)
                    else:
                        result = self.session.accept_scan(current)
                except (OSError, ValueError) as exc:
                    messagebox.showerror("寫入失敗", str(exc))
                    return
                self._push_status(
                    f"{current.record_id}: {result.status} row={result.row_number} blockers={result.blockers}"
                )
                if result.status == "blocked":
                    return
                if result.status in {"forced", "written"}:
                    if human_confirmed:
                        self._persist_confirmed_name_after_write(current)
                    self.written_indices.add(self.current_index)
        self.editing = False
        self.current_index += 1
        if self.current_index >= len(self.records):
            messagebox.showinfo("完成", "沒有更多資料。")
            return
        self._show_record(self.records[self.current_index])

    def _force_write(self) -> None:
        if not self.session:
            messagebox.showerror("缺少工作檔", "請先選擇模板 XLSX。")
            return
        if self.current_index < 0:
            messagebox.showerror("缺少資料", "請先載入 JSON 資料。")
            return
        if self.current_index in self.written_indices:
            messagebox.showinfo("提示", "目前資料已寫入，請切換下一筆。")
            return
        record = self.records[self.current_index]
        self._apply_form_to_record(record)
        try:
            human_confirmed = self._needs_name_confirmation(record)
            if human_confirmed:
                result = self.session.accept_scan(record, force=True, human_confirmed=True)
            else:
                result = self.session.accept_scan(record, force=True)
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
        self.fields["service_date"].set(record.service_date)
        self.fields["identity"].set(record.identity)
        self.fields["name"].set(record.name)
        self.fields["medical_record_no"].set(record.medical_record_no)
        self.fields["gender"].set(record.gender)
        self.editing = False

    def _apply_form_to_record(self, record: Record) -> None:
        record.record_id = self.fields["record_id"].get()
        record.service_date = self.fields["service_date"].get()
        record.identity = self.fields["identity"].get()
        record.name = self.fields["name"].get()
        record.medical_record_no = self.fields["medical_record_no"].get()
        record.gender = self.fields["gender"].get()
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

    def _push_status(self, message: str) -> None:
        self.status_list.insert(tk.END, message)
        self.status_list.see(tk.END)

    def _on_close(self) -> None:
        if self.session:
            self.session.close()
        self.destroy()


def run_app() -> int:
    app = ReviewApp()
    app.mainloop()
    return 0
