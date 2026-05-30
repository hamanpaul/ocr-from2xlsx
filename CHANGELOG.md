# Changelog

本專案所有重大變更都會記錄在此檔案。

格式基於 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，
本專案遵循 hamanpaul project policy v1.0.0。

## [Unreleased]

### Added
- `prepare-records` 新增可選 `--name-agent-config`：以 TOML 啟用手寫姓名 agent；缺席、停用或不支援 provider 時維持 no-op。
- 離線 OCR 外掛新增輸出個資最小化的姓名裁圖，路徑記於 `record.ocr.name_crop`。
- 新增 `name_suggestion` / `confirm_name`：候選姓名會先標 `name.unconfirmed`，人工確認則寫回本地 correction store 並重建 roster。
- 新增 `correction_store`（append-only JSONL）與 `name_roster`（difflib fuzzy match），供後續姓名匹配重用。
- 手寫姓名 agent 只接收姓名裁圖；API key 由 config 指定的環境變數讀取（預設 `ANTHROPIC_API_KEY`）。
- 新增 `plugins/paddleocr/mark_detect.py` 純函式打勾評分核心（灰階區域墨跡比例）。
- PaddleOCR 外掛新增身分/性別打勾辨識（文字錨點 + 框內墨跡 + OCR 異常文字訊號）與手寫姓名/病歷號擷取。
- `import-json --allow-incomplete`：辨識到的記錄即使缺病人限定欄位也可寫入（forced）以供核對。
- 新增參考 PDF ground-truth fixture、可選的實機 PaddleOCR 驗證測試，與 `build/build_paddle_plugin.py` 的 bundle 內容回歸測試。

### Fixed
- `prepare-records --name-agent-config` 現在會拒絕解析後跳出輸出目錄的 backend `record.ocr.name_crop` 路徑，並改回同層 `*-name.png` fallback；`name_agent.load_config()` 也改為嚴格驗證 TOML 型別，錯誤型別會直接報 `ValueError`，不再以 `bool(...)` / `str(...)` 靜默轉型。
- `name_suggestion` 現在只會把單行、姓名樣式的 OCR 字串當成 fallback 候選，並在 `confirm_name` 持久化前再次最小化 `ocr_raw`；多行整頁 OCR 內容與敏感欄位（如病歷號）不再寫進 `record.name` 或 correction store。`name_agent.load_config()` 缺省 prompt 也改用實際字串常數，避免 dataclass slots descriptor 混入設定。
- `name_suggestion.suggest_name` 在沒有任何可提案姓名時不再強制加上 `name.unconfirmed`；有 roster match 或 agent/OCR 候選時仍維持未確認警告。
- `correction_store.load_corrections` 現在會忽略 JSONL 中未認得的欄位，避免前向相容資料把 review flow 擋死。
- `ImportSession.accept_scan(..., human_confirmed=True)` 現在統一在成功寫入時清除 `name.unconfirmed`；Tk 純姓名確認不再把該筆標成使用者編輯。
- `ReviewApp` 現在只會在 `accept_scan()` 寫入成功（`written` / `forced`）後才把人工確認姓名寫進本地 correction store；被阻擋或寫入失敗時不再污染 learning loop。`prepare-records --name-agent-config` 對不支援或實際無法運作的 agent 設定也恢復 strict no-op，不再單靠 OCR fallback 填入姓名或追加 `name.unconfirmed`。
- 補齊手寫姓名 learning loop：`prepare-records` 會自動載入輸出 JSON 同層 `name_corrections.jsonl` 建 roster；`ImportSession` 預設阻擋 `name.unconfirmed`；Tk 審核流程確認姓名後會寫入同層 correction store 並清除警告再寫入。
- `prepare-records --name-agent-config` 現在會先使用 `record.ocr.name_crop`，缺席時才從 `source.preprocessed_image_path` 推導同層的 `*-name.png` 裁圖；只有裁圖存在時才進入建議流程，否則維持 strict no-op。
- `plugins/paddleocr/mark_detect.py`：改為只接受獨立或單字元裝飾的選項標籤，避免把標題與「數量」類欄位誤判成可勾選標籤。
- `plugins/paddleocr/mark_detect.py`：新增 OCR 文字異常的勾選推論（如 `中女性`、`V女性`、`病人6250712919`），讓實際被勾選的身份/性別可在未探到像素勾記時仍被辨識；純 `□標籤` 仍只作為 probe label，不視為文字已勾選。
- `plugins/paddleocr/field_extract.py`：忽略單一中文字元的姓名雜訊，並保留姓名欄錨點上方鄰近行的病歷號回收。
- 實機 PaddleOCR ground-truth 驗證目前仍會漏掉參考表單的手寫 `name`（`葉心安`）；README 已同步標示這是目前 mobile recognizer 的已知限制，建議搭配 `import-json --allow-incomplete` 進行人工核對。
- `build/build_paddle_plugin.py`：可攜 bundle 現在會一併打包 `mark_detect.py`。
- `build/build_paddle_plugin.py`：可攜 bundle 現在也會打包 `name_crop.py`，避免離線 PaddleOCR 外掛執行期缺模組。
- `prepare_records`：當 OCR backend（如 PaddleOCR 外掛）未提供 `record_id` 時，依頁序自動指派穩定 id（`pdf-0001`…），讓真實 OCR 結果能流入 `import-json`；既有 backend 提供的 `record_id` 仍保留。
- `build/package.py`：清理 `build/` 時保留 `build_paddle_plugin.py`，避免主程式打包誤刪可攜外掛建置腳本。
- normalized JSON/domain round-trip 現在會保留 backend 提供的 `record.ocr.name_crop`，且缺席時不會把 `"name_crop": null` 寫進每筆記錄。

### Changed
- `plugins/paddleocr/field_extract.py`：重構 `extract_name_and_mrn`，改用候選文字列表式擷取（`_name_from_candidates` / `_mrn_from_candidates`），支援手寫姓名與純數字病歷號（`_DIGIT_RUN \d{6,}`）分置兩格的版面；`_mrn_from_candidates` 同時嘗試 `_MRN_TOKEN`（含連字號）與 `_DIGIT_RUN`，保留既有含字母/連字號病歷號相容性。`extract_fields` 新增 `marked_labels=None` 參數（供後續任務使用），並補上 `identity`/`gender` 空字串欄位。
- `tests/test_paddle_field_extract.py`：新增 2 項測試——手寫姓名/病歷號分置兩格（anchor-row-handwriting）與 OCR 將標籤與數字合併（merges-label-and-digits），共 16 項全通過。
- `src/ocr_from2xlsx/preprocess.py`：PDF 頁面預處理由 200 DPI 提升到 400 DPI，改善真實 PaddleOCR 對身分/性別與病歷號的擷取表現。
- `plugins/paddleocr/field_extract.py`：強化姓名/病歷號擷取準確度——過濾打勾框與表單標籤雜訊（病人/親友/民眾/病歷號…），並要求候選值需含病歷號或中文姓名才接受，避免把鄰列的勾選框或雜訊（如 OCR 誤判的 "V"）當成姓名。
- `plugins/paddleocr/field_extract.py`：強化 MRN regex，要求至少含一個數字，避免純字母 token（如羅馬拼音姓名）被誤判為病歷號；新增 `normalize_roc_date` 與 `extract_service_date` 的 docstring，說明 v1 簡化假設。
- `tests/test_paddle_field_extract.py`：新增純姓名（無病歷號）與含連字號病歷號兩個覆蓋率測試，共 11 項全通過。

### Added
- 新增 PaddleOCR 可攜離線外掛（`plugins/paddleocr/`）：全頁 OCR + 文字錨點擷取服務日期/姓名/病歷號，內嵌 venv + PP-OCRv5 mobile 模型，透過 `ocr_plugin.v1` 契約供主程式呼叫。
- 新增 `build/build_paddle_plugin.py` 組裝可攜外掛 bundle。
- `PluginOcrBackend` 支援以相對路徑指向外掛內自帶直譯器，並容忍外掛非 UTF-8 的 stderr。
- 新增 OCR 外掛契約（`ocr_plugin.v1`）與 `PluginOcrBackend`，可透過 subprocess 呼叫可攜式外部 OCR；外掛不存在時安全回報。
- `prepare-records` 新增 `--ocr-backend {fixture,plugin}` 與 `--ocr-plugin-dir`（`--ocr-fixture` 改為非必填）。
- 新增 `prepare-records` 前處理流程，將固定版型 PDF 轉成 normalized JSON 後再交給既有匯入流程。
- 新增 `for testing only.pdf` 的人工標註 gold fixture 與端到端 regression 測試。
- 新增 `prepare-records` CLI，將 PDF 輸入前處理為 normalized JSON。
- 以 `hamanpaul/new-project-template` 建立專案骨架。
- 導入 `hamanpaul/paulsha-conventions` policy metadata、agent convention files 與 Policy Check workflow。
- 新增 OCR-to-XLSX 服務紀錄匯入工具設計規格。
- 新增 Python package scaffold 與 CLI entrypoint。
- 新增 Python sdist 版本檔案打包設定。
- 新增約 100 筆測試 JSON 產生器與 CLI subcommand。
- 新增 JSON 驗證與重複單判斷。
- 新增保留模板格式的 `個案總表` XLSX 寫入器。
- 新增每筆確認即寫入保存的匯入工作階段與報告模型。
- 新增 JSON 到 XLSX 的 CLI 匯入流程。
- 新增 JSON、圖片資料夾與 UVC 攝影機 capture adapter 邊界。
- 新增 PDF 文件 capture adapter，可讀取測試掃描檔頁數與頁面尺寸 metadata。
- 新增不開 localhost port 的 Tkinter 原生桌面審核介面。
- 新增 PyInstaller 打包流程生成 portable Windows .exe。
- 新增 PR template，對齊 policy checklist。

### Fixed
- `prepare-records` 的錯誤處理擴充為 `OSError`、`json.JSONDecodeError`、`ValueError`、`KeyError`、`IndexError`、`TypeError`。
- 補齊服務摘要對應未列舉標籤時的 raw code 轉換，避免重複單漏判。
- 讀取工作簿時要求完整病人/基本欄位與癌別欄位，缺漏即明確報錯。
- 病人欄位的「一年內新診斷」為空值時不再寫入「否」。
- 避免被阻擋的匯入記錄預先佔用重複鍵，並確認寫入結果。
- import-json 匯入途中失敗時，若已有記錄寫入，錯誤訊息會提示 working XLSX 可能已有部分資料。
- import-json 有阻擋記錄時回傳對應 exit code，並更新 CLI help 描述。
- 清理誤提交的 PyInstaller build 產物，避免 build cache 進入版本庫。
- Policy Check workflow 改為直接傳入 PR metadata，避免 GitHub event payload 差異造成誤判。
- 失敗的 PDF 頁面模板檢查不再先建立輸出目錄，避免留下空資料夾。
- Fixture OCR backend 會深拷貝頁面記錄，避免巢狀 `source` / `review` 狀態在多次抽取間互相污染。
