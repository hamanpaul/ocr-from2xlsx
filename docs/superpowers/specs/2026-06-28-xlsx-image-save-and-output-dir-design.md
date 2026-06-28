# XLSX 寫入崩潰（內嵌圖片）＋輸出位置 — 設計

日期：2026-06-28
狀態：approved（brainstorm 對齊後）

## 問題

使用者回報「服務項目 `fatigue_strength` 仍出現在 xlsx，而且更糟」。逐步蒐證後發現是**三件事疊在一起**：

1. **`fatigue_strength` 對應其實已修好**（PR #71，`_write_services` 改由 `form_layout` 推導完整 code→(編號,標籤)）。端到端驗證：勾選 4.疲憊與體力 → 寫入「諮詢-症狀與副作用照護4」(AE)＝「4.疲憊與體力」，無英文 code 外洩。
2. **真正的寫入失敗來自內嵌圖片**：官方模板 `115…xlsx` 有 **14 張內嵌圖片**（服務紀錄表 logo＋各月分頁）。openpyxl 載入（非 read-only）後，圖片資料是**延遲**從來源 zip 讀取的；該 zip 會在 `load_workbook` 後被關閉/GC，於是 `workbook.save()` 在 `_write_images()` 階段呼叫 `img._data()` → `PIL.Image.open(ref)` → `seek(0)` 時拋 **`ValueError: I/O operation on closed file`**。此為**非確定性**（取決於 GC 時機）：多次測試多半成功、偶發失敗；失敗時 `save` 寫到一半 → **產出損毀的 xlsx**（連 `[Content_Types].xml` 都缺）。
3. **輸出位置跑錯**：`_choose_template` / `_import_folder_batch` 用相對路徑 `Path("output")`，而 packaged exe 的 cwd＝`dist\`，所以檔案落在 `dist\output\`，不在使用者查看的 repo `output\` → 「output 下也沒有」。

使用者因此（a）拿到損毀/找不到的新檔，（b）回頭看昨天舊 exe 產生的 `2222\匯入中.xlsx` → 看到舊的 `fatigue_strength`。感受「沒修＋更糟」合理。

## 修法（已驗證）

### 1. 載入時即時把內嵌圖片讀進記憶體（Option A）
`WorkbookWriter.__init__` 在 `load_workbook` 之後、archive 仍可讀時，把每張圖 `img._data()` 讀出、改成 `img.ref = BytesIO(data)`，使 `save()` 不再依賴已關閉的 zip。實測：強制 `gc.collect()` 下 **8/8 存檔成功，14 張圖片完整保留**。以 try/except 包覆，openpyxl 版本差異或無圖時不影響載入。保留 logo、存檔穩定。

### 2. 輸出固定在 exe 所在資料夾的 `output\`
`_resolve_output_dir()`：有 `output_root`（測試覆寫）優先；否則 frozen（packaged exe）取 `Path(sys.executable).parent`，dev 取 `Path.cwd()`，再接 `output`。免選、可預測。寫入/開新報表後在狀態列顯示**完整絕對路徑**，並在「檔案」選單加「開啟輸出資料夾」。

## 不做（YAGNI）
- 原子寫入（temp→rename）：Option A 後 save 不再因圖片失敗，暫不需要；未來若要對任意錯誤防損毀再加。
- 移除圖片：會丟失 logo，捨棄。

## 測試
- 建含內嵌圖片的 fixture 模板 → `WorkbookWriter` 載入後圖片 `ref` 應為 `BytesIO`（已 materialize）、且 write+save 成功、重開圖片仍在。
- `_resolve_output_dir`：frozen / 非 frozen / `output_root` 覆寫三情境。
