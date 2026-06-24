# Webcam 擷取品質與辨識串接設計

**Date:** 2026-06-13
**Status:** Draft (brainstormed with empirical demos; pending spec review)

---

## 背景與實證

PR #20 讓 app 能即時預覽 webcam，但「webcam → 辨識」未串接。實際 demo（直接把 webcam 畫面餵現有 PaddleOCR plugin）一開始**辨識全空**，逐步診斷出真因：

| 擷取條件 | 解析度 | Laplacian 清晰度 | OCR raw_text | 結果 |
| --- | --- | --- | --- | --- |
| 手持傾斜、半畫面、1080p、無對焦 | 1920×1080 | 18.5 | 25 字 | 全空 |
| 側躺 90°、1080p、無對焦 | 1920×1080 | 18.5 | 25 字 | 全空（含誤判 mark） |
| **壓平正對、打光、自動對焦、足解析度** | **3264×2448** | **187.6** | **1324 字** | **service_date `2025-06-25`、identity `patient`、gender `female` 全對，表單全文辨識** |

**關鍵結論**：辨識失敗的主因是**擷取品質（解析度 + 對焦）**，不是缺去斜/對位/增強軟體。開自動對焦 + 用足相機最高解析度（此機 8MP）+ 打光後，現有管線就能正確辨識文字欄位。另外實測 PaddleOCR 內建方向分類 + 去扭曲（plugin 目前關閉）能把偵測文字量提升（25→86 字）但無法救回模糊輸入——印證「模糊無法用軟體事後修復，只能在擷取端避免」。

決策前提（已與使用者確認）：

- **形態**：可重用擷取/品質核心，**同時**供獨立 CLI 與 app「擷取並辨識」按鈕呼叫。
- **打勾**：v1 為 best-effort（identity/gender 已透過 OCR 文字訊號正確辨識）；精準打勾所需的模板對位（registration）延後為獨立子專案。
- **自動快門/即時引導**：延後；v1 為手動擷取 + 品質閘 + 重拍提示。
- v1 三件都要做：擷取品質、影像條件化保險層、手寫姓名/病歷號辨識改進。

## 目標

把 webcam 變成可用的掃描輸入：手動擷取一張高品質影像 → 現有 OCR plugin → normalized JSON → app 自動填表單 / CLI 輸出，並用清晰度品質閘擋掉糊照、提示重拍。

## 非目標（YAGNI / 延後）

- 不做模板對位（feature-based registration）；精準幾何打勾留待後續。
- 不做自動快門與即時文件框引導（留待 app 子專案）。
- 不替換或重訓任何 OCR 模型；不改 `ocr_plugin.v1` 契約的既有欄位語意。
- 不支援多頁拼接、不做超解析度。

## 架構與資料流

```
[app 按鈕 / CLI]
   → capture_still(index)           # 開 AF + 最高解析度 + 暖機，回傳 frame + 品質指標
   → quality gate (sharpness)       # 太糊則拒收、回報重拍；不進 OCR
   → (Phase B) condition(frame)     # 可選：方向/去扭曲 + OpenCV 增強，gated、可量測決定保留與否
   → save image
   → bridge: image → plugin OCR     # 重用現有 plugin；產出 service_record.v1 batch JSON
   → app 載入 JSON 自動填表單 / CLI 寫出 JSON
```

各單元職責清楚、可獨立測試：

1. **擷取品質核心（`capture.py` 擴充）**
   - `measure_sharpness(gray) -> float`：純函式（Laplacian variance），給定影像陣列即可測，CI 可測。
   - `capture_still(index, *, min_sharpness, ...) -> CaptureResult`：cv2-guarded。開 `CAP_PROP_AUTOFOCUS=1`、**拉滿相機原生最高解析度**、暖機 ~80 frames 讓 AF 鎖定，回傳 `frame`、`resolution`、`sharpness`、`brightness`、`passed`（是否過清晰度閘）。
   - `negotiate_max_resolution(cap)`：**不寫死目標解析度**——請求一個超大值（如 10000×10000）讓 driver clamp 到實機上限，再讀回 `CAP_PROP_FRAME_WIDTH/HEIGHT` 取得真實最大值並沿用。確保不浪費高階相機（如 demo 機讀回 3264×2448 8MP；更高階相機自動吃滿其上限）。
   - 沿用既有 `enumerate_cameras` / `decide_camera_selection`。

2. **影像條件化（Phase B，`document_condition.py`，cv2-guarded、預設關、可量測）**
   - `enhance(frame) -> frame`：灰階、必要時放大到目標長邊、CLAHE 對比、輕度去噪。純 cv2，給定陣列可測形狀/型別。
   - plugin 方向/去扭曲開關：webcam 路徑可開啟 `use_doc_orientation_classify` / `use_doc_unwarping`（透過 request 旗標或 env），掃描路徑預設不變。
   - 驗收以 eval harness 量測：條件化後辨識若無提升則不納入預設流程（避免無效複雜度）。

3. **webcam → OCR 橋接**
   - 擴充記錄準備路徑以接受「靜態影像輸入」（webcam 擷取或檔案），直接交給現有 plugin（demo 已證明 plugin 可直接吃影像），輸出與現行一致的 `service_record.v1` batch JSON（重用既有 record_id 指派、normalization、name-agent 掛點）。
   - app「擷取並辨識」按鈕：`capture_still`（含品質閘）→ 橋接 → 載入 JSON 自動填表單；任何失敗（無相機/太糊/OCR 失敗）給明確訊息，不中斷 app。
   - CLI：擷取或指定影像檔 → 橋接 → 寫出 JSON。

4. **手寫姓名 / 病歷號辨識改進（Phase C，`field_extract.py` / `name_crop.py`）**
   - 現況：good capture 下 name_crop 仍 `None`、MRN 未抓到。改進姓名錨點定位（在 OCR 結果中定位姓名欄並裁圖供 name_rec 模型辨識）與病歷號擷取（anchor + digit run）在實拍表單上的命中率。
   - 屬辨識邏輯調校（與擷取無關），不確定性較高；以 eval harness 量測改進幅度。

## 評測 harness（跨階段）

- 提交一張**良品實拍**填寫表單影像 fixture + 其 ground-truth 欄位（service_date/identity/gender/name/mrn + 已勾選項）。
- harness：fixture 影像 → plugin OCR → 與 ground truth 比對，輸出 per-field 命中與整體分數（report.json/md）。
- 此測試需 paddle，列為 marker / `.venv-paddle` 測試（非預設 CI）；純邏輯（sharpness、gate 決策、影像→PDF/wrap、CLI wiring）走預設 CI。

## 錯誤處理

- 無可用相機 / cv2 缺席：app 維持既有預覽與 JSON 流程；CLI 給明確錯誤。
- 清晰度未過閘：不進 OCR，回報「太模糊，請重拍（調整對焦/光線/距離）」並附分數。
- OCR 失敗 / plugin 缺席：回退既有行為，記錄訊息。

## 測試策略

- **純 CI（`.venv`）**：`measure_sharpness` 數值性質；品質閘決策（過/不過/邊界）；影像輸入 → batch JSON 的 wrapping 與 record_id；CLI 參數與 app 按鈕 handler 的純邏輯（monkeypatch 擷取與橋接）。
- **marker（`.venv-paddle`）**：`capture_still` 真機擷取（手動驗證）；fixture 影像端到端 eval harness；Phase B 條件化前後對照；Phase C 姓名/MRN 命中率。
- 既有測試與 `python -m policy_check` 全綠；`-W error` 不新增警告。

## 成功準則

- [ ] `capture_still` 拉滿相機原生最高解析度（讀回實際值，不寫死），良好擺位下穩定產出 sharpness >100 的影像（手動驗證 + 量測）。
- [ ] 清晰度品質閘擋下糊照並提示重拍（純測試覆蓋決策）。
- [ ] webcam/影像 → OCR → batch JSON → app 自動填表單，service_date/identity/gender 在良品擷取下正確（eval harness）。
- [ ] Phase B 條件化「只有在量測顯示提升時」才納入預設；否則保留為可選旗標並記錄結論。
- [ ] Phase C 姓名/MRN 命中率較現況提升（eval harness 有數字）；未達標則明確標示限制。
- [ ] README / CHANGELOG / OpenSpec specs / policy 全部同步。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 不同相機/驅動的 AF 與最高解析度設定行為不一 | 中 | 中 | 請求後讀回實際值；暖機讓 AF 鎖定；清晰度閘把關，糊就重拍 |
| Phase B 條件化對 good capture 無益甚至有害 | 中 | 低 | eval harness 量測前後；無提升則不納入預設、僅留可選旗標 |
| Phase C 姓名/MRN 改進在實拍多樣性下不穩 | 高 | 中 | 以實拍 fixture 量測；達不到就縮為「標示未確認、人工補」，不硬塞 |
| 啟用 paddle 方向/去扭曲影響既有掃描路徑 | 低 | 中 | 僅 webcam 路徑開啟，掃描路徑預設不變；回歸測試保護 |
| 8MP 影像體積/OCR 時間 | 低 | 低 | 單張；必要時下採樣到辨識足夠的長邊 |
```
