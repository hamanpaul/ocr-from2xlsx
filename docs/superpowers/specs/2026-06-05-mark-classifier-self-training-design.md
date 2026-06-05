# 打勾分類器自我訓練閉環設計

**Date:** 2026-06-05
**Status:** Draft (brainstorming approved; pending spec review)

---

## 背景

合成集評測（`add-synthetic-eval`，已合併）量出打勾偵測在 35 張合成表單上 **precision 1.000 / recall 0.716 / F1 0.834**：零誤報，但漏掉約 28% 的真實勾記，且各欄位 recall 落差極大（`nationality` 1.00、`nutrition_diet` 0.98 對上 `identity` 0.40、`supplies` 0.56）。根因是現行 `plugins/paddleocr/mark_detect.is_marked` 用一條固定門檻 `dark_ratio ≥ 0.12`，對「不同大小的框、不同記號樣式（✓／劃-／局部塗黑）」一視同仁。

此外，live plugin 的實際打勾路徑 `detect_marked_labels` 是「OCR 標籤錨點」式，且只探測少數 probe 標籤（gender/identity），多數欄位的打勾框在真實掃描上其實沒在抓；而合成/評測路徑用的是「已知模板幾何框」（`layout_render.option_mark_box`）。這個落差是合成↔真實的核心問題。

本子專案以一個**學習式的每框 marked/unmarked 分類器**取代固定門檻，並建立**自我訓練閉環**：以合成答案卷 bootstrap，持續用每張掃描的人工確認/修正回補語料、自動重訓、自動 eval 把關後重佈。

## 目標

- 用**手工特徵 + 輕量模型**判定每個打勾框是否被勾，導出**純權重**，plugin 端只用 numpy 推論（零新增 runtime 依賴）。
- 把現行只覆蓋少數欄位的 live 打勾偵測，擴成**對齊影像上以已知框逐框分類、覆蓋全部選項**。
- 建立完整閉環：合成 bootstrap → 推論 → 人工確認收割標註裁切 → 自動重訓 → **自動 eval-gate（不退化才換權重）** → 重佈。
- precision 安全：重訓重佈絕不讓誤報上升（醫療情境：誤判「有勾」＝記下沒發生的服務）；生產端 GUI 人工確認為最終防線。
- 以 `CropProvider` 介面與**模板對位（registration）子專案**銜接；本 spec 不實作 registration，提供介面與 Geometry 實作。

## 非目標（YAGNI）

- 不實作模板對位 registration（角點/錨點偵測＋透視校正）——另立子專案，實作同一個 `CropProvider` 介面後插入本閉環。
- 不做 CNN／深度模型（輕量線性模型即可；保留同一「導出純權重＋numpy 推論」契約以便日後替換）。
- 不改 OCR 文字辨識、產生器答案卷格式、`form_layout`、confirm 流程的對外行為。
- 不在 plugin runtime 引入 sklearn 等重依賴（只在離線訓練使用）。

## 範圍與分解

整個系統含兩個可分離的子系統，以 `CropProvider` 介面銜接：

1. **模板對位 registration（獨立子專案，本 spec 不做）**：原始 webcam 影像 → 偵測表單四角/錨點 → 透視校正對齊到標準模板 → 輸出「選項框落在已知幾何」的對齊影像。獨立可測（對合成圖施加透視扭曲再量重對位誤差），且對整條 OCR 管線都有益。

2. **打勾分類器 + 自我訓練閉環（本 spec）**：消費 `CropProvider` 給出的每框裁切，分類 marked/unmarked，收割人工修正成標註裁切，自動重訓、自動 eval-gate 重佈，整合進 plugin。

`CropProvider` 兩種實作：
- `GeometryCropProvider`——已知框（合成圖、已對齊影像）。閉環**今天就能在它上面端到端運轉**（合成資料可無限產、真實資料 ≈ 0）。
- `RegistrationCropProvider`——對齊原始掃描後再用已知框（子專案 1 產出，插同一介面）。registration 落地後，合成訓練輸入與真實推論輸入**完全一致**，消除合成↔真實落差。

## 位置與環境

推論碼必須能在獨立 plugin bundle（自帶 venv，僅 numpy+stdlib 可用、無法 import 主套件）內執行；訓練/收割/eval-gate 為離線、可用重依賴。

```
plugins/paddleocr/
  mark_features.py       NEW. 裁切→geometry-normalized 特徵向量（只用 numpy+stdlib）。
  mark_model.py          NEW. 載入 mark_model.json、預測；無權重退回 is_marked。
  crop_provider.py       NEW. CropProvider 介面 + GeometryCropProvider（讀 template_boxes.json）。
  template_boxes.json    NEW(離線產). 標準模板每個選項的已知框（由 layout_render 匯出）。
  mark_detect.py         既有. is_marked 保底；detect_marked_labels 作為未對齊影像的退路。
  main.py                MODIFY. 對齊影像走 crop_provider+mark_model；否則維持 detect_marked_labels。

training/
  export_template_boxes.py  NEW. 由 layout_render 匯出 template_boxes.json（離線、可測一致性）。
  mark_dataset.py           NEW. 裁切語料的 manifest 讀寫（JSONL + 小圖）；合成與修正同格式。
  harvest_corrections.py    NEW. 由「確認後 record + 影像 + CropProvider」產出標註裁切，append 進語料。
  train_mark_model.py       NEW. 語料→抽特徵(path import mark_features)→fit 輕量模型→挑 operating point→導出純權重。
  eval_gate.py              NEW. 候選 vs 現行權重在留出集上的採用/拒用決策（純）。
  out/mark_dataset/         (gitignored) 裁切語料 manifest + 小圖。

src/ocr_from2xlsx/
  session.py / confirm 流程  MODIFY(小). 確認產生修正時，呼叫 harvest + 觸發重訓（離線端）。
```

**權重檔解析順序**（離線 trainer 與 plugin 都能存取、又不污染 bundle）：
`環境變數/設定檔指定路徑` → `使用者資料夾的 runtime 權重`（重訓寫此）→ `plugin bundle 內附 baseline 權重` → 無 → 退回 `is_marked`。

## 元件（盡量純、可測）

| 元件 | 純度 | 職責 |
| --- | --- | --- |
| `mark_features` | 純(numpy) | 裁切先**縮放到固定網格（24×24 灰階）**再抽 ~10–12 維可解釋特徵（見下）。框大小差異於此消除。 |
| `mark_model` | 純(numpy) | 讀 `mark_model.json`：標準化→內積→sigmoid→比 threshold；無權重 → 退回 `is_marked`。 |
| `crop_provider` | PIL | 介面：影像 → `{(field,code): crop}`。Geometry 實作讀 `template_boxes.json`。 |
| `export_template_boxes` | 半純 | 由 `layout_render.option_mark_box` 匯出標準模板框；一致性可測（防漂移）。 |
| `mark_dataset` | 純/IO | 裁切語料 manifest（JSONL：crop 檔名、label、field、code、source(synthetic\|correction)、time、provider）+ 小圖。 |
| `harvest_corrections` | PIL | 確認後 record（真值已勾集合）+ 影像 + CropProvider → 逐框裁切＋標籤 append 進語料。 |
| `train_mark_model` | 離線 | 合成 ∪ 修正語料 → 抽特徵 → fit logistic → 挑 operating point → 導出純權重。 |
| `eval_gate` | 純 | 候選權重在留出集 eval：`recall↑ 且 precision ≥ 門檻` 才採用；否則保留舊權重；記稽核 log。 |

### 特徵（geometry-normalized、純 numpy、約 10–12 維）

裁切先縮放到固定網格再計算：
- `dark_ratio`：整體墨跡比例。
- 墨跡重心相對框中心 `(dx, dy)`。
- 墨跡 bounding box 正規化寬、高。
- 列/行投影：有墨列數、有墨行數、最長連續墨跡段。
- 對角帶墨跡比（✓ 的對角結構）。
- 平均每列 暗↔亮 轉換次數（區分筆畫 vs 均勻塗黑/糊）。

### 模型與權重格式

邏輯斯迴歸（線性權重＋偏置＋特徵標準化）；離線可用 sklearn fit，**只導出純權重**。先做**單一全域模型**（縮放正規化後框大小差異已消除）；某欄位長期偏差時再加 field-id 類別特徵（YAGNI）。

```json
{
  "version": 1,
  "feature_names": ["dark_ratio", "centroid_dx", "centroid_dy", "ink_w", "ink_h",
                    "rows_with_ink", "cols_with_ink", "max_run", "diag_ratio", "row_transitions"],
  "mean": [...], "std": [...],
  "coef": [...], "intercept": -1.23,
  "threshold": 0.78,
  "trained_at": "2026-06-05T00:00:00Z",
  "train_counts": {"synthetic": 1167, "correction": 0}
}
```

**precision 安全 — operating point**：fit 後不用 0.5，而在驗證切片上挑「precision ≥ 門檻(預設 0.99) 前提下 recall 最大」的機率門檻，存進權重。這是「自動重訓也不會讓誤報上升」的機制來源。

## 閉環生命週期與資料流

1. **bootstrap**：產生器產合成圖＋答案卷 → `GeometryCropProvider` 裁每框 → 配答案卷標籤成初始語料 → 訓出 v1 權重。
2. **推論**：plugin → CropProvider 出框 → `mark_features` → `mark_model` 逐框判定 → 組進 record；**無權重退回 `is_marked`**。
3. **人工確認/修正（每張都經過）**：人在 GUI 確認後的「已勾集合」即真值 → 同一 CropProvider 裁該影像每框、標上確認後標籤 → append 語料（打勾裁切不含個資，可保存）。
4. **自動重訓**：一個確認 session 若產生 ≥1 筆修正，自動觸發；在「合成 ∪ 修正」語料上重抽特徵、重 fit、挑 operating point → 候選權重。
5. **自動 eval-gate 重佈**：候選在固定留出集（種子固定的合成留出集 ＋ 累積足量後的真實修正留出集）跑 eval；**recall↑ 且 precision ≥ 門檻才寫 runtime 權重路徑**，否則保留舊權重並記「未採用」原因；全自動、無人工核可（生產端人工確認為最終防線）。

**跨行程**：plugin 為獨立 bundle/venv，閉環靠**共享檔案**跨界——收割寫「裁切語料夾」、重訓寫「runtime 權重」、plugin 下次推論讀該權重；雙方共用 `mark_features`（path import）與 `template_boxes.json`。

## plugin 整合（含覆蓋率修補）與安全

- 對齊影像（合成／日後 registration 輸出）→ `GeometryCropProvider` 出**所有選項框** → 有權重走分類器、無權重退回 `is_marked`（同一組框，覆蓋率已優於現況）。
- 未對齊影像（registration 落地前的原始 webcam）→ 維持現有 `detect_marked_labels`。
- registration 子專案落地後，真實掃描走 GeometryCropProvider，分類器覆蓋全欄位。
- `ocr_plugin.v1` JSON 契約不變；新增分類器為內部變更。

**安全層層**：① threshold 保 precision ② 重佈前自動 eval-gate ③ 無權重退回 is_marked ④ 生產端 GUI 人工確認為最終防線，分類器輸出僅為「建議」絕不直接寫 xlsx ⑤ 每次重佈把「採用/未採用＋指標」寫入稽核 log（醫療可追溯）。
**依賴保證**：plugin runtime 仍只 numpy+stdlib（讀 JSON 權重）、零新增 runtime 依賴；sklearn 只在離線訓練用。

## 測試策略

**純單元（CI，`.venv`）**
- `mark_features`：手工裁切（✓／空白／單點雜訊／均勻塗黑）→ 各維落在預期範圍、可重現。
- `mark_model`：給定權重＋特徵 → 預測等於手算 sigmoid/threshold；無權重 → 退回 `is_marked`。
- operating-point：給定標註分數 → 挑出的 threshold 滿足 precision ≥ 門檻且 recall 最大。
- **eval-gate（醫療安全核心）**：recall↑ 且 precision ≥ 門檻才採用；**蓄意給 precision 掉到門檻下的候選 → 必須拒用、保留舊權重**。
- `template_boxes.json` 一致性：匯出框等於 `layout_render.option_mark_box`（防漂移）。

**較重 / marker（`.venv-paddle`／訓練環境）**
- `GeometryCropProvider`：合成圖上裁框座標正確（PIL）。
- 收割：合成圖＋確認後 record → 產 N 筆標註裁切，標籤與 `record_marks` 一致。
- `train_mark_model` 端到端：小合成批 → 產權重 → 留出集上 **recall 勝過 `is_marked` baseline(0.72) 且 precision ≥ 0.99**（smoke）。
- plugin 整合：載入訓練後權重對合成圖判定，eval 勝過 baseline（需 bundle，marker）。
- 既有測試與 policy 全綠；純邏輯進 CI，sklearn/PIL 部分 marker。

## 成功準則

- [ ] 合成 eval 上分類器 recall 明顯 > 0.72 baseline，且 precision ≥ 0.99。
- [ ] 收割 → 自動重訓 → 自動 eval-gate → 只在不退化時換權重；退化候選被拒（有測試證明）。
- [ ] plugin 維持離線、零新增 runtime 依賴；無權重優雅退回 `is_marked`。
- [ ] 訓練與推論共用同一份 `mark_features`；`template_boxes.json` 與 `layout_render` 一致（有測試）。
- [ ] registration 以 `CropProvider` 介面銜接（本 spec 留介面 + Geometry 實作，不實作 registration）。
- [ ] 既有測試與 policy 全綠。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 自動重訓引入退化（誤報上升）| 中 | 高 | operating point 保 precision ＋ 重佈前自動 eval-gate 擋退化 ＋ 生產端人工確認 |
| 合成↔真實落差使分類器轉移有限 | 中 | 中 | registration 使兩端輸入一致；真實修正持續回補語料；以人工確認為底線 |
| 模型對合成渲染過擬合 | 中 | 中 | 用少量可解釋特徵＋線性模型（非 CNN）；留出集評測；真實修正進語料校正 |
| 真實修正樣本長期偏少（冷啟動）| 高 | 中 | 合成語料 bootstrap 足以先勝過固定門檻；修正只是持續微調 |
| `template_boxes.json` 與 layout 漂移 | 低 | 高 | 離線匯出＋一致性測試守門；產生器/收割/推論共用同一組框 |
| 跨行程權重/語料路徑不一致 | 中 | 中 | 單一解析順序（env/設定→runtime→bundle→is_marked），集中於 model loader |
