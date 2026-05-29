# PaddleOCR 可攜外掛 + 打勾辨識設計

## 背景

`feature/bootstrap-ocr-design` 已完成 OCR → JSON → XLSX 的完整管線，並以真實月報表
`115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx` 驗證跑通（17 sheet 保留、公式/樣式不動、
資料寫入「個案總表」）。但 `prepare-records` 的 OCR 仍是 `FixtureOcrBackend`（查表假資料），
沒有真正辨識。

本設計補上唯一缺口：**真正的本機離線 OCR**，並依使用者需求：
1. 引擎用 **PaddleOCR**。
2. 以**可攜外掛**形式交付，主程式 exe 保持輕量、呼叫外掛。
3. **文字欄位與打勾選項都要自動辨識。**

被辨識的表單是標準「癌症資源中心服務紀錄表」（A/B/C 三大區、大量 □ 勾選格、日期為民國年），
這是穩定的固定版面，適合一次校正後重複使用。

**校正來源（已確認）**：目標月報表
`115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx` 內的 **「服務紀錄表」分頁**
就是這份表單的最原始版面。該分頁中**每個選項都是一個有座標、有文字的儲存格**
（例如 `C4 = □1.癌症篩檢與預防`、`B23 = □病人`、`A43~F47 = 25 種癌別`），選項清單、
分類結構與代碼可直接由此匯出，並與 `constants.py` 既有列舉對照。因此座標校正改為
「由 xlsx 結構化匯出」而非人工像素量測。

## 輸入來源與容差要求（重要）

第一版以 PDF 渲染頁測試，但**正式使用是 webcam 逐張掃描**（UVC，呼應原設計 capture controller）。
因此輸入會有透視變形、歪斜、縮放、光線不均，**不可依賴固定像素座標**。設計必須：

- 座標一律以**正規化/相對座標 + 誤差餘裕**表示，而非絕對像素。
- 外掛先做**影像正規化（registration）**：偵測表單外框並做去歪斜 / 透視校正，把擷取影像對齊到
  canonical 版面，再做欄位擷取。
- 打勾與文字偵測採**文字錨點自動對齊**（用 PaddleOCR 辨識到的選項標籤位置就地定位 □ 區域），
  容忍掃描變異，進一步降低對固定座標的依賴。
- 每個 □ 判定區域加 padding 餘裕；低對比/對齊不確定者標 warning 交審核 UI。

## 目標

- 在不更動既有 `OcrBackend` Protocol、`prepare_records`、`preprocess`、`session`、`workbook`
  的前提下，新增能對真實表單做文字 + 打勾辨識的 OCR 來源。
- OCR 引擎以獨立可攜元件交付，主程式有無外掛皆可運作（無外掛時退回 fixture/人工）。
- 全程離線：不開 port、不在執行期下載模型。

## 非目標

- 不重寫既有管線；只新增 backend 與外掛。
- 不處理多種表單版面；v1 只支援 `service_record.v1` 這一種固定版面。
- 不追求 100% 手寫辨識率；辨識不確定的欄位走既有「停在可修正狀態 + 桌面審核 UI」流程。

## 整體架構

```
主程式 exe (輕量)
  └─ PluginOcrBackend  ── 實作既有 OcrBackend Protocol
        │  subprocess + JSON 契約 (傳入 PNG + template_id，回傳 raw record JSON)
        ▼
  plugins/paddleocr/  (獨立可攜資料夾，與主程式分離)
        ├─ 內嵌 Python + PaddleOCR + OpenCV + 離線模型
        ├─ 文字 zone OCR
        └─ 打勾框 mark detection
```

外掛回傳的 raw record JSON 形狀與現行 `FixtureOcrBackend.extract()` 完全一致，
因此下游 `normalizer` → `validation` → `session` → `workbook` 不需任何改動。

## 子專案拆解（各自 spec → plan → 實作）

| 順序 | 子專案 | 內容 | 阻擋前提 |
| --- | --- | --- | --- |
| 1 | OCR 外掛架構 | 定義插件 JSON 契約；新增 `PluginOcrBackend`；外掛不存在時 fallback；`prepare-records` 加 `--ocr-backend`。 | 無，可立即開始 |
| 2 | PaddleOCR 可攜外掛 | 把 paddle + 模型 + opencv 打成獨立可攜資料夾；文字欄位 OCR；可行性 spike + 打包腳本。 | 子專案 1 的契約 |
| 3 | 表單版面定義 | 由「服務紀錄表」分頁結構化匯出**所有**文字欄位 + 選項清單，擴充 `form_template`。 | 已有來源（xlsx 分頁） |
| 4 | 打勾偵測 | 用 PaddleOCR 文字定位對齊掃描頁，判定每個 □ 選項 marked/unmarked，映射到既有 JSON 代碼。 | 子專案 2、3 |

子專案 1 先做（自成一體、解耦合、不需表單）。3 的版面來源已確認（xlsx「服務紀錄表」分頁）。

## 子專案 1：OCR 外掛架構（先實作）

### 插件 JSON 契約 v1

主程式呼叫外掛（subprocess），以檔案/標準輸入輸出傳遞 JSON：

請求（主程式 → 外掛）：
```json
{
  "contract_version": "ocr_plugin.v1",
  "template_id": "service_record.v1",
  "pages": [
    { "image_path": "<absolute png path>", "document_name": "for testing only.pdf", "page_number": 1 }
  ]
}
```

回應（外掛 → 主程式）：
```json
{
  "contract_version": "ocr_plugin.v1",
  "pages": [
    { "document_name": "for testing only.pdf", "page_number": 1, "record": { ... raw record ... } }
  ]
}
```

`record` 的形狀與現行 OCR fixture 的 `record` 一致（`service_date`、`name`、
`medical_record_no`、`identity`、`gender`、`patient_fields`、`services`、`ocr` …），
讓 fixture 與外掛可互換。

### `PluginOcrBackend`

- 實作 `OcrBackend` Protocol：`extract(page: PreparedPage) -> dict`。
- 外掛位置解析順序：`OCR_PLUGIN_DIR` 環境變數 → 主程式旁 `plugins/paddleocr/` → 找不到視為 unavailable。
- 以 subprocess 呼叫外掛入口，逐頁（或整批）取得 record；補上 `source` 後交給 `normalize_raw_record`。
- 外掛 unavailable 時拋出明確錯誤（或回報），讓 CLI 提示改用 `--ocr-backend fixture` 或人工流程。

### CLI 串接

- `prepare-records` 新增 `--ocr-backend {fixture,plugin}`，預設 `fixture`（維持測試確定性）。
- 選 `plugin` 時 `--ocr-fixture` 改為非必填；可加 `--ocr-plugin-dir` 覆寫外掛位置。
- `validate-json`、`import-json` 不變。

### 測試

- `PluginOcrBackend` 用一個**假外掛腳本**（回傳固定 JSON）驗證 subprocess 契約與映射，不依賴 paddle。
- 外掛不存在時的 fallback / 錯誤訊息測試。
- 既有 `FixtureOcrBackend` 與全部既有測試保持綠燈。

## 子專案 2：PaddleOCR 可攜外掛（概要）

- 可行性 spike：在開發 venv 裝 `paddleocr` + `paddlepaddle` + `opencv-python`，跑通單頁文字辨識，確認離線模型檔位置與大小。
- 打包：以 PyInstaller（或內嵌 Python + 預裝 venv 資料夾）把外掛做成獨立可攜資料夾；隨附 detection/recognition/angle 模型；設 `PADDLEOCR_HOME` 指向 bundle，確保離線、不下載。
- 文字 zone：依 `form_template` 座標（PDF point × 200/72 → 像素）裁切後辨識；`service_date` 容錯民國年/分隔符 → ISO；低信心寫入 `ocr.field_confidences` 與 warnings。
- 產出可行/折衷結論，寫入 spec 與 README。

## 子專案 3：表單版面定義（概要）

- 來源已確認：xlsx「服務紀錄表」分頁（A1:F52），每個選項皆為含 `□` 與文字的儲存格。
- 由該分頁匯出標準版面：欄位分區（A 服務評估、B 綜合身份、C 病人基本資料）、每個選項的
  分類 + 序號 + 標籤文字 + 儲存格座標。
- 擴充 `form_template.service_record_template()`：以選項標籤（canonical text）為主鍵，
  對照 `constants.py` 既有代碼（如 `□1.癌症篩檢與預防` → `screening_prevention`）。
- 比對發現的差異（如表單有「診斷日」「性別數量」「轉院、掛診」等）逐一在 spec 標註對應或忽略。

## 子專案 4：打勾偵測（概要）

- 偵測採**文字定位對齊**：PaddleOCR 在掃描頁辨識出各選項標籤文字與其 bounding box，
  以子專案 3 的 canonical 標籤比對定位，再檢查標籤左側 `□` 區域的填塗/打叉密度判定 marked。
  此法自動對齊實際掃描（容忍縮放/輕微歪斜），降低對固定像素座標的依賴。
- 多選欄位（癌別、A 區服務）收集所有 marked 代碼；單選欄位取最高分。
- 邊界情況（多選衝突、全空、低對比、標籤辨識失敗）標 warning，交審核 UI。

## 整體驗證策略

- 既有測試與 `FixtureOcrBackend` 全保留（CI 確定性）。
- 新增契約測試用假外掛，不在 CI 跑真 paddle。
- PaddleOCR 真實推論與打勾偵測的 smoke test 放 optional marker（CI 預設略過）。
- 端到端：用真實表單跑 `prepare-records --ocr-backend plugin` → `validate-json` → `import-json`，
  人工核對寫入「個案總表」的結果。

## repo policy 遵循

- 在 `feature/paddleocr-plugin-ocr` 上工作，不碰 `main`。
- 每個 PR 同步更新 `CHANGELOG.md [Unreleased]`；CLI help 變動同步 README marker。
- 完成前 `python -m policy_check --repo .` 需通過。
