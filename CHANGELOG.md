# Changelog

本專案所有重大變更都會記錄在此檔案。

格式基於 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，
本專案遵循 hamanpaul project policy v1.0.0。

## [Unreleased]

### Changed
- app GUI 改版：webcam/來源預覽與審核表單兩大區塊最大化（2-pane），移除右側 status list，改為底部
  單行狀態列只顯示目前狀態；完整訊息寫入 log 檔（`OCR_FROM2XLSX_HOME` 或 `~/.ocr_from2xlsx/app.log`）。
- 新增「旋轉」鈕：開程式時把預覽喬正一次（每按一次轉 90°、整個 session 記住），同一旋轉也套用到
  擷取送辨識的影像；live 預覽不做逐幀方向偵測（CPU 不可行），辨識端另有 `SCAN_DOC_PREPROCESS` 校正。
- 打包加入 PyInstaller 原生開機 splash（`build/splash.png`），exe 解包期間即顯示載入視窗，app 視窗
  就緒後自動關閉，避免使用者以為程式沒啟動。

### Changed
- 預覽新增「放大」/「縮小」鈕：以中心裁切＋填滿方式放大 webcam 預覽（最高 8×），方便看清表單內容。
- 「擷取並辨識」辨識期間彈出全域鎖定的「辨識中…」modal，避免長時間辨識看起來像當掉；找不到 OCR
  plugin 時改報明確訊息（提示先 `python build/build_paddle_plugin.py`）。

### Fixed
- app 關閉視窗後不再殘留 zombie 進程：cv2/DirectShow 會留下非 daemon 擷取執行緒，使 one-file exe
  關窗後仍存活、佔住相機並鎖住 exe 檔。`_on_close` 完成 teardown 後改為強制結束程序，關窗即乾淨退出
  （子程序與 one-file bootloader 父程序皆退出，實測關窗 5 秒後殘留 0）。
- 開機 splash 不再於 `__init__` 初建佔位預覽時就提早關閉（那會在 GUI 視窗 map 前、cv2 載入那十幾秒
  留下空白）；改為視窗 map 後才關，splash 真正覆蓋啟動載入期。
- 攝影機已連接狀態訊息由「已連接攝影機 0」改為「攝影機已連接（裝置 #0）」，避免把裝置編號 0 誤讀成
  「0 台」。
- 「旋轉」設定持久化到 `~/.ocr_from2xlsx/config.json`：開程式喬正一次後，之後每次啟動沿用該旋轉。
- 相機列舉改用 DirectShow 快速探測（`_default_camera_opener`/`_enumeration_backend`）：原本預設 MSMF
  backend 對不存在的 index 會各卡數秒、且 index 存取不穩，造成「選擇攝影機→找不到攝影機」與啟動偵測
  動輒十餘秒。改後列舉 ~0.9s 並穩定找到相機；`capture_still` 仍保留跨 backend 解析度協商（取最高解析度）。

### Added
- 離線 VLM 輔助辨識（進行中，change `replace-recognition-with-local-vlm`）：新增 `recognition` 模組——
  `service_record.v1` 版面 layout（identity/gender/國籍/年齡組/管道/疾病狀態/來源/癌別 對應官方代碼）與純
  band 幾何。將以本機 Vision-LLM 預填整張表＋人工核對，取代既有不準的 OCR/幾何/heuristic 辨識路徑。設計見
  `docs/superpowers/specs/2026-06-14-offline-vlm-assisted-recognition-design.md`。
- 辨識覆蓋強化：`癌別` grid 改為 **5 直欄子切片**（整格太寬、2B 讀不到 → 分欄後正確讀出，含 ✓肝癌），並加
  「整片全勾即視為幻覺丟棄」守則，去除某欄全 marked 的 false positive。
- 辨識覆蓋：新增 **Section A 服務評估統計（全 10 服務欄：諮詢 6 類別＋用品＋院內/院外轉介＋成果）**——標籤/code
  重用 `form_layout`（DRY），mapper 支援三層 dotted（`services.consultation.<category>`），並把模型回的裸編號
  （如 `"1"`）依 label 開頭數字 remap 回完整 code。諮詢類別實測讀出 心理情緒支持/失落與悲傷關懷/照顧者支持 等；
  院內/院外轉介為又寬又薄的 10 項密集列，2B 偏弱、主要交人工核對（同癌別格病灶，子切片回報低不划算）。
- 辨識：把「已服務病人確認名單」接進 vision backend——CLI `--ocr-backend vision` 現會從 `name_corrections.jsonl`
  載入 roster，VLM 讀到的手寫姓名自動 snap 到既有病人（先前 roster 是空的、形同未比對）。
- webcam 掃描 Phase A：新增清晰度量測/門檻、原生高解析 still capture、`scan` CLI、still-image OCR bridge，
  以及 app「擷取並辨識」按鈕，可把相機拍照直接送入既有 JSON review flow。
- webcam 掃描 Phase B：新增 opt-in `document_condition.enhance()` OpenCV 文件影像增強，以及
  `SCAN_DOC_PREPROCESS` 控制的 PaddleOCR 文件方向/去扭曲 hook；預設流程仍維持關閉。`PluginOcrBackend`
  也支援 subprocess env override，供後續只對 scan 路徑做量測後 rollout。
- webcam 掃描 Phase C：提交實拍 `tests\fixtures\scan\form.png` / `lines.json` fixture 與
  `tests\test_paddle_field_extract_scan.py` regression test，並讓 `plugins\paddleocr\field_extract.py`
  額外回傳 `name_anchor` metadata，明確鎖定目前可驗證的上限：MRN 可回收、姓名裁圖錨點可定位，但
  這張 fixture 的手寫姓名仍可能 unresolved。
- 一般使用者體驗：裸跑 `ocr-from2xlsx`（或雙擊 exe）直接開啟桌面 app（#18），exe 改為 windowed
  （無 console 視窗；需要 stdout 的 CLI 使用者請以明確子命令執行，例如 `python -m ocr_from2xlsx <subcommand>` 或 `python -m ocr_from2xlsx import-json`）。
- app 啟動自動偵測攝影機：單支自動連接並即時預覽，多支彈出選擇對話框，無攝影機或未安裝 opencv 時
  優雅降級維持既有 JSON 流程；新增「選擇攝影機」按鈕（#19）。opencv 一併打包進 exe。

- 新增手寫中文姓名 rec 模型微調訓練引擎（CPU、離線）：`training.fetch_paddleocr_train`（pin 官方
  trainer repo 與預訓練權重）、`training.gen_names`（姓氏×名用字合成語料，train/validation/holdout
  三批不相交、留出集永不進訓練、OOV 字過濾）、`training.train_name_model`（官方管線微調＋匯出薄殼）、
  `training.eval_name_model`（exact-match＋字元準確率報告）、`training.retrain_name`（留出集 gate：
  exact-match 提升且字元準確率不退化才原子部署 runtime 模型目錄，稽核 `name_audit.jsonl`）。
  v1 留出集成績：exact-match 0.9832 / 字元準確率 0.9944（pip PP-OCRv5_mobile_rec baseline
  0.8255 / 0.9145）。
- PaddleOCR 外掛支援姓名專用 rec 模型：解析順序 `NAME_REC_MODEL_DIR` env →
  `OCR_FROM2XLSX_HOME`/`~/.ocr_from2xlsx/name_rec/`（`training.retrain_name` 寫此）→ bundle 內
  `name_rec/`；對既有姓名裁圖辨識並填入 `record.name` 建議（維持 `name.unconfirmed`），模型缺席或
  推論失敗時行為與現狀完全相同。`build/build_paddle_plugin.py` 會在 `name_rec/` 存在時一併打包。
  注意：v1 模型因匯出體積 ~136 MB 未 commit 進 repo（官方 mobile rec 約 16 MB，體積異常列為
  follow-up），需依 README 在本機產出。
- 新增 `training.harvest_name_corrections`：把 `name_corrections.jsonl`（人工確認姓名＋裁圖）轉成
  rec label 格式併入下次微調語料；缺圖或無效列跳過不中斷。
- 新增 `training.retrain`：手動修正重訓指令——在指定語料（合成 ∪ 修正 manifest）上重訓候選權重，
  以固定留出集對「現行權重（無則 `is_marked` baseline）」過 eval-gate（recall 上升且 precision ≥ 門檻
  才採用），採用時原子寫入使用者 runtime 權重（`OCR_FROM2XLSX_HOME` 或 `~/.ocr_from2xlsx/`），
  每次決策 append 稽核 `mark_audit.jsonl`；支援 `--validation` 以獨立乾淨驗證批校準 operating point
  （`train_mark_model.train_linear_model` 亦新增 `validation_examples` 參數）。
- `eval_gate.decide_candidate` 新增不安全現行權重規則：現行 precision 低於安全門檻（如 degenerate
  全判正 baseline）且候選 precision 達標時直接採用，不再被現行的虛高 recall 擋下。
- `training.harvest_corrections` 新增 `--answers` 批次模式：一次收割整份合成 `answers.json`
  （bootstrap 語料），`source` 預設 `synthetic`；單筆 confirmed record 模式維持不變。
- PaddleOCR 外掛 mark model 權重解析新增使用者 runtime 層：`MARK_MODEL_PATH` env →
  `OCR_FROM2XLSX_HOME`/`~/.ocr_from2xlsx/mark_model.json`（`training.retrain` 寫此）→ bundle 內
  baseline → 退回 `is_marked`。
- 隨 plugin 出貨合成 bootstrap 訓練的 v1 baseline `mark_model.json` 與 `template_boxes.json`。
- 新增 mark classifier self-training 閉環：plugin-safe `mark_features` / `mark_model` /
  `crop_provider`、template box 匯出、勾選框裁圖 JSONL 語料、confirmed correction harvest、stdlib
  線性模型訓練與 precision-safe operating point，並讓 PaddleOCR 外掛在提供 template boxes /
  mark model assets 時可走幾何裁圖 classifier（無 assets 保留既有 fallback）。
- PaddleOCR 外掛支援在明確提供 template boxes / mark model assets 時，改用幾何裁圖與輕量 classifier 判斷身分/性別勾選，並保留既有 OCR label fallback。
- 新增 `training.train_mark_model`：以 stdlib 訓練輕量勾選框線性模型、選擇安全 operating point，並匯出 `mark_model.json`。
- 新增勾選框裁圖資料集 JSONL 工具與 confirmed record correction harvest 流程，
  可從 geometry template boxes 產生標註 PNG/manifest 供 mark classifier self-training。
- 新增合成資料評測工具：`training.eval_metrics` 純度量、`python -m training.eval_marks`
  mark-blinded 勾選框評測，以及 `python -m training.eval_pipeline` OCR pipeline diagnostic
  評測，皆輸出 `report.json` / `report.md`。
- 新增單頁、`form_layout` 驅動的確認 UI：完整顯示並可編輯整筆服務紀錄，支援 adaptive source image、整頁「確認並寫入」/「強制寫入」，以及純函式 `record_access`、`confirm_form` 供 record-path 與 form-state round-trip。
- 新增共用表單版面模型 `form_layout`（區塊/欄位/選項 + 代碼 + record_path），供確認 UI 與訓練資料產生器共用；附對照「服務紀錄表」分頁的雙向涵蓋驗證測試。
- 新增 `training/` 手寫訓練資料產生器：以 `form_layout` 與空白 `服務紀錄表` 合成文字/勾選影像，輸出 `training/out/images/*.png` 與 workflow 相容答案卷 `training/out/answers.json`（`service_record.v1` + `training` + `source_image`）；取樣維持每選項涵蓋率、單多選約束，支援離線 OFL 字型下載、可選輕量 augmentation 與系統字型 fallback。
- `import-json --allow-unconfirmed-name`（開發用）：允許在未經 GUI 確認下寫入機器建議的姓名，報告仍保留 `name.unconfirmed` 標記；正式部署預設仍要求 GUI 人工確認。
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
- webcam 掃描 Phase A：camera discovery / preview 的輕量 readable probe 現在會在讀到第一張有效 frame 後立刻停止，
  不再把整個 probe budget 全數耗完；`capture_still()` 也改為先完成 backend 解析度排序，再只對最後實際候選
  做完整 autofocus warmup，保留慢啟動 fallback 與「通過清晰度優先、否則退回最高解析度失敗 capture」規則的同時，
  降低 preview 啟動與拍照掃描延遲。
- webcam 掃描 Phase A/C follow-ups：repo 內 `plugins\paddleocr\plugin.json` 改回 source-runnable
  `__PYTHON__` placeholder，而 `build\build_paddle_plugin.py` 會在 bundle 時改寫成內嵌
  `python\Scripts\python.exe`；`scan` CLI / `ReviewApp` 的 webcam 擷取在缺少 OpenCV 時也會明確提示
  `pip install .[camera]` / `pip install opencv-python`，不再誤報成無攝影機；`capture_still()`
  則會在已有通過門檻且解析度不低的最佳 backend 後，跳過不可能勝出的後續 backend 重 warmup。
- webcam 掃描 Phase A/C review follow-ups：source-mode 預設 OCR plugin 解析現在會錨定 package/repo 位置而非啟動
  cwd；camera discovery / preview 先保留輕量 probe、全失敗後再回退 still-capture startup budget，因此慢啟動
  webcam 也能最終被辨識；`plugins\paddleocr\name_crop.py` 的實際 saved crop 則會額外裁掉 real scan
  fixture 上方殘留的 MRN 墨跡。
- webcam 掃描 Phase A：source / unfrozen 的 scan/app 預設 OCR plugin 解析現在會先尋找
  `dist\plugins\paddleocr` built bundle，再退回 repo 內 `plugins\paddleocr`；明確
  `--ocr-plugin-dir` 與 `OCR_PLUGIN_DIR` override 優先序維持不變。
- webcam 掃描 Phase A：`ocr-from2xlsx scan` 在指定的 `--output` JSON 已存在時，現在會像 app 一樣自動配置同目錄唯一 sibling 檔名，避免重跑時靜默覆寫先前的 prepared JSON。
- webcam 掃描 Phase A/C blocking defects：`plugins\paddleocr\name_crop.py` 現在會依實際自上方侵入姓名列的
  MRN bbox 下緣裁掉重疊，同列且位於姓名錨點右側的合法姓名文字不再被誤裁；`capture_still()` 也會先偏好
  通過清晰度門檻的 backend capture，只有全部 backend 都失敗時才退回解析度最佳的失敗 capture。
- webcam 掃描 Phase A/C blocking defects：`capture_still()` 現在會在所有可讀 backend 間挑選實際協商解析度最佳的 still；
  `scan.prepare_records_from_images()` 在輸出目錄發生同名去重時，`source.image_path` 會記錄本地複製後檔名；
  `plugins\paddleocr\name_crop.py` 的頂部裁切不再把同列、位於姓名錨點右側的手寫姓名誤判成 MRN 侵入而回傳 `None`。
- webcam 掃描 Phase A/B/C blocking review fixes：`plugins\paddleocr\name_crop.py` 現在會對裁掉 MRN 後的
  top edge 做安全整數化（避免殘留重疊，且無正高度可裁時回傳 `None`）；`ReviewApp` 的「擷取並辨識」
  在有未保存人工編輯時會直接阻擋；`capture_still()` 也可直接處理 grayscale frame 的亮度量測。
- webcam 掃描 Phase C：`plugins\paddleocr\name_crop.py` 現在會在 `姓名/病歷號` 錨點上方的 MRN OCR bbox
  侵入姓名列時，往下裁掉重疊區；`tests\test_paddle_field_extract_scan.py` 也改為驗證「姓名裁圖不得與
  MRN bbox 重疊」的性質，而不再凍結錯誤的重疊座標。
- webcam 掃描 Phase B：`plugins\paddleocr` 的 `SCAN_DOC_PREPROCESS` opt-in 現在只會在 runtime
  可找到 `PP-LCNet_x1_0_doc_ori` 與 `UVDoc` model dirs 時才啟用文件方向/去扭曲；離線/bundled plugin
  缺模型時會安全維持關閉，不再要求額外下載才可執行預設流程。
- webcam 掃描 Phase A：camera enumeration、`ReviewApp._start_camera()` 預覽啟動與 `capture_still()` 現在共用同一套相機開啟策略：backend 不只要 `isOpened()`，還必須真的能讀到 frame；因此遇到「開得起來但完全不出畫面」的 default backend 時，discovery/preview 會像 `capture_still()` 一樣回退到後續可讀取的 backend（例如 `cv2.CAP_DSHOW`），而正常可讀的 default backend 仍維持既有優先順序。
- webcam 掃描 Phase A：`capture.negotiate_max_resolution()` 改為使用純 property id，不再在 default 非 camera 測試環境硬性 import OpenCV；未安裝 `opencv-python` 也可執行解析度 negotiation regression test。
- webcam 掃描 Phase A：`scan` CLI 在 webcam still 寫檔失敗（`cv2.imwrite(...) == False`）時，現在會走既有 `error: ...` 路徑並回傳 exit code 2，不再拋出 traceback。
- webcam 掃描 Phase A：`ReviewApp` 的「擷取並辨識」成功載入 still image 後不再自動重啟 live preview 覆蓋預覽；capture 失敗（無攝影機 / 模糊 / OCR 例外）時也只會在 capture 前 live preview 原本就啟用時才恢復，不再覆蓋既有 record/placeholder preview。`scan --image` 對非 PNG 輸入也會在輸出旁建立 `.png` preview bridge，並把 `source.preprocessed_image_path` 指向該 preview，讓 review app 可持續顯示來源影像。
- webcam 掃描 Phase A：camera-backed `scan` CLI / `ReviewApp`「擷取並辨識」現在會先配置唯一的 `scan-capture*.png` / `scan-prepared*.json` 路徑，避免重複掃描同一輸出資料夾時覆寫舊批次 artefacts；`capture_still()` 回傳無可用攝影機時，也不會在同一次擷取流程內立刻重啟剛失敗的 live preview。
- `ReviewApp` 攝影機預覽現在會對連續 `read()` / `imencode()` 失敗採用有限重試，超限後推送狀態、停止攝影機並恢復 placeholder；啟動路徑的 `VideoCapture` 建立 / `isOpened()` 檢查 / failure cleanup 也統一留在 graceful fallback 內，避免 backend 例外直接中斷 UI。
- webcam 掃描 Phase A：`ReviewApp` 現在只會在已有明確可用的攝影機選擇時執行「擷取並辨識」；取消選擇、啟動失敗、找不到相機或預覽故障都會清掉失效 camera state，不再靜默退回 camera 0 或沿用 stale index。
- webcam 掃描 Phase A：camera discovery / preview 使用的 readable-backend probe budget 現在與 still capture warmup 對齊，慢啟動但可用的 webcam 不再在 enumerate/preview 階段被過早判定為不可用。
- webcam 掃描 Phase A：camera discovery / preview 現在改用獨立的輕量 readable probe budget，不再在 app 啟動或「選擇攝影機」同步耗掉 still capture 的 80-frame warmup；`capture_still()` 仍保留較重的 warmup / backend selection 路徑。
- webcam 掃描 Phase A/B review follow-ups：`capture_still()` 的 backend 解析度 probe 現在會在每次探測後立即釋放 handle，再只重開排序後的候選 backend 做最終 warmup/capture，避免獨占式 camera driver 卡住較高解析度 backend；`SCAN_DOC_PREPROCESS` 也改為預設不再被一般 `PluginOcrBackend` subprocess 繼承，只有 `scan` CLI / app「擷取並辨識」在明確 opt-in 時才會顯式傳遞。
- webcam 掃描 Phase A blocking follow-up：`capture_still()` 在選定 backend 後重新開啟最終 handle 時，現在會重新協商/確認解析度再進入 warmup；`CaptureResult.resolution` 也改為回報 final handle 的實際 capture resolution，不再沿用 probe-only handle 的舊值。
- `training.gen_names.render_corpus()` 現在會先做 CJK-aware 字型選擇；手寫字型支援中文時仍優先使用，不支援時會安全退回系統 CJK 字型，避免 Latin handwriting fonts 直接渲染中文姓名。
- `training.fetch_paddleocr_train` now pins the PP-OCRv5 mobile rec pretrained weights URL to
  PaddleX's official pretrained model host, matching the current PaddleOCR docs.
- `training.generate --augment` 修正 `Image.Resampling` 誤用 instance 屬性導致的 `AttributeError`，
  augmentation 路徑現在可用。
- `form_layout.Field.selected_codes` 現在把空字串視為未選（同 `None`），收割含未勾 single_choice
  的記錄不再誤報 unknown selected code。
- PaddleOCR 外掛 geometry classifier 路徑在影像缺失/不可讀（`OSError`）時退回既有
  `detect_marked_labels`，不再讓 plugin 失敗。
- PaddleOCR 外掛在「有 template boxes 但無 mark model 權重」時不再走逐框 `is_marked` 幾何路徑
  （實測該 fallback 會把印刷「□」全判為有勾），改為整體退回 `detect_marked_labels`。
- `training.handwriting.draw_text()` 現在會以 `textbbox()` 的完整偏移/邊界做縮放與定位，確保實際墨跡留在目標框內；新增對應 regression test 覆蓋 Windows 字型的垂直溢出案例。
- `prepare_records` 現在會把 OCR/backend 直接帶入的 `name` 一律標成 `name.unconfirmed`；`correction_store.load_corrections` 也會跳過損壞或不可用的 JSONL entries，避免 `prepare-records` 因單筆壞資料整體失敗。
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
