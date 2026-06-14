# 表單對位 + 全表勾選擷取設計（辨識準確度子專案）

**Date:** 2026-06-14
**Status:** Draft (brainstormed; pending spec review)
**Tracks:** GitHub #22（準確度部分；暖 plugin 與 agent 路線另開 #22 剩項 / #23）

---

## 背景

PR #20/#21 落地 webcam 擷取品質 + GUI + scan 橋接，但實測辨識「錯得離譜」（見 memory `webcam-recognition-limits`）。根因診斷：

- plugin 的 `field_extract.extract_fields` 只回傳 5 欄（`service_date / name / mrn / identity / gender`），**服務評估統計 A/B/C 區的全表勾選從未擷取**。
- 打勾幾何模型 `template_boxes.json` 假設**對齊掃描**；手持 webcam 沒對位 → 幾何全失效。identity/gender 退而靠脆弱的「OCR 文字異常」啟發式，兩次擷取結果不同。

關鍵發現：素材其實大致齊備——

- `plugins/paddleocr/template_boxes.json`：**全表 125 個勾選框**，每框含 `field` / `code` / canonical 座標（如 `{"field":"consultation.health_medical","code":"screening_prevention","box":[317,96.125,323,101.125]}`）。
- `plugins/paddleocr/mark_model.json` + `mark_features` + `mark_model`：判單一 crop marked/unmarked（合成勾記訓練，holdout precision 1.0 / recall 0.909）。
- `crop_provider.py`：依框裁圖。
- `form_layout`（含 `selection_to_record`）：把勾選組成 `service_record.v1` record。

真正缺的三塊：**(1) 對位 registration**（125 框是 canonical 座標，擷取影像沒對齊就全錯位）、**(2) 全表映射**（`field_extract` 只映 5 欄、未把 125 框組成完整 record）、**(3) 暖 plugin**（速度，本 spec 範圍外）。

決策前提（已與使用者確認）：

- 拆分：**本 spec = 準確度 (A 對位 + B 全表映射)**；暖 plugin 另開獨立子專案。
- 對位：**自動特徵對位 (ORB/homography) + 手動四角 fallback**。
- 對位放在 plugin，webcam 與 PDF 掃描路徑都受惠。

## 目標

把擷取/掃描影像對齊到 canonical 模板座標，讓全表 125 框用既有 `mark_model` 正確分類，組成完整 `service_record.v1` record，灌入既有 confirm UI 全欄自動填。

## 非目標（YAGNI / 另開）

- 暖 plugin / 常駐 process（速度，另開子專案）。
- 手寫姓名辨識改進（既有限制，#23 agent 路線另議）。
- 自動快門 / 即時引導。
- 不替換 OCR 文字模型；不改 `ocr_plugin.v1` 契約既有欄位語意（只新增填滿的欄位值）。

## 風險驅動的第一步：對位精度 smoke（Phase 0 gate）

最大風險＝「對位精度夠不夠裁對 ~6px 的小框」。實作第一個任務固定為**精度煙霧驗證**：

> 取一張高解析實拍服務紀錄表 → 自動對位到 canonical → 把 125 框畫回對齊後影像並輸出疊圖 → 人眼檢查框是否落在實際勾選框上；同時量「對位後該勾的框被判 marked」的命中率。

精度足夠（框對位、mark 命中明顯優於未對位）才往下蓋 B；不足則回頭調（提高擷取解析度、改特徵/比對策略，或先以手動四角為主）。設計其餘部分不受影響，因為對位被包在 `registration.py` 薄介面後。

## 架構與資料流

```
影像（webcam 擷取 / PDF 預處理影像）
  → registration.register_to_template(image, reference)        # 自動 ORB 特徵 → homography
       └─ 信心低 / 內點不足 → 回傳 RegistrationResult(needs_manual=True)
  → (needs_manual) 手動四角點選 → four_point_warp(image, corners)
  → warp 到 canonical 座標系
  → crop_provider 依 template_boxes 125 框裁圖
  → mark_model 逐框分類 marked / unmarked → marked_labels（field+code 集合）
  → field_extract.extract_fields(lines, marked_labels)         # 擴充：映射全部 125 框
  → form_layout.selection_to_record → 完整 service_record.v1 record
  → 既有 confirm UI 全欄自動填（姓名仍 name.unconfirmed）
```

各單元職責清楚、可獨立測試：

1. **`plugins/paddleocr/registration.py`（NEW，純 CV、cv2-guarded）**
   - `register_to_template(image, reference, *, min_inliers=...) -> RegistrationResult`：ORB 特徵 + BFMatcher + `findHomography(RANSAC)`，把影像對齊到空白表單 canonical 參考；回傳 `homography`、`inliers`、`confident`（內點達門檻）、`warped`（對齊後影像）。注入式 detector/matcher 供測試。
   - `four_point_warp(image, corners, size) -> warped`：手動四角透視校正（`getPerspectiveTransform` + `warpPerspective`）。
   - `RegistrationResult` dataclass：`warped` / `homography` / `inliers` / `needs_manual`。
   - **canonical 參考**＝空白服務紀錄表渲染到 canonical（重用訓練產生器的 base render；canonical 尺寸與 `template_boxes` 座標一致）。

2. **`plugins/paddleocr/main.py`（MODIFY，cv2-guarded glue）**
   - scan 路徑：對 name_crop/全頁影像先 `register_to_template`，對齊後再走既有 geometry crop + mark 分類。
   - 對位失敗/低信心：回報 `needs_manual`，由上層（app）提示手動四角；plugin 端維持安全（無對位則沿用既有行為，不崩）。

3. **`plugins/paddleocr/field_extract.py`（MODIFY）**
   - `extract_fields` 擴充：以 `marked_labels`（field+code）映射**全部** form_layout 欄位（服務項目、癌別等），不只 identity/gender；維持空字串/未選語意；單多選約束由 `form_layout` 規則套用。

4. **app（`src/ocr_from2xlsx/app.py`，MODIFY，glue）**
   - 辨識回傳 `needs_manual` 時，彈出手動四角點選 UI（在預覽影像上點 4 角）→ 重跑對位辨識。
   - 沿用既有 confirm UI；全欄自動填；姓名維持 `name.unconfirmed`。

## Mark 模型真實驗證（第二風險）

`mark_model` 為**合成勾記**訓練；真實手寫 ✓ / ✗ / 塗黑 / 圈選可能不同。設計納入：對位後在實拍上量 mark 準確率（per-box marked/unmarked）；**不足則用既有 `training/harvest_corrections` 收割實拍勾選裁圖 → `training/retrain` 重訓**，沿用 eval-gate（precision-safe）。本 spec 先建立量測；重訓視 Phase 0/實測數據決定。

## 錯誤處理

- cv2 缺席 / 對位例外：plugin 安全回退既有行為（不崩），app 顯示明確訊息。
- 對位低信心：回 `needs_manual`，app 走手動四角；使用者取消 → 維持現狀、不寫入。
- 對齊後仍無有效勾選：record 對應欄位留空（未選），不臆造。

## 測試策略

- **純 CI（`.venv`，cv2 以 `pytest.importorskip` 守）**：
  - homography 數學：給定已知變換與對應點，`register_to_template`（注入假 detector 回固定對應點）還原該變換、`confident` 門檻判斷、低內點→`needs_manual`。
  - `four_point_warp`：已知四角 → 輸出尺寸/角點落位正確。
  - 125 框 → record 映射：給定 marked field+code 集合，`extract_fields`/`selection_to_record` 產出正確 record，單選至多一、多選子集、未選留空。
- **marker / 實拍（`.venv-paddle`）**：Phase 0 精度 smoke（疊圖 + mark 命中率）；對位後 mark 準確率 eval；端到端實拍 → 全表 record。
- 既有測試與 `python -m policy_check` 全綠；`-W error` 不新增警告。

## 成功準則

- [ ] Phase 0：對位後 125 框疊圖人眼落位正確，且對位後 mark 命中率明顯優於未對位（有數字）。
- [ ] 自動對位低信心時可靠觸發手動四角 fallback；手動四角對齊精度足夠。
- [ ] 全表 125 框分類結果正確組成 `service_record.v1`（單多選約束有測試），灌入 confirm UI 全欄自動填。
- [ ] 對位後實拍 mark 準確率有量測；未達標則明確標示並啟動收割重訓路徑（不硬湊）。
- [ ] plugin 無對位資產 / cv2 缺席 / 對位失敗時行為安全（不崩、回退既有）。
- [ ] README / CHANGELOG / OpenSpec specs / policy 全部同步。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 對位精度不足裁錯 ~6px 小框 | 高 | 高 | Phase 0 先驗；手動四角 fallback；高解析擷取（8MP）；必要時 per-region 微對位 |
| 合成 mark 模型不認真實手寫勾記 | 高 | 中 | 對位後實拍量測；不足則 harvest_corrections 收割 + retrain（eval-gate） |
| 反光/遮擋/角度大 → 特徵點不足 | 中 | 中 | 內點門檻 → 退手動四角；引導使用者改善擺位 |
| canonical 參考與 template_boxes 座標不一致 | 低 | 高 | 參考與框同源（form_layout 幾何渲染）；Phase 0 疊圖驗證 |
| 全表映射的單多選約束遺漏 | 中 | 中 | 純測試覆蓋 form_layout 約束；對照訓練產生器 selection_to_record |
