# 共用表單版面模型設計（form_layout）

**Date:** 2026-05-31
**Status:** Draft (brainstorming approved; pending spec review)

---

## 背景

兩個獨立子專案都需要「服務記錄表」的結構化描述：
- **A**：單頁鏡像確認 UI（一頁顯示所有欄位、可直接改、一次確認）。
- **B**：手寫訓練資料產生器（以空白表單為底合成不同筆跡手寫圖 + 答案卷）。

為避免兩邊各自硬編表單結構，先抽出一個**共用、render 無關、人工校訂**的版面模型，作為 A/B 唯一來源。
來源是 repo 內 `115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx` 的「服務紀錄表」分頁（A1:F52，
每個選項皆為含「□+標籤」的儲存格，33 個合併範圍）。

## 目標

- 提供一個結構化模型：區塊(A/B/C) → 欄位(含型別) → 選項(標籤 + 代碼 + 儲存格)。
- 模型是「表單 ↔ workflow Record schema」的**完整橋樑**：每個欄位標明它對應到 `service_record.v1`
  Record 的哪個路徑，讓 B 能由「勾了哪些選項」組出合法 Record，並讓評測能逐欄對齊。
- 代碼一律重用既有 `constants.py`，不另立一套。
- 以對照分頁的測試保證模型與真實表單一致（雙向涵蓋）。

## 非目標（YAGNI）

- **不含幾何/像素座標**：格位→像素的 render 由 B 自理；UI 版面由 A 自理。
- 不取代 `form_template.py`（負責 preprocess 的頁面尺寸檢查）或 `constants.py`（保留並被引用）。
- 不在本案實作 A 的 UI 或 B 的產生器（各自獨立 spec→plan）。
- 純 stdlib，不依賴 paddle/PIL/openpyxl（驗證測試可用 openpyxl，但模型本身不依賴）。

## 資料結構（Python dataclass，純 stdlib）

`src/ocr_from2xlsx/form_layout.py`：

```text
Option(label: str, code: str, cell: str)
    label  分頁上的選項文字（如 "1.癌症篩檢與預防"）
    code   canonical 代碼（來自 constants，如 "screening_prevention"）
    cell   儲存格參照（如 "C4"）

Field(key: str, title: str, kind: Kind, record_path: str,
      anchor_cell: str, options: list[Option])
    kind          "text" | "single_choice" | "multi_choice"
    record_path   對應 service_record.v1 Record 的路徑（見下）
    anchor_cell   text 欄位用（其值或標籤所在格）；choice 欄位為其標題格
    options       choice 欄位的選項；text 欄位為空

Section(id: str, title: str, fields: list[Field])     # A / B / C / top

FormLayout(template_id: str, sections: list[Section])
    helpers: field_by_key(key), iter_fields(), iter_options(),
             options_by_code(field_key)

service_record_layout() -> FormLayout     # 建構校訂後版面，重用 constants 代碼
```

### record_path 對應（表單 ↔ Record schema 橋樑）

| Field key | kind | record_path |
| --- | --- | --- |
| service_date | text | `service_date` |
| identity | single_choice | `identity` |
| name | text | `name` |
| medical_record_no | text | `medical_record_no` |
| diagnosis_date | text | `null`（workflow Record 無對應欄位，見備註） |
| gender | single_choice | `gender` |
| nationality | single_choice | `patient_fields.nationality` |
| age | single_choice | `patient_fields.age_group` |
| channel | single_choice | `patient_fields.channel` |
| disease_status | single_choice | `patient_fields.disease_status` |
| source | single_choice | `patient_fields.source` |
| cancer | multi_choice | `patient_fields.cancers` |
| newly_diagnosed | single_choice | `patient_fields.newly_diagnosed_within_year` |
| consultation.health_medical | multi_choice | `services.consultation.health_medical` |
| consultation.symptom_side_effect | multi_choice | `services.consultation.symptom_side_effect` |
| consultation.nutrition_diet | multi_choice | `services.consultation.nutrition_diet` |
| consultation.psychosocial_emotion | multi_choice | `services.consultation.psychosocial_emotion` |
| consultation.financial_social | multi_choice | `services.consultation.financial_social` |
| consultation.care_support | multi_choice | `services.consultation.care_support` |
| supplies | multi_choice | `services.supplies` |
| internal_referrals | multi_choice | `services.internal_referrals` |
| external_referrals | multi_choice | `services.external_referrals` |
| referral_outcomes | multi_choice | `services.referral_outcomes` |

備註：「診斷日」目前 workflow Record 無對應欄位（非目標欄位）；模型仍收錄其 anchor_cell 供 A 顯示 / B 合成，
但 record_path 標為 `null`（不寫入 Record）。`newly_diagnosed` 在表單是單一「□」勾選，對應布林值。

## 涵蓋範圍（完整表單）

- 頂部：服務日期。
- A 服務評估統計：諮詢 6 分類（健康與醫療系統 / 症狀與副作用照護 / 營養與飲食 / 社會心理情緒 /
  經濟與社會資源 / 照顧與支持）各自的選項；提供實體用品及設備；轉介院內資源；轉介院外資源；資源成果。
- B 綜合身份統計：身分、姓名/病歷號、診斷日、性別、國籍、年齡。
- C 病人基本資料統計：管道、疾病狀態、來源、癌別、一年內新診斷個案。

## 訓練答案卷格式（B 的下游需求，本模型負責對齊）

B 產出的答案卷必須與 workflow JSON **同格式**（`service_record.v1` 的 `Batch`/`records[]`），
每筆記錄只多兩個欄位：
- `training: true`（標示為訓練/答案卷用）
- `source_image: "<產圖檔名/路徑>"`（對應原始合成圖）

本模型透過 `record_path` 確保「勾選的選項代碼」能正確組進 Record 的對應位置，使答案卷與 OCR 實際輸出
可逐欄對齊比較。（答案卷的實際組裝與輸出在 B 的 spec 實作；本模型只保證對齊所需的結構與代碼。）

## 正確性保證（對照分頁驗證）

測試（`tests/test_form_layout.py`，可用 openpyxl 讀 repo 空白 xlsx）：
1. **模型→分頁**：每個 `Option.cell` 所在儲存格的文字包含該 `Option.label`。
2. **分頁→模型（雙向涵蓋）**：分頁中每個含「□」的選項儲存格，都有對應的 `Option`（無遺漏）。
3. **代碼合法**：每個 `Option.code` 是 `constants.py` 中該欄位的合法代碼；單選欄位代碼互斥、多選欄位代碼集合正確。
4. **record_path 合法**：每個非 null 的 `record_path` 對得上 `Record` schema 的實際欄位。

## 測試策略

- 存取器單元測試（`field_by_key`、`iter_options`、`options_by_code`、計數）。
- 上述對照分頁雙向涵蓋驗證測試。
- 純 stdlib；模型本身可在無 openpyxl 環境匯入（驗證測試才需要 openpyxl）。

## 成功準則

- [ ] `form_layout.py` 提供 dataclass 模型與 `service_record_layout()`，重用 constants 代碼。
- [ ] 每個欄位有 `record_path`（或 null），完整對應 `service_record.v1` Record。
- [ ] 對照分頁雙向涵蓋測試通過：模型與真實「服務紀錄表」一致、無遺漏選項。
- [ ] A、B 皆可只 import 此模型取得表單結構，不需各自硬編。
- [ ] 既有測試與 policy 全綠。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 分頁標籤與 constants 標籤文字不一致導致代碼綁錯 | 中 | 高 | 驗證測試逐格比對；代碼以人工校訂綁定並測試合法性 |
| 表單版面日後變動 | 低 | 中 | 雙向涵蓋測試會抓出 drift |
| record_path 與 Record schema 不同步 | 中 | 高 | 測試驗證每個 record_path 對得上 Record 欄位 |
| 「診斷日」等無 Record 對應欄位造成混淆 | 低 | 低 | record_path 標 null，文件明示不寫入 Record |
