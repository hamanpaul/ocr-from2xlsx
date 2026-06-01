# 合成集評測設計（雙模：打勾隱化 + 端到端）

**Date:** 2026-06-01
**Status:** Draft (brainstorming approved; pending spec review)

---

## 背景

子專案 B 的訓練資料產生器會產出合成服務記錄表影像與**與 workflow 同格式的答案卷**
（`service_record.v1` Batch，每筆 + `training` + `source_image`）。有了答案卷就能量化 OCR 的正確率，
回答先前「OCR→JSON 正確率如何」的問題。

關鍵限制：合成表單是**幾何重建**（標籤用小字型、非真實版面）。整條 plugin 管線靠 OCR 讀到的印刷
標籤當錨點，若 PaddleOCR 讀不出合成標籤，端到端數字反映的是「合成圖品質」而非「OCR 能力」。但產生器
**知道每個勾選框的精確座標**，因此可直接量「框內墨跡判定」是否正確，繞過標籤可讀性。

## 目標

- **模式 1（主、可靠）打勾偵測隱化評測**：用已知選項框座標 + `mark_detect.is_marked` 對每個選項判定，
  與答案卷比對，得打勾偵測的 precision/recall/F1（總體與各欄位）。不依賴 OCR 讀標籤。
- **模式 2（診斷）端到端管線評測**：對每張合成圖跑 `PluginOcrBackend.extract`，預測 record 與答案卷
  gold record 逐欄比對；誠實標註合成↔真實落差。
- 共用一個**純度量模組**（P/R/F1、scalar exact-match、record 逐欄比對），CI 可測。

## 非目標（YAGNI）

- 不改 OCR 管線、產生器、`form_layout`（evaluator 只讀）。
- 不做模型訓練；不追真實掃描評測（合成集評測）。
- 真實 OCR 多樣本評測（用真表單）為後續，需累積真實樣本。

## 位置與環境

沿用 `training/`（與產生器同族）；evaluator 只讀產生器輸出。

```
training/eval_metrics.py    NEW. 純度量：set→P/R/F1、scalar exact、compare_records、compare_mark_sets。
training/eval_marks.py      NEW. 打勾隱化評測（PIL，.venv-paddle）。
training/eval_pipeline.py   NEW. 端到端評測（需 dist bundle；markered/manual）。
training/out/eval/          (gitignored) report.json + report.md
```

**重用**：`form_layout`（欄位/選項/record_path/cell）、`record_access.get_by_path`、`layout_render`
（選項框幾何）、`mark_detect.is_marked`、`plugin_backend.PluginOcrBackend`、`json_io.load_batch`、答案卷。

## 共用度量（`eval_metrics`，純、可測）

- `prf(tp, fp, fn) -> (precision, recall, f1)`（分母 0 時定義為 0）。
- `compare_sets(gold: set, pred: set) -> (tp, fp, fn)`。
- `compare_mark_sets(gold_marks, pred_marks)`：以 `(field_key, code)` 為元素的集合比對 → 聚合與各欄位 P/R/F1。
- `compare_records(layout, gold_record, pred_record)`：逐欄
  - text / single_choice（scalar）：exact-match（bool，空值對空值算正確）。
  - multi_choice：集合 P/R/F1（gold/pred 各欄位代碼集合）。
  - 輸出每欄結果 + 聚合（scalar accuracy、multi 微平均 P/R/F1、整體）。
  以 `record_access.get_by_path` 依 `form_layout` `record_path` 取值；`record_path=None` 欄位略過。

## 模式 1：打勾偵測隱化評測（`eval_marks`）

對答案卷每筆 record 與其 `source_image`：
1. 載入合成圖；用 `layout_render` 幾何取每個選項的勾選框（cell→像素框）。
2. 對每個選項框 `mark_detect.is_marked` → 預測 marked set（`(field_key, code)`）。
3. gold marked set：由 record 經 `record_access` 解出各 choice 欄位已選代碼。
4. `compare_mark_sets` → 整體＋各欄位 P/R/F1，寫入報告。

不依賴 OCR；量「框內墨跡判定」對 ✓/劃-/局部塗黑 的準確度與門檻是否恰當。

## 模式 2：端到端管線評測（`eval_pipeline`，markered/manual）

對答案卷每筆 record 與其 `source_image`：
1. 以 `PreparedPage(image_path=合成圖)` 呼叫 `PluginOcrBackend(dist/plugins/paddleocr).extract` → 預測 record。
2. `compare_records(layout, gold, pred)` 逐欄比對 → 報告（含各欄位 accuracy/P/R/F1、未讀出/錯誤清單）。
3. 報告需標註：合成標籤若 OCR 讀不出，數字偏低反映合成↔真實落差，非真實能力。

需 `dist/plugins/paddleocr` bundle 與 `.venv-paddle`；以環境變數/marker 控制（預設 CI 不跑）。

## 報告格式

`training/out/eval/report.json`（機器可讀）+ `report.md`（人類可讀）：
- 模式 1：打勾 P/R/F1（總體 + 各欄位）、樣本數。
- 模式 2：各欄位 accuracy（scalar）/P/R/F1（multi）、整體、未讀出/錯誤逐筆清單。

## 測試策略

- **`eval_metrics`**：純單元測試 —— `prf` 邊界（含 0 分母）、`compare_sets`、`compare_mark_sets`、
  `compare_records`（scalar exact、multi P/R/F1、`record_path=None` 略過），用合成 gold/pred records。
- **`eval_marks`** smoke（`.venv-paddle`）：產 1–2 張合成圖 → 跑隱化評測 → 驗報告結構、F1 在 [0,1]。
- **`eval_pipeline`** smoke（markered/manual，需 bundle）：對 1 張合成圖跑端到端 → 驗報告結構。
- 既有測試與 policy 全綠；純度量進 CI，PIL/paddle 部分 skip/markered。

## 成功準則

- [ ] `eval_metrics` 提供 P/R/F1、`compare_sets`、`compare_mark_sets`、`compare_records`，純、CI 測過。
- [ ] `eval_marks` 對合成集輸出打勾 P/R/F1（總體＋各欄位）報告，不依賴 OCR。
- [ ] `eval_pipeline` 對合成集跑端到端、逐欄比對、輸出報告，並標註合成↔真實落差。
- [ ] 報告含 `report.json` + `report.md`；evaluator 只讀、不改管線/產生器。
- [ ] 既有測試與 policy 全綠。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 端到端因合成標籤不可讀而數字偏低被誤讀為「OCR 差」 | 中 | 中 | 報告明確標註落差；以模式 1（隱化）為可靠主標 |
| `mark_detect` 門檻對某些合成 mark 樣式判錯 | 中 | 中 | 評測本身會量出，作為調門檻的依據（這正是評測目的） |
| 大量合成圖端到端跑很慢 | 中 | 低 | 端到端 markered/manual、可限樣本數；隱化評測較快 |
| 幾何框與產圖時的框不一致 | 低 | 高 | evaluator 與產生器共用同一 `layout_render` 幾何，確保一致 |
