# OCR-to-XLSX 服務紀錄匯入工具設計

## 目標

建立一個 Windows 可攜式工具，協助把「服務紀錄表」手寫問卷的辨識結果轉成結構化資料，經使用者確認後寫入既有月報活頁簿的「個案總表」sheet。工具必須保護原始 Excel 格式、版面、配色與公式，只填入資料，不覆寫原始模板。

第一版以 Python 快速實作與驗證流程，但架構要保留未來改寫成 Rust 的可行性。模組邊界以 JSON、檔案路徑與明確資料結構溝通，避免把核心流程綁死在 Python UI 或特定函式庫。

## 非目標

- 第一版不需要真正完成手寫 OCR 引擎。
- 第一版不修改「服務紀錄表」或原始 Excel 模板格式。
- 第一版不自行重算所有月報/年總表統計，只寫入「個案總表」，保留原公式並讓 Excel 開啟時自動重算。
- 第一版不處理「是否曾經今年服務過」欄位，先留白。

## 平台與封裝

- 目標平台是 Windows 工作環境電腦。
- 工具應以可攜式方式交付，優先朝單一執行檔或單一資料夾執行設計。
- UI 不使用 localhost web server，不開本機 port，避免觸發嚴格資安防護。
- 第一版使用 Python native desktop UI；未來若流程確認後，可依相同資料邊界改寫成 Rust native desktop app。
- 攝影機輸入以一般 Windows UVC webcam 介面為目標，IPEVO DO-CAM 視為普通相機來源。

## 使用者流程

1. 使用者啟動工具，選擇原始 xlsx 模板與輸出資料夾。
2. 工具建立工作階段暫存 xlsx，例如 `output\115年..._匯入中_YYYYMMDD-HHMMSS.xlsx`。
3. 主畫面進入連續掃描工作台：
   - 左側顯示攝影機 live preview，第一版也可用圖片或既有 JSON 模擬。
   - 支援自動偵測換張與手動擷取兩種模式，預設兩者都可用。
   - 程式偵測新單後進行 OCR adapter、分析、轉成標準 JSON。
4. 中間顯示辨識後的可編輯表單。
5. 若該筆沒有阻擋性錯誤，使用者抽換下一張時視為同意上一筆正確，工具立即寫入暫存 xlsx 並保存。
6. 若有缺欄、重複、低信心或使用者手動暫停，畫面停在該筆，讓使用者修改、重拍、略過或強制寫入。
7. 每次確認一筆都必須立即保存暫存 xlsx，避免程式或 Excel 閃退造成資料遺失。
8. 掃描完成後，使用者按「完成並另存正式檔」，工具輸出正式 xlsx 與匯入報告。

## 架構

系統拆成下列模組：

| 模組 | 職責 |
| --- | --- |
| Native desktop UI | 選檔、顯示攝影機/圖片預覽、顯示可編輯辨識結果、控制掃描流程與狀態。 |
| Capture controller | 管理 UVC camera、圖片匯入、JSON 匯入、自動換張偵測與手動擷取。 |
| OCR adapter | 把影像轉成原始辨識結果。第一版可用假 OCR、手動貼入、圖片對應 JSON 或既有 JSON。 |
| Normalizer | 將 OCR 結果轉成穩定的 normalized JSON schema。 |
| Validator | 檢查必填欄位、代碼合法性、病人限定欄位、重複資料與模板相容性。 |
| Review state | 管理待確認、已寫入、略過、錯誤、強制寫入等狀態。 |
| Workbook writer | 複製模板、找到下一個可用資料列、只寫入「個案總表」資料格、立即保存暫存 xlsx。 |
| Import report | 記錄每筆來源、辨識狀態、使用者修改、重複判斷、寫入列號與錯誤。 |

## JSON 資料格式

使用批次 JSON。一個檔案包含 schema version、批次來源資訊與 `records` 陣列；每張服務紀錄表是一個 record。

建議結構：

```json
{
  "schema_version": "service_record.v1",
  "source_batch": {
    "created_at": "2026-05-24T15:30:00+08:00",
    "source_type": "camera|image_folder|json_import|manual",
    "template_name": "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"
  },
  "records": [
    {
      "record_id": "scan-0001",
      "source": {
        "image_path": null,
        "capture_time": null
      },
      "service_date": "2026-03-15",
      "identity": "patient|family_caregiver|public_other",
      "name": "王小明",
      "medical_record_no": "A123456",
      "birthdate": null,
      "gender": "female|male|other",
      "patient_fields": {
        "nationality": "local|foreign|null",
        "age_group": "20_under|21_30|31_40|41_50|51_60|61_70|71_over|null",
        "channel": "self_known|introduced|active_followup|internal_referral|external_referral|activity|other|null",
        "disease_status": "undiagnosed|diagnosed_not_treated|diagnosed_refused|treating|recurrence_treating|followup|palliative|null",
        "source": "outpatient|inpatient|emergency|null",
        "cancers": ["breast_cancer"],
        "newly_diagnosed_within_year": false
      },
      "services": {
        "consultation": {
          "health_medical": ["screening_prevention"],
          "symptom_side_effect": [],
          "nutrition_diet": [],
          "psychosocial_emotion": [],
          "financial_social": [],
          "care_support": []
        },
        "supplies": [],
        "internal_referrals": [],
        "external_referrals": [],
        "referral_outcomes": []
      },
      "discharge_followup": null,
      "notes": "",
      "ocr": {
        "confidence": 0.95,
        "raw_text": "",
        "warnings": []
      },
      "review": {
        "status": "pending|confirmed|skipped|forced",
        "edited_by_user": false
      }
    }
  ]
}
```

## 測試 JSON

第一版實作前必須先產生約 100 筆測試 JSON records，作為 UI、驗證與寫入流程的驗證資料。

測試資料需涵蓋：

- 12 個月份的服務日期。
- 病人、親友及照顧者、一般民眾及其他。
- 女性、男性、其他性別。
- 病人限定欄位的不同組合：國籍、年齡、管道、疾病狀態、來源、癌別、一年內新診斷。
- A 區各類勾選：諮詢、用品設備、院內轉介、院外轉介、資源成果。
- 少量重複資料，用於測試本批掃描與既有 xlsx 的重複判斷。
- 少量缺欄、低信心或非法代碼資料，用於測試阻擋與修正流程。

## Excel 寫入規則

- 原始模板永遠只讀，不覆寫。
- 工具啟動時複製模板建立工作階段暫存 xlsx。
- 每次確認一筆就寫入暫存 xlsx 並立即保存。
- 寫入範圍限定「個案總表」資料列。
- 透過表頭建立欄名對應，不依賴硬編碼欄位字母。
- 只修改目標資料格的值，不修改欄寬、列高、合併儲存格、樣式、配色、公式與其他 sheet。
- 基本欄位：
  - 服務月份由 `service_date` 自動推算。
  - 服務日期填 ISO 日期對應值。
  - 身分、姓名、ID、性別依 JSON 填入。
  - ID 欄填服務紀錄表上的病歷號。
  - 生日第一版留白。
  - 是否曾經今年服務過第一版留白。
- 病人限定欄位只在 `identity = patient` 時驗證與填入。
- 親友及照顧者、一般民眾及其他不驗證也不填國籍、年齡、管道、疾病狀態、來源、癌別、一年內新診斷。
- A 區勾選項目依 JSON 代碼映射到個案總表同名分類欄位。

## 重複判斷

工具需同時檢查：

1. 本批掃描中是否已出現相同單子。
2. 目標 xlsx 既有「個案總表」是否已有相同資料。

第一版重複判斷鍵：

- 服務日期
- 姓名
- 病歷號
- 勾選內容摘要

若符合重複條件，該筆視為阻擋性錯誤，不自動寫入；使用者可選擇略過或強制寫入，匯入報告需記錄。

## 錯誤處理

阻擋性錯誤：

- 服務日期缺失或格式不合法。
- 身分無法判斷。
- 性別無法判斷。
- 病人身分缺少病人限定必填分類。
- 重複單。
- 目標模板缺少必要表頭或 sheet。
- 暫存 xlsx 無法保存。

警告：

- OCR 低信心但欄位仍可解析。
- 備註辨識不完整。
- 非病人身分出現病人限定欄位。
- OCR 原文與標準化結果存在可疑差異。

阻擋時不得自動寫入。警告可允許使用者抽換下一張時自動確認，但 UI 必須清楚標示。

## UI 設計

主畫面是一個連續掃描工作台：

- 上方：目前模板、暫存輸出檔、正式輸出資料夾、批次狀態。
- 左側：攝影機 live preview 或圖片模擬預覽。
- 左側控制：自動偵測、手動擷取、重拍、略過、暫停。
- 中間：辨識結果表單，可直接編輯日期、身分、姓名、病歷號、性別、病人欄位與勾選項目。
- 右側：本批掃描清單，顯示待確認、已寫入、略過、重複、錯誤。
- 底部：上一筆寫入狀態、暫存檔保存狀態、完成並另存正式檔。

確認行為：

- 沒有阻擋性錯誤時，使用者抽換下一張等同確認上一筆。
- 若使用者正在編輯，系統暫停自動確認，直到儲存/取消編輯。
- 寫入成功後才把狀態改為已寫入。

## 驗證策略

實作時需驗證：

- 約 100 筆測試 JSON 可完整跑過 UI、驗證、確認與寫入流程。
- 重複資料會被攔截，不會自動寫入。
- 缺欄資料會停在可修正狀態。
- 每確認一筆都會保存暫存 xlsx。
- 輸出 xlsx 只新增/修改「個案總表」資料列。
- 非目標 sheet、公式、欄寬、合併儲存格與樣式保持不變。
- 原始模板不被修改。

## 後續 Rust 改寫考量

為了降低未來改寫成本：

- JSON schema 必須穩定並版本化。
- OCR adapter、validator、workbook writer 與 UI 狀態分離。
- 核心流程避免依賴 Python UI 物件。
- 匯入報告格式用 JSON 或 CSV，便於跨語言產生。
- 第一版應保留一組 CLI 或模組入口，可用同一批 JSON 直接跑驗證與寫入，方便未來 Rust 版本做相容性測試。
