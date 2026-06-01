# 手寫訓練資料產生器設計（子專案 B）

**Date:** 2026-05-31
**Status:** Draft (brainstorming approved; pending spec review)

---

## 背景

要量測與提升 OCR（尤其打勾辨識）需要一批**帶標準答案**的表單影像。手上只有 1 張真實樣張，無法統計
正確率，也不足以訓練。本子專案以共用的 `form_layout` 模型為基礎，**自動合成**不同筆跡的服務記錄表
影像，並產出與 workflow 同格式的「答案卷」，供 OCR 辨識訓練與評測對齊。

現實限制：系統字型只有印刷體中文，無連筆手寫字型；改以 **setup 腳本下載開源（OFL）手寫中文字型**
（涵蓋繁體）到本機供合成，產圖過程離線。打勾記號（✓/劃-/局部塗黑）以程式化方式合成、可達高擬真。

## 目標

- 以空白服務記錄表為底，合成**不同筆跡**的手寫表單影像（文字欄位＋打勾記號）。
- 每張影像保留「實際填了什麼」的**答案卷**：與 workflow 同格式（`service_record.v1` `Batch`/`records[]`），
  每筆額外帶 `training: true` 與 `source_image`（對應產出圖檔），可與 OCR 輸出**逐欄對齊**。
- 打勾記號涵蓋 ✓、劃-、局部塗黑等多種樣式/筆跡。
- 涵蓋率：**每個選項在整批中被勾 ≥5 次**；每張隨機勾選比例 **10%–50%**、至少 1 項；單選欄至多 1、
  多選欄取隨機子集。

## 非目標（YAGNI）

- 不訓練/微調模型本身（只產資料集與答案卷）。
- 不追求對真實掃描的完美擬真（提供基本 augmentation 選項即可）。
- 字型僅用 OFL/開源授權；無手寫字型時退回系統印刷字型。
- 不修改 `form_layout` / `Record` / workflow / shipped package。

## 位置與環境

獨立工具，置於 `training/`，**不屬於 shipped 套件**；以 `.venv-paddle`（已有 PIL+numpy）執行，不新增主
套件依賴。

```
training/
  fetch_fonts.py        下載 curated、涵蓋繁體的 OFL 手寫中文字型到 fonts/，記錄來源+授權
  fonts/                (gitignored) 下載的字型；無字型時產生器退回系統印刷字型
  layout_render.py      由 form_layout + xlsx 幾何重建底圖與每格像素框（純幾何可測）
  handwriting.py        文字/記號合成（OFL 字型＋抖動；✓/劃-/塗黑程序化）
  sampler.py            取樣器（涵蓋率/比例/單多選約束，純可測）
  answer_key.py         由選中代碼組答案卷（重用 confirm_form/record_access，純可測）
  generate.py           編排：取樣→畫圖→存 PNG→累積答案卷
  out/images/*.png      合成影像
  out/answers.json      答案卷 Batch（每筆 + training + source_image）
```

## 重用既有

- `form_layout.service_record_layout()`：欄位/選項/代碼/儲存格/`record_path`。
- `confirm_form.apply_form_state` + `record_access`（子專案 A）：把「選中代碼」組進合法 `Record`，
  確保答案卷與 workflow JSON 同結構、可逐欄對齊。

## 元件（盡量純、可測）

| 元件 | 純度 | 職責 |
| --- | --- | --- |
| `layout_render`（幾何部分） | 純 | 由 `form_layout` cell + xlsx 欄寬/列高（補預設值）算出每格像素框；回傳「選項代碼→勾選框框」「文字欄位→可寫區框」。座標由建構得知（精確 ground truth）。 |
| `layout_render`（畫底圖） | PIL | 依像素框畫表單格線＋印刷標籤，得到空白底圖。 |
| `handwriting` | PIL | 文字欄位以 OFL 手寫字型（多套輪替）＋隨機旋轉/偏移/大小/筆畫渲染；勾選記號程序化合成（✓、劃-、局部塗黑），多樣式/粗細/位置抖動。 |
| `sampler` | 純 | 每張決定填哪些欄位/選項：單選≤1、多選隨機子集；整張比例 10–50%、≥1；跨整批每個選項 ≥5 次（涵蓋率驅動張數）。輸出每張的「選中代碼集合 + 文字欄位值」。 |
| `answer_key` | 純 | 選中代碼 → form-state → `apply_form_state` → `Record` → `Batch`（+`training`+`source_image`）。 |
| `generate` | 編排 | 串接以上；可選輕度 augmentation（雜訊/旋轉/模糊）。 |

文字欄位（姓名/病歷號/日期）的值來自小型內建樣本池（姓名取常見繁體姓名、病歷號隨機數字串、日期隨機
民國年），記入答案卷對應 record_path（診斷日 `record_path=None` 不寫回 Record，但仍可畫於圖上）。

## 取樣與涵蓋率（核心規則）

1. 對每張影像：以目標比例 r ∈ [10%, 50%]（隨機）選取全表單選項的子集要「勾」；
   - 單選欄位被選到時只取其中 1 個選項；多選欄位取隨機非空子集；
   - 保證整張至少 1 個選項被勾。
2. 跨整批：持續產生直到**每個選項累計被勾 ≥5 次**（涵蓋率驅動總張數；對長期未達標的選項提高其被選機率）。
3. 文字欄位（姓名/病歷號/日期）每張隨機填入（亦計入答案卷）。

## 答案卷格式

`out/answers.json` 為 `service_record.v1` `Batch`：`records[]` 每筆由該張影像實際勾選/填寫組出，
額外欄位 `training: true` 與 `source_image: "images/<檔名>.png"`。答案卷**忠實記錄該圖實際內容**
（供 OCR 逐欄對齊），不強制為臨床上合理的 record。

## 測試策略

- **`sampler`**：純單元測試 —— 比例落在 10–50%、≥1、單選≤1、多選子集合法；模擬整批達成每選項 ≥5 次。
- **`answer_key`**：純測試 —— 選中代碼 → Record → Batch；含 `training`/`source_image`；與 `service_record.v1`
  結構一致（可被 `load_batch` 接受，忽略額外欄位）。
- **`layout_render` 幾何**：純測試 —— 每個選項/欄位框落在合理頁面範圍、不重疊錯置、對得上 cell。
- **影像產生 smoke test**：產 1–2 張，驗 PNG 存在、答案卷項目數對、勾選記號像素落在對應框內。
- 跑 `.venv-paddle`；不污染主套件、不加主依賴。

## 成功準則

- [ ] `fetch_fonts.py` 能把 curated OFL 手寫字型抓到本機並記錄來源/授權；無字型時產生器退回系統字型。
- [ ] 產生器能輸出合成表單 PNG 與 `service_record.v1` 答案卷（含 `training`/`source_image`）。
- [ ] 打勾記號涵蓋 ✓/劃-/塗黑多樣式；每選項整批 ≥5 次、每張 10–50%、≥1、單多選約束正確。
- [ ] 答案卷由 `confirm_form` 組出、與 workflow 同格式、可逐欄對齊 OCR 輸出。
- [ ] 取樣器/答案卷/幾何皆有純單元測試；影像產生有 smoke test；既有測試與 policy 全綠。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 下載字型對繁體覆蓋不足 → 缺字 | 中 | 中 | 挑選已知涵蓋繁體的 OFL 字型；產圖時檢查字符可繪，缺字改用系統字型備援 |
| 重建底圖與真實掃描差距大 → OCR 轉移有限 | 中 | 中 | 主力價值在打勾記號（可擬真）；提供 augmentation；名字辨識仍以人工確認為底線 |
| 字型授權問題 | 低 | 高 | 僅用 OFL/開源並在 `fonts/` 記錄來源與授權 |
| 大字型檔灌進 repo | 低 | 中 | `fonts/` gitignored；以 setup 腳本取得，不入庫 |
| 取樣達不到每選項 ≥5（單選稀有選項） | 中 | 中 | 涵蓋率驅動：對未達標選項提高被選機率，直到全部達標 |
