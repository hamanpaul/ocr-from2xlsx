# 連續拍照（hands-free 自動掃描）設計

**Date:** 2026-06-22
**Status:** Draft (brainstormed; pending spec review)
**Builds on:**
- `docs/superpowers/specs/2026-06-13-webcam-capture-quality-design.md`（`capture_still` / 清晰度量測）
- `docs/superpowers/specs/2026-06-14-offline-vlm-assisted-recognition-design.md`（辨識後端：本機 VLM 預填）
- PR #30 圖片/PDF 批次處理（`scan.prepare_records_from_folder` / 逐筆審核左側顯示原圖）

---

## 背景

辨識策略已定案：**批次處理 + 本機小模型（VLM）做中文手寫識別**。現有兩條輸入路徑：

| 路徑 | 行為 | 缺口 |
| --- | --- | --- |
| 單張 webcam 擷取（`擷取並辨識` / `_capture_and_recognize`） | 選相機→停預覽→`capture_still` 拍一張→`_recognize_capture` 跑後端→進審核 | **一拍一審**，無法連續掃一疊 |
| 資料夾批次（`匯入資料夾批次` / `prepare_records_from_folder`） | 選含圖片/PDF 的資料夾→全部辨識合併成一批→逐筆審核（左側顯示原圖） | 來源是**既有檔案**，不是現場相機 |

本案補上中間那條：**用相機現場連續掃一疊紙本**——一張張放鏡頭下，自動偵測→合焦確認→拍照→累積成批，最後一次批次辨識、進既有逐筆審核。

## 決策前提（已與使用者確認）

| 議題 | 決定 | 理由 |
| --- | --- | --- |
| 觸發方式 | **自動偵測拍照（hands-free）** | 使用者明定；最省手 |
| 換頁判定 | **拿開再放**：拍完要先偵測到「畫面相對上一張大幅改變（紙被拿走/換掉）」才重新武裝 | 最不會重複拍同一張 |
| 辨識時機 | **拍完整疊再一次批次辨識** → 進既有逐筆審核 | 最單純、重用最多；不做邊拍邊辨/邊拍邊審 |
| 拍攝來源 | **觸發後 `capture_still` 重拍**（重開相機＋autofocus warmup＋清晰度 gate）取高解析度 | 沿用最成熟單張路徑；合焦由 `capture_still` 權威把關 |
| 合焦要求 | **必須確認鏡頭合焦後再拍**：銳利度到頂且不再上升＋畫面穩定才觸發；`capture_still` 再做權威 gate | 使用者明定；autofocus 搜尋途中不可拍 |
| 拍照回授 | **咔嚓快門音**（bundled `shutter.wav`，`winsound.PlaySound` async）＋預覽邊框閃光 | hands-free 看不到螢幕也要知道拍到了 |
| 誤拍救援 | **保留「復原上一張」**（刪最後一張 still、計數-1） | 自動偵測必有誤拍，需就地救援 |
| 門檻調校 | **合理預設 + env 覆寫 + 實機校準**（比照 `OCR_BACKEND`/`SCAN_DOC_PREPROCESS`） | 門檻與相機/光線相關，需現場微調 |

## 目標

工具列一鍵開始「連續拍照」session：相機 live 預覽持續監看，偵測到「放上新表單→畫面穩定→合焦收斂」就自動 `capture_still` 拍高解析度、存檔、計數、咔嚓回授；偵測到「紙被拿走/換掉」就重新武裝等下一張。按「完成並辨識」把整疊 stills 餵進既有 `prepare_records_from_images` → 進既有逐筆審核（左側顯示每張原圖）。

## 非目標（YAGNI / 延後）

- 不做邊拍邊背景辨識、不做邊拍邊審、不做多頁併一筆。
- 不改辨識後端、`service_record.v1` schema、`workbook.py`、`confirm_form` 審核 UI 與 `prepare_records_from_images` 既有語意。
- 不做純機器自動裁邊/超解析度/畫面引導框。
- 不做 live 預覽逐幀方向偵測（CPU 不可行，沿用既有「旋轉」設定）。

## 架構：留 / 新

| | 元件 | 處置 |
| --- | --- | --- |
| **留** | `capture.capture_still` / `rotate_frame` / `measure_sharpness` / `passes_sharpness_gate` / `DEFAULT_MIN_SHARPNESS` / `open_camera_capture` | 沿用 |
| **留＋小擴充** | `scan.prepare_records_from_images`（吃 list[stills]，正是連拍要的）；**新增可選 `on_progress(done, total, name)`** 比照 `prepare_records_from_folder` 以驅動進度 modal / `next_output_artifact_path` | 沿用＋小擴充 |
| **留** | `app._resolve_recognition_backend` / `_open_processing_modal` / `_set_modal_message` / `_set_loaded_records` / `JsonRecordSource` / `dump_batch` / `_resolve_template` | 沿用 |
| **留** | live 預覽迴圈 `app._poll_camera_frame` / `_start_camera` / `_stop_camera` / `self._preview_rotation` | 沿用，掛上偵測 |
| **新** | `autocapture.py`：純偵測狀態機（state machine）+ cv2 薄包裝（frame metrics） | 新增（唯一新核心邏輯） |
| **新** | `app.py`：「連續拍照」鈕 + session 流程 + 狀態/計數/回授 + 完成/取消/復原 | 新增 |
| **新** | `assets/shutter.wav` 快門音資產 + 打包納入 | 新增 |

## 資料流（end to end）

```
按「連續拍照」
  └ 前置擋：require_camera_support()、需已選相機、editing 未存檔則擋下
  └ 選一次輸出資料夾（比照 _import_folder_batch）
  └ 啟動 live 預覽（_start_camera），進 ARMED
       每幀(_poll_camera_frame)：算 FrameMetrics → 餵 AutoCaptureDetector.observe()
         ├ 回 CAPTURE：停預覽 → capture_still(index, min_sharpness=DEFAULT_MIN_SHARPNESS)
         │     ├ passed → rotate_frame(self._preview_rotation) → 存 scan-capture-NNNN.png
         │     │           → 計數+1、咔嚓音、預覽閃光、detector.mark_captured(ref) → 進 DISARMED
         │     │           → 重啟預覽
         │     └ None/not passed → 不存、狀態列提示、冷卻 → 重啟預覽、留 ARMED（重試上限內）
         └ 回 REARMED：狀態列「請放上下一張」
  └ 按「復原上一張」：刪最後 still、計數-1、detector 清掉該 ref
  └ 按「取消」：停預覽、丟棄 session（stills 留在輸出夾，不辨識）
  └ 按「完成並辨識」：
       停預覽 → modal「批次辨識中… done/total」（由新 on_progress 回呼驅動）
       → backend = _resolve_recognition_backend(json_path, scan_doc_preprocess_env_overrides())
       → batch = prepare_records_from_images([所有 stills], 輸出夾, template, backend, on_progress=...)
       → dump_batch(batch, json_path) → _set_loaded_records → 既有逐筆審核（左側原圖）
```

## `autocapture.py`：偵測狀態機（純函式核心）

比照本 repo「純函式決策 + cv2 薄包裝」慣例（`decide_camera_selection`、`passes_sharpness_gate`、`mark_detect`）。**狀態機只吃純量、不碰 cv2，100% 可單元測試**；影像數學另放薄 helper。

### 每幀指標 `FrameMetrics`（cv2 薄 helper 算出）
- `motion: float`——與**前一幀**的灰階平均絕對差（畫面是否靜止）。
- `change_from_ref: float`——與**上一張已拍 reference** 的灰階平均絕對差（是否換了新張 / 是否被拿走）。第一張時 ref 為 None，視為已滿足新張。
- `sharpness: float`——`measure_sharpness`（Laplacian 變異數），預覽端**粗篩**用。

> 影像數學在下採樣後的灰階小圖上做（diff/sharpness），省 CPU；存檔仍存 `capture_still` 的全解析度原圖。

### 狀態與轉移
- **ARMED**（等放穩、合焦的新張）：當
  - `motion < motion_thresh` 連續 `stable_frames` 幀（畫面靜止），**且**
  - `change_from_ref ≥ newpage_thresh`（或第一張），**且**
  - `sharpness ≥ preview_min_sharpness` **且銳利度不再上升**（對焦收斂粗篩：最近數幀 sharpness 斜率 ≤ 容差）
  → 回報 **CAPTURE**。
- **CAPTURE 後**（app 完成 `capture_still`）：
  - 成功 → app 呼叫 `detector.mark_captured(reference)` 設新 ref → **DISARMED**。
  - 失敗/取消 → `detector.note_failed_capture()` → 進冷卻、留 ARMED，連續失敗達 `retry_limit` 則回報 **STALLED**（app 停在等待、提示使用者調整對焦/光線）。
- **DISARMED**（拿開再放）：當 `change_from_ref ≥ clear_thresh` 連續 `clear_frames` 幀（紙被拿走/換掉）→ 回 **ARMED**，回報 **REARMED**。
- **冷卻**：CAPTURE 後 `cooldown_frames` 內不重新觸發，避免同張連發。

### 門檻（預設 + env 覆寫；實機校準）
| 參數 | 預設（草案，待校準） | env |
| --- | --- | --- |
| `motion_thresh` | 2.0（灰階 0–255 平均差） | `AUTOCAPTURE_MOTION_THRESH` |
| `stable_frames` | 6 | `AUTOCAPTURE_STABLE_FRAMES` |
| `newpage_thresh` | 12.0 | `AUTOCAPTURE_NEWPAGE_THRESH` |
| `clear_thresh` | 18.0 | `AUTOCAPTURE_CLEAR_THRESH` |
| `clear_frames` | 4 | `AUTOCAPTURE_CLEAR_FRAMES` |
| `preview_min_sharpness` | 60.0（**獨立於**全解析度 `DEFAULT_MIN_SHARPNESS=100`） | `AUTOCAPTURE_PREVIEW_MIN_SHARPNESS` |
| `cooldown_frames` | 8 | `AUTOCAPTURE_COOLDOWN_FRAMES` |
| `retry_limit` | 3 | `AUTOCAPTURE_RETRY_LIMIT` |

> 預覽端 sharpness 只是粗篩——**權威合焦/清晰度由 `capture_still` 的全解析度 `passes_sharpness_gate` 把關**，兩個門檻刻意分開。

## `app.py` 整合（UI / session / 回授）

- 工具列新增 **「連續拍照」** 鈕（鄰 `匯入資料夾批次`）。按下＝toggle session 開/關。
- 前置擋：`require_camera_support()`（缺 OpenCV 沿用 `CameraDependencyError` 訊息）、需已有可用相機選擇（比照 `_capture_and_recognize`）、`self.editing` 為真則擋下（「請先確認並寫入或強制寫入」）。
- Session 中**底部單行狀態列**即時顯示狀態＋計數：`連續拍照中｜已擷取 N 張｜請放上表單…` / `對焦中…` / `已拍第 N 張，請拿開換下一張` / `等待換頁…` / `太模糊，請調整對焦/光線後重試`。
- **拍下回授**：`_play_shutter()` 播 `shutter.wav`（`winsound.PlaySound(path, SND_FILENAME|SND_ASYNC)`，非 Windows/缺 winsound/缺檔→`MessageBeep` 或安全 no-op）＋預覽邊框短暫變色一下。
- Session 控制（session 啟動時才顯示/啟用）：**完成並辨識** / **取消** / **復原上一張**。
- 旋轉：存檔前 `rotate_frame(frame, self._preview_rotation)`，同 `_recognize_capture`。
- 偵測掛在既有 `_poll_camera_frame`：取得 frame 後，session active 時算 `FrameMetrics` 餵 detector、依回報動作執行；非 session 時行為不變。偵測數學在下採樣灰階上做，維持每幀低成本。

## 快門音資產與打包

- `assets/shutter.wav`：短（~0.3s）、license-clean（CC0）單聲道 wav。
- 路徑解析：以 `importlib.resources` / package 相對路徑定位；找不到時 `_play_shutter` 安全降級。
- 打包：`build/package.py` 的 PyInstaller datas 納入 `assets/shutter.wav`，確保 one-file exe 內可取得。
- 取不到 license-clean 資產時的後備：以 stdlib `wave` 合成短「click」當預設音（離線、無授權問題），並可日後替換為真實快門音。

## 錯誤處理

- 無相機 / 無 OpenCV：沿用 `CameraDependencyError` 訊息，不開 session。
- `capture_still` 回 `None`（拍時相機消失）：停 session、明確提示。
- `capture_still` `not passed`（太模糊）：不存、狀態列提示、冷卻後自動重試；連續失敗達 `retry_limit` → STALLED，停在等待要使用者處理（不靜默丟）。
- 「完成」時 0 張：提示無內容、不進辨識。
- 完成辨識失敗：比照 `_import_folder_batch` 的 `messagebox.showerror`，關 modal。
- session 期間關視窗：沿用既有 `_on_close` teardown（停相機、force-kill），stills 已落地不遺失。

## 測試策略

- **狀態機純測**（無 cv2，餵 `FrameMetrics` 序列）：
  - 放穩＋合焦收斂＋新張 → CAPTURE；對焦未收斂（sharpness 仍上升）→ 不觸發。
  - `mark_captured` 後同張微動 → 不重拍；`change_from_ref` 跨 `clear_thresh` → REARMED。
  - 連續 `not passed` 達 `retry_limit` → STALLED；冷卻期不重觸發。
  - 門檻 env 覆寫生效。
- **frame metric helper**：小 numpy 陣列驗 `motion` / `change_from_ref` / `sharpness` 串接（grayscale 直接餵，避免硬依賴 cv2）。
- **app 層**（比照 `test_scan_folder` / `test_app_navigation`，注入假 `capture_still` 與假 detector / 假相機）：
  - session 累積 N 張 stills；「完成」正確路由到 `prepare_records_from_images` 並進審核。
  - 「復原上一張」刪檔＋計數-1；「取消」不辨識。
  - `editing` 時擋下開 session。
- `prepare_records_from_images` 新增的 `on_progress`：補一個小測試驗每張回呼 `(done, total, name)`；其餘既有行為與 `capture_still` / `_resolve_recognition_backend` 已有測試，不重測。

## 落地備註（policy v1.0.0, flat profile）

- 單一 feature batch；同 PR 更新 `CHANGELOG.md [Unreleased]`（`### Added` 連續拍照模式）。
- PR template checklist 全勾、`python -m policy_check --repo .` 無 failure。
- 分支：於 `feature/bootstrap-ocr-design`（或 `wt/bootstrap-ocr-design/<subtask>`）進行，不直推 main。
- CLI help / README 視需要補「連續拍照」說明（README 既有 webcam 段落）。
