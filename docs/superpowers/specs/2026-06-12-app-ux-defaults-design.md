# App UX 預設行為設計（exe 直接開 app + webcam 自動偵測）

**Date:** 2026-06-12
**Status:** Draft (decisions locked with user; pending spec review)

---

## 背景

兩個面向一般使用者的 UX 缺陷（GitHub issues #18、#19）：

1. **#18**：`ocr-from2xlsx.exe` 裸跑只印 help，不會開視窗。一般使用者不會用 CLI 帶子命令，預期雙擊就開 app。
2. **#19**：app 啟動後沒有真的連接攝影機——左邊看似「webcam 區」其實是 `tk.Text` 佔位字（`攝影機或圖片預覽區\n第一版可用 JSON 模擬連續掃描。`）。`opencv` 為選配 `[camera]` extra，也沒打包進 exe，故出貨 exe 無法掃描。

## 決策前提（已與使用者確認）

- **#18**：exe 改 **windowed（`console=False`）**——雙擊乾淨、不閃黑窗。接受代價：從終端機跑 CLI 時 stdout 不顯示（power user 改用 `python -m ocr_from2xlsx`）。`cli.main()` 行為與測試不受影響。
- **#19**：**完整落地**——把 `opencv` 打包進 exe，讓出貨 exe 真的能接攝影機；多支時讓使用者選。

## 目標

- 裸跑 `ocr-from2xlsx`（無參數）→ 直接啟動 app；`--version`、`--help`、各子命令行為不變。
- exe 雙擊為 windowed 體驗（無 console 視窗）。
- app 啟動自動偵測攝影機：0 支 → 維持現狀（佔位／JSON 模式）；1 支 → 自動連接並即時預覽；2 支以上 → 彈出選擇對話框。
- 提供「選擇攝影機」按鈕讓使用者重新挑選／切換。
- opencv 缺席（dev 無 `[camera]`）時優雅降級：維持現狀，JSON 流程照常。
- opencv 打包進 PyInstaller exe，frozen 環境可載入 cv2。

## 非目標（YAGNI）

- 不做「擷取攝影機畫面 → 直接餵 OCR pipeline」：現行 OCR 走 PDF（`prepare-records`），擷取掃描成 PDF/影像再進流程是後續題目。本次只做「連接 + 即時預覽 + 選擇」。
- 不引入 Pillow：cv2 frame 以 `cv2.imencode('.ppm', frame)` 轉 bytes 餵 `tk.PhotoImage(data=...)`。
- 不做攝影機解析度/對焦/曝光設定 UI。
- 不為 CLI 提供 windowed exe 的 stdout 還原（`AttachConsole` 之類）；power user 用 module 模式。

## 設計

### #18：預設子命令 + windowed exe

- `cli.build_parser()`：在 subparsers 定義後加 `parser.set_defaults(command="app")`。裸跑 → `args.command == "app"` → `run_app()`。
  - `--version` 在 `main()` 最前面檢查，先返回，不受影響。
  - `--help` 由 argparse 原生處理，help 文字不變（README cli-help marker、R-16 不受影響）。
  - 明確子命令（`sample-json` 等）仍由 subparser 覆寫 `command`，行為不變。
- `build/ocr-from2xlsx.spec`：`console=True` → `console=False`。

### #19：攝影機偵測／選擇／預覽

**純函式（TDD 核心，`src/ocr_from2xlsx/capture.py`）**

- `enumerate_cameras(max_probe=5, opener=None) -> list[int]`：探 index `0..max_probe-1`，回傳可開啟的 index 清單；`opener(index)->bool` 可注入（測試用假 opener，不需 cv2）。預設 opener 以 `cv2.VideoCapture(index).isOpened()` 判斷，cv2 缺席回 `False`。
- `decide_camera_selection(indices) -> tuple`：純決策——`[]→("none",)`；`[i]→("auto", i)`；`2+→("choose", tuple(indices))`。

**app 整合（`src/ocr_from2xlsx/app.py`，cv2-guarded glue，沿用 app.py「薄膠合」慣例）**

- 啟動時 `_init_camera()`：`enumerate_cameras()` → `decide_camera_selection()` →
  - `none` → 維持 `_show_placeholder_preview()`；
  - `auto` → `_start_camera(index)`；
  - `choose` → `_ask_camera(indices)`（modal Toplevel + Listbox/Radiobutton）取得選擇 → `_start_camera(index)`。
- `_start_camera(index)`：`cv2.VideoCapture(index)`，以 `after(33, ...)` loop 讀 frame → `imencode('.ppm')` → `PhotoImage(data=...)` → 渲染進左側預覽（沿用既有 `self.preview` 容器或改 `tk.Label`）。任何例外 → 停止、退回佔位、`_push_status` 記錄。
- 關閉時釋放 `VideoCapture`、取消排程（`_on_close` 一併處理）。
- toolbar 新增「選擇攝影機」按鈕 → 重新 `enumerate` 並彈選擇。
- 全程 cv2-guarded：`import cv2` 失敗 → 功能靜默停用、JSON 流程照常。

**打包（`build/ocr-from2xlsx.spec` + `build/package.py` 文件）**

- spec `hiddenimports` 加 `"cv2"`（必要時 `collect_dynamic_libs('cv2')` 補 binaries）。
- 打包前需安裝 opencv：`pip install -e ".[dev,camera]"` 後再 `python build/package.py`；README/打包段落同步說明。
- 加一個便宜的 spec 內容回歸測試（assert `console=False`、`cv2` 在 hiddenimports），避免日後改 spec 漏掉。

## 測試策略

- **純單元（CI、`.venv`）**
  - `cli.main([])` → 觸發 app：monkeypatch `ocr_from2xlsx.app.run_app` 為假函式，斷言被呼叫且回傳 0；`main(["--version"])`、`main(["sample-json", ...])` 行為不變（回歸）。
  - `enumerate_cameras`：注入假 opener（指定哪些 index 可開）驗證回傳；cv2 缺席預設 opener 回 `[]`。
  - `decide_camera_selection`：none/auto/choose 三分支。
  - spec 回歸：讀 `build/ocr-from2xlsx.spec` 斷言 `console=False` 與 `cv2` hiddenimport。
- **手動驗證（Tk + cv2，不進 CI）**：真機雙擊 exe 開 app、單／多攝影機分支、即時預覽、選擇切換、無攝影機降級。
- 既有測試與 `python -m policy_check` 全綠；`-W error` 不得新增警告。

## 成功準則

- [ ] 裸跑 `ocr-from2xlsx` 開 app；`--version`/`--help`/子命令不變（有測試）。
- [ ] exe `console=False`（spec 測試 + 手動雙擊驗證）。
- [ ] `enumerate_cameras` / `decide_camera_selection` 純函式有測試涵蓋三分支與 cv2 缺席。
- [ ] app 啟動 0/1/2+ 攝影機行為正確（手動驗證），opencv 缺席優雅降級。
- [ ] opencv 打包進 exe，frozen 環境 cv2 可載入（手動驗證）。
- [ ] README（exe 用法、打包需 `[camera]`）、CHANGELOG、policy 全部同步。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| windowed exe 讓 CLI stdout 消失，power user 困惑 | 中 | 低 | README 註明 CLI 改用 `python -m ocr_from2xlsx`；測試走 `cli.main()` 不受影響 |
| PyInstaller 打包 cv2 在 frozen 環境載入失敗 | 中 | 高 | spec 用官方 hook/`collect_dynamic_libs`；打包後手動驗證 cv2 import；失敗則回退 collect_all('cv2') |
| 多攝影機 index 探測誤判（phantom index） | 中 | 低 | `max_probe` 上限；選擇對話框讓使用者人工挑；探測失敗不阻斷 app |
| 即時預覽 PhotoImage 記憶體洩漏／卡頓 | 中 | 中 | 保留單一 `_preview_image` 參照覆寫；`after()` 節流（~30fps）；關閉時釋放 |
| exe 體積大增（opencv 數十 MB） | 高 | 低 | 使用者已同意；必要時後續改精簡 opencv-python-headless |
