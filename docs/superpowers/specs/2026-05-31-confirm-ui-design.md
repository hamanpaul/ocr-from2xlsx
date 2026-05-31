# 單頁鏡像確認 UI 設計（子專案 A）

**Date:** 2026-05-31
**Status:** Draft (brainstorming approved; pending spec review)

---

## 背景

現有 `app.py` 審核 UI 只顯示 6 個文字 Entry（record_id / service_date / identity / name /
medical_record_no / gender），沒有身分/性別的選擇控制、沒有病人限定欄位、沒有 A 區諸勾選；人工要逐欄
看、逐欄改，效率差。共用的 `form_layout` 模型（區塊/欄位/選項/代碼/`record_path`）已落地，可資料驅動
地呈現整張表單。

## 目標

- 一頁顯示**整張服務記錄表的所有欄位**、可直接修改、**一次確認**（非逐欄確認）。
- 由 `form_layout` 資料驅動生成編輯控制；確認＝整頁 human-confirmed 寫入 xlsx。
- 版面隨輸入來源自適應：以圖檔 OCR（有來源頁圖）→ 並陳來源圖供核對；webcam 分析（無存檔頁圖）→ 只表單。
- 重用既有 `session`（含 `human_confirmed`）、`correction_store`、`form_layout`，不重寫核心。

## 非目標（YAGNI）

- 不實作即時 webcam 擷取本身（沿用既有 capture；A 只負責確認 UI）。
- 學習回路維持以姓名為主（沿用現有 correction store 行為）；不在 A 擴成全欄位學習（屬子專案 B/後續）。
- 不改 workbook 寫入器、不改 `ocr_plugin.v1` 契約、不改 `form_layout`。

## 架構與元件

| 元件 | 位置 | 職責 | 純度 / 可測 |
| --- | --- | --- | --- |
| `record_access` | `src/ocr_from2xlsx/record_access.py` | 依點分路徑讀寫 Record 巢狀結構：`get_by_path(record, path)` / `set_by_path(record, path, value)`，支援 `identity`、`patient_fields.age_group`、`services.consultation.health_medical`、`patient_fields.cancers`（list）、`patient_fields.newly_diagnosed_within_year`（bool）等 | 純函式、不依賴 Tkinter，可單元測試 |
| 表單預填/收集邏輯 | `src/ocr_from2xlsx/confirm_form.py` | 純函式：`record_to_form_state(layout, record)` → 每欄位的選取代碼集合/單選代碼/文字；`apply_form_state(layout, record, state)` 經 `record_access` 寫回 | 純、可測（不依賴 Tkinter） |
| 表單檢視 | `app.py`（或 `ui_form.py`） | 遍歷 `form_layout` 依 `kind` 生成 widget（text→Entry、single_choice→Radiobutton、multi_choice→Checkbutton），分區(A/B/C)以 LabelFrame、可捲動 | Tkinter；以 smoke test 驗證建構 |
| 來源圖面板 | `app.py` | record 的 `source.preprocessed_image_path` 存在 → 左側顯示來源頁圖核對；不存在 → 隱藏 | Tkinter |
| 編排 | `app.py` `ReviewApp` | 載入 JSON → 逐筆建表單 → 確認並寫入 → 下一筆 | Tkinter |

`form_layout` 的 `record_path` 為 `None` 的欄位（如 `diagnosis_date`）：表單可顯示/編輯，但不寫回 Record。

## 控制項對應

- `text` → `Entry`：service_date、name、medical_record_no、diagnosis_date。
- `single_choice` → 一組 `Radiobutton`（含一個「未選」狀態）：identity、gender、nationality、age、channel、
  disease_status、source、newly_diagnosed（單一勾選＝True/False）。
- `multi_choice` → 每選項一個 `Checkbutton`：cancer、consultation 六分類、supplies、internal_referrals、
  external_referrals、referral_outcomes。
- 依 record 預填：多選勾出 record 既有代碼、單選選中現值、文字帶入。

## 自適應版面

```
[走1：有來源圖]                         [走3：webcam / 無來源圖]
┌─────────────┬─────────────────┐      ┌─────────────────────────┐
│  來源表單圖   │ A 區 諮詢勾選…    │      │ A 區 諮詢勾選…            │
│ (可捲動核對)  │ B 區 身分○ 性別○ │      │ B 區 身分○ 性別○ 姓名[_] │
│             │   姓名[____]     │      │ C 區 癌別 ☑☐☐…          │
└─────────────┴─────────────────┘      └─────────────────────────┘
   [確認並寫入] [強制寫入] [上一筆/下一筆]
```

- 來源圖路徑：以載入 JSON 所在/輸出資料夾 + `record.source.preprocessed_image_path` 解出；不存在則不顯示面板。

## 確認與寫入流程（一次確認）

1. 使用者在整頁直接修改任意欄位。
2. 按「**確認並寫入**」：經 `apply_form_state` 把所有 widget 值寫回 Record、標 `review.edited_by_user=True`。
3. 呼叫 `session.accept_scan(record, human_confirmed=True)`（人工已審視整頁）→ 寫入 xlsx（剝除
   `name.unconfirmed`），姓名校正寫回 correction store；前進下一筆。
4. 若有阻擋性錯誤（如代碼非法）→ 就地顯示，不前進；保留「強制寫入」給不完整但要保存的資料
   （`force=True, human_confirmed=True`）。
5. 一筆＝一頁；提供上一筆/下一筆瀏覽。

## 測試策略

- **`record_access`**：純單元測試 —— 巢狀 `patient_fields.*`、`services.consultation.<cat>`、多選 list
  寫入/讀取、bool 欄位、`record_path=None` 不寫回；無效路徑報錯。
- **`confirm_form`**：`record_to_form_state` 與 `apply_form_state` 往返（round-trip）純測試，不依賴 Tkinter。
- **Tkinter 建構 smoke test**：沿用既有 `tests/test_app_navigation.py` 風格，驗證表單能由 `form_layout`
  建出、預填、收集；確認/強制寫入路徑與 session 整合。
- 既有測試與 policy 全綠。

## 成功準則

- [ ] 一頁顯示服務記錄表所有欄位（文字＋單選＋多選），由 `form_layout` 資料驅動、可直接編輯。
- [ ] `record_access` 能依 `record_path` 正確讀寫所有欄位（含巢狀、多選、bool、None）。
- [ ] 「確認並寫入」一次套用整頁、以 `human_confirmed=True` 寫入 xlsx 並推進；姓名校正寫回 store。
- [ ] 有來源圖時並陳核對、無來源圖時只表單（自適應）。
- [ ] 純邏輯（record_access / confirm_form）有單元測試；UI 有建構 smoke test；既有測試與 policy 全綠。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 點分路徑寫回巢狀結構錯置（尤其多選 list / bool） | 中 | 高 | `record_access` 純單元測試完整覆蓋各路徑型態 |
| 整張表單 widget 量大（~120 選項）造成 UI 雜亂/卡頓 | 中 | 中 | 分區 LabelFrame + 可捲動；資料驅動生成 |
| 來源圖路徑解析失敗 | 低 | 低 | 解不出就隱藏面板（走 3），不影響確認流程 |
| 確認全欄位後仍有非法代碼擋寫 | 低 | 中 | 就地顯示阻擋原因；保留強制寫入 |
