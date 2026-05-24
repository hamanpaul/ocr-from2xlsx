from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ocr_from2xlsx.capture import JsonRecordSource
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.session import ImportSession


class ReviewApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OCR from Service Record to XLSX")
        self.geometry("1200x720")
        self.records: list[Record] = []
        self.current_index = -1
        self.session: ImportSession | None = None
        self.editing = False
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
        self.current_index = -1
        self.editing = False
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
            current = self.records[self.current_index]
            try:
                result = self.session.accept_scan(current)
            except (OSError, ValueError) as exc:
                messagebox.showerror("寫入失敗", str(exc))
                return
            self._push_status(
                f"{current.record_id}: {result.status} row={result.row_number} blockers={result.blockers}"
            )
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
        record = self.records[self.current_index]
        self._apply_form_to_record(record)
        try:
            result = self.session.accept_scan(record, force=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("寫入失敗", str(exc))
            return
        self._push_status(f"{result.record_id}: {result.status} row={result.row_number} blockers={result.blockers}")
        self.editing = False
        self.current_index += 1
        if self.current_index >= len(self.records):
            messagebox.showinfo("完成", "沒有更多資料。")
            return
        self._show_record(self.records[self.current_index])

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
