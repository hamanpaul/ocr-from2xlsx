# 離線 VLM 輔助辨識設計（取代整套 OCR 辨識層）

**Date:** 2026-06-14
**Status:** Draft (brainstormed; pending spec review)
**Supersedes:**
- openspec change `fix-core-field-recognition`（text-anchor + ink-probe hybrid）— 整套辨識策略改弦。
- `docs/superpowers/specs/2026-06-14-form-registration-checkbox-design.md`（PARKED 的幾何對位路線）— 確認放棄幾何。

---

## 背景與架構 Review

PR #21（webcam 擷取品質）落地後，對真實文件攝影機（IPEVO DO-CAM，固定位、8MP、打光）實測：**擷取品質不是瓶頸，辨識本身錯得離譜**。逐一診斷後，三條既有辨識路全部失敗或不可行：

| 路線 | 狀態 | 根因 |
| --- | --- | --- |
| PaddleOCR 文字層 + `field_extract` | 只填 `service_date`，其餘空/錯 | 從沒做服務評估 A/B/C 區勾選；identity/gender 走 OCR 文字異常啟發式，兩次擷取就不同 |
| 幾何對位（registration）+ `template_boxes` ink-probe | 放棄 | 6px 小框要求 warp 誤差 <1%；鏡頭畸變＋紙張微翹＋角點誤差在 3264px 尺度下超標，4 種對位法全失敗 |
| OCR 文字洩漏 heuristic（`classify_marks.py`） | 太雜 | 勾選只「部分洩漏」進文字；列標題被誤判成選項，滿江紅 `[?]` |

**Review 的關鍵發現**：`domain.py` 已完整建模 `service_record.v1`（含 `patient_fields`：國籍/年齡組/管道/疾病狀態/來源/癌別，與 `services`：諮詢/院內外轉介/成果/用品），`workbook.py` 的 `write_record` **已會把這整包寫進 Excel**。也就是說 **schema 與 Excel 寫入端早已完工，整個專案唯一缺的是「真的能填滿這些欄的辨識」**。

**結論**：本案是**純辨識層替換**——把舊 OCR/幾何/heuristic 整套換成本機 Vision-LLM 預填，下游（schema、validation、workbook、審核 UI）幾乎不動。

## 決策前提（已與使用者確認）

| 議題 | 決定 | 理由 |
| --- | --- | --- |
| 硬指標 | 打勾／各種日期／數字辨識，**最終 Excel ≥95%** | 使用者明定 |
| 現有 OCR | **完全棄用** | 實測完全不準 |
| 雲端 vs 本機 | **完全本機/離線** | 個人使用、不願付 API 費；醫療個資不出本機 |
| 引擎 | **本機開源 Vision-LLM（VLM）** | 唯一被證明能「看圖理解」勾選的路；非舊離線那套 |
| 目標形態 | **輔助式：機器預填 + 人快速核對** | 低階硬體上純機器無法保證 95%；人核才是 ≥95% 的保證關卡。個人/季節性使用本就人在迴圈 |
| 硬體 | 內顯/低階卡（CPU-bound、季節性批次可接受慢） | 使用者實況 |
| 預設模型 | **Qwen 3.5 VL 2B**（小、可攜、中文強）；4B/7B 為 config 升級 | 中文是決勝軸；CheckboxQA 顯示準確率對尺寸敏感，故保留升級孔 |
| Runtime（出貨） | **llama.cpp `llama-server`**（單一可攜 exe + GGUF、Vulkan 吃內顯、零安裝）；dev 期可用 Ollama | 可攜性最佳；模型權重不進 git，build 時抓進 `dist/` |
| 隱私邊界 | **無**（全本機 → 不需遮罩、不需雲/本機分流） | 因引擎全本機而自然消失 |

## 目標

把擷取到的表單影像（webcam still 或圖檔）→ 本機 VLM **預填**完整 `service_record.v1`（勾選／日期／數字／姓名／病歷號全本機）→ 在既有 `confirm_form` 審核 UI 並排顯示、**標出低信心欄位**供人快速核對改錯 → 既有 `workbook.py` 寫進 Excel。最終正確率由人核保證。

## 非目標（YAGNI / 延後）

- 不做雲端 backend（只在介面層留「孔」，日後可換）。
- 不重訓任何模型；不微調 VLM（v1 用 prompt + 已知選項清單）。
- 不改 `workbook.py` 寫入邏輯與 `service_record.v1` 既有欄位語意（已支援整張）。
- 不做精準幾何對位（6px 框）；切片只用寬鬆比例分區帶。
- 不做自動快門/即時引導/多頁拼接/超解析度。

## 架構：留 / 退 / 新

| | 元件 | 處置 |
| --- | --- | --- |
| **留** | `capture`（webcam still + 圖檔）、`document_condition`（轉正/增強）、`domain`(schema)、`validation`、`workbook.py`、`confirm_form` 審核 UI、`name_roster`/`name_suggestion`、`correction_store`、`ocr_plugin.v1` backend 接縫 | 沿用 |
| **退** | PaddleOCR `field_extract`/`mark_detect`/`mark_model`、幾何 `crop_provider`+`template_boxes`、ink-probe、OCR 文字洩漏 heuristic | 從辨識路徑移除（程式碼可保留歸檔，但不再接線） |
| **退** | openspec `fix-core-field-recognition`、parked registration spec | 標 superseded |
| **新** | `vision_backend`（本機 VLM 預填，填完整 `service_record.v1`）、VLM client（連本機 `llama-server`）、切片/分區模組、可攜模型 build 腳本 | 新增 |

## 辨識引擎設計（本機 VLM）

### Runtime
- 出貨：bundle `llama-server`（llama.cpp）為子程序，listen 本機 port；app 以 HTTP 呼叫。Vulkan backend 可用內顯，自動降級 CPU。
- 模型：GGUF（Q4）權重，預設 **Qwen 3.5 VL 2B**；`mmproj`（視覺投影）一併 bundle。權重 **不進 git**，由 `build/` 腳本（仿 `build/build_paddle_plugin.py`）在打包時抓進 `dist/`。
- 模型名/路徑/port 皆可由 config 與環境變數覆寫（沿用 `OCR_FROM2XLSX_HOME` 慣例），讓 Phase 0 與日後升級 4B/7B 只改設定。

### 切片策略（schema-guided，非幾何精準）
1. 轉正（沿用 app「旋轉」設定 / `document_condition`）。
2. 依**寬鬆比例分區帶**切成數片：A 服務評估、B 綜合身份、C 病人基本資料、數量框、姓名-病歷號列。分區帶針對固定 IPEVO 版位調一次即可（偶爾切歪由人核兜底）；**不需 6px 精度**。
3. 每片連同「**該區已知選項清單**」送 VLM，prompt 要求回每個已知選項 `marked/unmarked`、手寫日期/數字的值，以 JSON 輸出（結構化、欄位封閉）。
4. 合併各片 → 完整 `service_record.v1`。

### 姓名 / 病歷號
- 同一本機 VLM 讀「姓名-病歷號列」片：CJK run → `name`，長數字 run → `medical_record_no`。
- `name` 結果 snap 到 `name_roster`（既有）以 `name_suggestion` 拉高準確；無把握則留空交人。

### 信心與標示
- 每欄附 VLM 信心（或由我們導出低信心旗標：留空、roster 無匹配、數字長度異常等）。
- 低信心欄位在審核 UI 標紅，導引人眼優先核對。

## 輔助審核 UX
- `confirm_form` 並排顯示**表單影像（可縮放，已有放大鈕）** ＋ 預填欄位。
- **低信心 / 未填欄位視覺標紅**。
- 人改完 → 確認 → 既有 `workbook.py` 寫 Excel。
- 修正寫入 `correction_store`，作為日後改 prompt / roster 的回饋來源。

## 整合接縫與資料流
- 新增 `vision_backend`，實作與現有 OCR backend **同一介面**，但填**完整** `service_record.v1`。
- VLM 呼叫**可注入/可假造**（沿用現有 `ocr_fn`/`mark_fn` 注入模式）：純邏輯（切片合併、schema 映射、roster snap、信心旗標）不依賴真模型即可單元測試。
- 因 `workbook.py` 已吃整張 → **寫入端零或極小改動**（已驗 identity/gender/國籍/年齡組/管道/疾病狀態/來源/癌別/services 各類；**「諮詢人次」count 欄位的 schema↔writer 映射待實作時確認**，若缺再補，屬小範圍）。
- webcam still 與圖檔輸入走**同一條**辨識路。

```
影像(webcam still / 圖檔)
  → 轉正 / 條件化
  → 分區切片 + 各區已知選項清單
  → 本機 VLM（llama-server）逐片判讀 → JSON
  → 合併 service_record.v1（含信心旗標）
  → confirm_form 並排核對（標紅低信心）
  → 人確認
  → workbook.py 寫 Excel
```

## Phase 0：先除風險（原型 + 評估）

在大規模實作前，先做一次量測：

- **模型 bake-off**：候選 **{Qwen 3.5 VL 2B（預設）、4B、Gemma 4 E2B、7B（準確率天花板）}**，在**真實樣本（`output/reg/filled_cam` 等）＋使用者機器**上量「逐區預填準確率」與「每張延遲」。
- **Runtime 視覺支援驗證**：bundle 前先確認所選模型的 **vision 路徑在可攜 llama.cpp 已支援**（Gemma 3n 曾只支援文字 → 必驗）。
- **Ground-truth 小集**：用審核 UI 標數張真實表單（`correction_store` 產 labels）作評估基準。
- **「預填夠好」定義**：相對全手動，預填能砍掉多少勾選工；最終人核 Excel ≥95%（實際接近 100%）。
- 產出決定是否沿用 2B 或升級 4B/7B、分區帶座標、prompt 模板。

## 錯誤處理 / Fallback
- `llama-server` 未就緒 / 模型缺檔 → 明確提示，**手動輸入照常可用**（預填是加分，不是前提）。
- 某片辨識失敗或 JSON 不合法 → 該區留白交人，不 crash。
- VLM 回非預期欄位/格式 → 以封閉 schema 驗證並丟棄越界值，記 warning。

## 測試策略
- 純邏輯單元測試（無模型）：切片合併、schema 映射、roster snap、信心旗標、JSON 驗證。
- 可注入 fake VLM client 驅動 `vision_backend.run()` 的端到端組裝測試。
- Optional marker 的真模型回歸測試（預設 CI skip，手動以 bundle 跑），對 ground-truth 逐欄比對。
- 既有測試與 `policy_check` 維持綠燈。

## 打包（可攜）
- `build/` 新增腳本：抓 `llama-server`（含 Vulkan）＋ GGUF＋mmproj 進 `dist/`。
- 模型/runtime **不進 git**（遠超體積門檻，仿 PaddleOCR portable plugin 與 name 模型慣例）。
- 可攜包預估體積：2B 約 2.5–3GB（+runtime）。

## 範圍
- **In**：`vision_backend` 本機 VLM 預填（填整張）、審核低信心標示、Phase 0 原型＋評估、退場舊辨識模組接線、可攜 build 腳本。
- **Out（本批不做）**：雲端 backend 實作、模型重訓/微調、workbook 改動、自動快門。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 2B 預填準確率不足（CheckboxQA：3B=43.6 vs 7B=71.9，尺寸敏感） | 中高 | 中 | 人核為 ≥95% 的真正保證；config 一行升 4B/7B；Phase 0 量「省工」門檻 |
| 所選模型 vision 路徑在 llama.cpp 未支援 | 中 | 高 | Phase 0 bundle 前必驗；備援 runtime（Ollama/其它）或換模型 |
| 固定相機版位偶有偏移 → 分區切歪 | 中 | 低 | 寬鬆比例帶＋人核兜底；非 6px 精度 |
| 低階硬體每張數分鐘 | 高 | 低 | 季節性批次可排隊/過夜；2B 已是最輕選擇 |
| 可攜包體積大（GB 級） | 中 | 低 | 一次性離線部署可接受；模型不進 git |

## 成功標準
- [ ] `vision_backend` 對真實參考表能預填完整 `service_record.v1`（勾選/日期/數字/姓名/病歷號），逐欄可對照影像。
- [ ] 純邏輯（切片合併/映射/roster/信心）有不依賴模型的單元測試且通過。
- [ ] 審核 UI 標示低信心欄位，人核流程可改錯並寫入 Excel。
- [ ] Phase 0 報告：模型選定、逐區準確率、每張延遲、「省工」結論。
- [ ] 可攜 build 產出含 runtime+模型的 `dist/`，模型不在 git。
- [ ] 既有測試與 `policy_check` 綠燈；CHANGELOG / openspec / README 同步。
