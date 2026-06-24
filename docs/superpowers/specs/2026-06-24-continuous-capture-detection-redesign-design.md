# 連續拍照偵測重設計（空桌基準法）設計

**Date:** 2026-06-24
**Status:** Draft (brainstormed; pending spec review)
**Supersedes:** `docs/superpowers/specs/2026-06-22-continuous-capture-design.md` 的**偵測（換頁/新張判定）**段落——原「pixel-diff vs 上一張已拍表單」改為「diff vs 空桌基準」。其餘（hands-free、capture_still 重拍、合焦確認、批次辨識進審核）維持。
**Related:** 對抗性 review 找到的 Critical/Important；校正進度 resume 另立 issue #37（本次不做）。

---

## 背景：為什麼要重設計

原設計用 `change_from_ref`（新表單 vs **上一張已拍的表單**）判定「新張」。對本工具的真實用途——掃**一疊同一版型**的服務紀錄表（每張 ~99% 相同，只差手寫/勾選）——此訊號失效：

- 對抗 review 以真實管線實測：兩張同版型表單經 `to_metric_gray(width=320)` + `mean_abs_diff` 後差異 **≈1.6**，遠低於 `newpage_thresh=12` → **第二張永不自動拍**。
- 該訊號量的是「**移動**」不是「**內容**」，且任何 ≥2px 位移就飽和到 ~13–18 → **調門檻救不了**（對齊→永遠不拍；微移→會拍但重放同一張也重拍）。

對抗 review（4 個攻擊視角）另查出並一併修正：CJK 路徑 `cv2.imwrite` 靜默失敗→retry storm、STALLED 無限快門迴圈、convergence 單向（邊對焦邊拍/失焦也算收斂）、相機消失/辨識失敗造成已拍 stills 資料遺失。

## 決策前提（已與使用者確認）

| 議題 | 決定 |
| --- | --- |
| 偵測訊號 | **空桌基準差異法**：`diff_from_baseline`（current vs 本 session 空桌基準），取代 form-vs-last-form |
| 比對範圍 | **中央 ROI**（預設中央 ~65%，可設）——避開邊緣手伸入/背景雜訊 |
| 基準擷取 | **開始明確擷取**（提示清空桌面）＋**「重設空桌基準」鈕**；不自動刷新 |
| 去重 | **淨空循環**：拍完必須回到接近基準才再武裝（同張留著永不重拍） |
| CJK 寫檔 | `imencode`+`write_bytes`，**僅套新連續路徑**，不動既有單張 `_recognize_capture` |
| STALLED | 進 **PAUSED 停著等使用者**，不自動恢復 |
| convergence | 改 **`abs(sharpness−last) ≤ tol`**（收斂＝穩定，非單純「不上升」） |
| 資料不遺失 | 相機消失 / 辨識失敗時**保留 stills 可完成/重試** |
| 辨識完成 | 批次辨識完跳**「辨識完成」對話框**，再進既有逐張審核 |
| 校正 resume | **另案 issue #37**，本次不做 |

## 目標

讓連續拍照對「一疊同版型表單」可靠運作：以空桌基準（中央 ROI）判定在位/淨空，淨空循環去重，合焦由 `capture_still` 權威把關；並修掉對抗 review 的 Critical/Important。連拍完按「完成辨識」→ 全部批次辨識 → 「辨識完成」對話框 → 既有逐張審核（每張 confirm→即時寫 xlsx→下一張）。

## 非目標（YAGNI / 延後）

- 校正進度暫存／resume（issue #37）。
- 不改辨識後端、`service_record.v1`、`workbook.py`、審核 UI 語意（僅新增「辨識完成」對話框）。
- 不動既有單張 `_recognize_capture` 與資料夾批次的辨識本身（CJK 修正只套新路徑）。
- 不做文件區域/輪廓偵測、超解析度、live 逐幀方向偵測。

## 偵測狀態機（`autocapture` 改寫）

`FrameMetrics` 改為：`motion`（vs 前一幀，判靜止）、`diff_from_baseline`（vs 空桌基準，判在位/淨空）、`sharpness`。**移除** `change_from_ref`。所有影像數學在**中央 ROI 下採樣灰階**上做；baseline 與 current 用同一 ROI 取法。狀態機仍只吃純量、不碰 cv2。

狀態：`NEED_BASELINE` → `ARMED` → `DISARMED` →（淨空）→ `ARMED`；另有 `PAUSED`。
- `NEED_BASELINE`：`observe` 一律回 NONE（尚未設基準）。
- `set_baseline()`：設定基準 → `ARMED`。
- **ARMED → CAPTURE**：`diff_from_baseline ≥ present_thresh`（在位）＋ `motion < motion_thresh`（靜止）＋ `sharpness ≥ preview_min_sharpness` 且 `abs(sharpness − last) ≤ settle_tol`（合焦收斂）連續 `stable_frames` 幀。
- `mark_captured()` → `DISARMED` ＋ `cooldown`（**不更新 baseline**——基準永遠是空桌）。
- **DISARMED → ARMED**：`diff_from_baseline ≤ clear_thresh` 連續 `clear_frames` 幀（回到空桌）。`clear_thresh < present_thresh`（遲滯）。
- `note_failed_capture()`：連續 `retry_limit` 次（全解析度太模糊）→ **`PAUSED`**（`observe` 回 NONE，直到 app 重設基準/重啟）。

門檻：`present_thresh` / `clear_thresh` / `clear_frames` / `motion_thresh` / `stable_frames` / `preview_min_sharpness` / `settle_tol` / `cooldown_frames` / `retry_limit` / `roi_fraction`，皆 `AUTOCAPTURE_*` env 可覆寫、實機校準。

## App 整合（`app.py`）

- **基準擷取 UX**：按「連續拍照」→ 選輸出夾 →「請清空桌面後確定」對話框 → 擷取一張穩定空桌、取**中央 ROI 灰階**為基準 → `set_baseline` → 開始偵測。新增 **「重設空桌基準」** 鈕隨時重抓（背景/光線變了、或 PAUSED 後恢復）。
- `_observe_autocapture_frame`：`diff_from_baseline = mean_abs_diff(roi_gray, baseline_roi_gray)`、`motion = mean_abs_diff(roi_gray, prev_roi_gray)`、`sharpness`。餵 detector。**不再需要 ref_gray 管理**。
- `_perform_autocapture`：CAPTURE → `capture_still`（合焦權威 gate）→ **CJK 安全寫檔** `_imwrite_unicode(path, frame)`（`cv2.imencode('.png', frame)` + `Path.write_bytes`，取代 `cv2.imwrite`；**僅此新路徑**）→ 成功才 append + shutter。寫檔失敗：訊息＋`note_failed_capture`/cooldown，不 retry storm。
- **STALLED → 暫停**：detector 回 STALLED → app 暫停 session（停止自動拍）、訊息「連續多張太模糊，已暫停；調整後請按『重設空桌基準』或重新開始」。
- **完成辨識**：批次辨識（`prepare_records_from_images` + 進度 modal）→ 跳 **「辨識完成」對話框** → `_set_loaded_records` 進既有逐張審核。
- **資料不遺失**：
  - 相機中途消失：保留已拍 stills，提示「相機中斷，已擷取 N 張」；**「完成辨識」改為只要有 stills 就能執行**（不再被 `_autocapture_active` 擋死）。
  - 「完成辨識」辨識失敗：保留 stills、可重試（不一次失敗就永久卡死）。

## 測試（含回歸守門）

- **detector 純測（無 cv2）**：無基準不拍；在位＋靜止＋收斂→CAPTURE；淨空才 REARMED；**同版型一疊回歸守門**——baseline=空桌，form1 高 `diff_from_baseline`→拍，淨空（diff→~0）→再武裝，**form2 對空桌仍高 diff→拍（即使 form2 ≈ form1）**；STALLED→PAUSED 後 `observe` 不再 CAPTURE（不迴圈）；`abs` 收斂（失焦下降不算收斂）；ROI 只看中央（邊緣變化不影響）。
- **指標 helper**：中央 ROI 裁切 + `mean_abs_diff`（小 numpy 陣列）。
- **app 測**：基準擷取設定 detector baseline；「重設空桌基準」重設；**CJK 路徑寫檔成功**（寫進中文名資料夾並斷言檔案存在）；相機消失後 stills 仍可「完成辨識」；辨識失敗可重試；「辨識完成」對話框出現後才進審核。

## 落地備註

- 更新 openspec change `add-continuous-capture`（delta：修正/補上偵測 requirement 與 scenarios，反映 baseline 法、PAUSED、資料回復）。
- `CHANGELOG.md [Unreleased]` 更新；本 spec supersede 2026-06-22 設計的偵測段。
- 實作續走 subagent 逐任務 + **對抗性 review**（這次偵測一定要有同版型一疊的回歸測試擋著）。
- 分支沿用 worktree `wt/bootstrap-ocr-design/continuous-capture`。
