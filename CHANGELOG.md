# Changelog

本專案所有重大變更都會記錄在此檔案。

格式基於 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，
本專案遵循 hamanpaul project policy v1.0.0。

## [Unreleased]

## [0.1.0] - 2026-06-28

### Added
- README 加入**示範影片** `example/ocr-from2xlsx_example.mp4`。
- 發佈**首個 release v0.1.0**：可執行版打包（`ocr-from2xlsx.exe` + `plugins/`（PaddleOCR）+ `example/`），
  作為 GitHub Release asset 提供下載（不進 git；見先前對 1.3GB plugin 屬建置產物的處置）。

### Changed
- 新空白頁的游標改**定位在「服務日期」**（最上欄），不再往下跳到「姓名」（#focus-service-date）。開啟報表與
  每次確認並寫入帶出新頁時都從最上欄開始，符合由上而下的填寫動線。
- 工具列**移除「新增頁面」按鈕**（#remove-add-page-button）。`開啟報表` 與每次 `確認並寫入` 都會自動帶出
  新空白頁（#manual-continue），手動加頁已多餘；此動作仍保留在「編輯」選單作為備援。預覽提示與 README 一併更新。
- 工具列按鈕改名與重排（#gui-toolbar-relabel）：「開新報表」→「開啟報表」、「新增空白」→「新增頁面」，
  且「新增頁面」按鈕**移到「確認並寫入」之後**（並以分隔線與導覽群組區隔），讓「寫完一筆→再新增一頁」的
  動線更直覺。選單列（檔案「開啟報表（選 XLSX 模板）」、編輯「新增頁面」）、預覽提示、狀態訊息、開檔對話框
  標題與 README 一併同步新名稱。功能與既有快捷鍵不變。

### Fixed
- 第二筆（含）之後寫入的紀錄**底色跑掉**（#appended-row-style）。官方模板只把**第一個資料列（第 2 列）**
  完整上色（47 欄有填滿樣式），其下的列只有稀疏的 6 欄；`write_record` 只寫值、不複製列樣式，所以接在第 3 列
  之後的紀錄背景大片空白。此問題先前被「手動寫第二筆會跳 JSON 錯」（#manual-continue）掩蓋，修好後才浮現。
  改為寫入時把**第一個資料列的逐欄樣式**（填滿/框線/字型，只複製 `_style`、不動值）套到每個寫入列，讓第 2 筆
  之後與第 1 列外觀一致；批次匯入的列也一併受惠。
- 手動建單寫完一張後**無法接著寫下一張**（#manual-continue）。`開啟報表 → 填單 → 確認並寫入`後，
  `_confirm_current` 呼叫 `_next_record` 把 `current_index` 推到清單尾端之外（顯示「沒有更多資料」），畫面
  仍停在已寫入那筆；操作員直接改填下一位再按「確認並寫入」就撞到 `current_index >= len(records)` 的守門，
  跳出**誤導訊息「請先載入 JSON 資料。」**。改為：純手動模式（無 JSON/掃描來源，且當筆為 `manual-NNNN`）寫完
  最後一張時**自動開一張新空白頁**，讓「再寫下一張」直接可用；批次/掃描的清單尾端 sentinel 行為不變。
- 手動建單的**服務月份沒寫進報表**（#manual-date-month）。表單「服務年/月/日」是自由文字，操作員輸入斜線西元
  （`2026/06/16`）或民國（`115/6/28`）；`service_month_label()` 只認嚴格 ISO（`date.fromisoformat`），於是
  `_write_services` 前算月份時拋 `ValueError`、月份被寫成空白（掃描路徑因為 `parse_roc_date` 正規化過所以正常）。
  新增 `normalize_service_date()`（斜線/點/破折號分隔；年 < 1911 視為民國 +1911；無法解析則原樣保留），於
  `_apply_form_to_record` 把手動輸入的日期正規化成 ISO，月份即正確寫入、服務日期也與掃描路徑一致。
- `build/package.py` 打包時不再清掉 `dist/output/`：該資料夾是執行期輸出（`匯入中.xlsx` 等），原本每次打包會
  被一併刪除（資料遺失），且若操作員正開著輸出檔測試，刪鎖定檔會拋 `WinError 32` 並讓打包**中途失敗、連 exe
  都被刪掉**。比照 `vlm`/`plugins` 加入保留清單（#build-keep-output）。
- 校對表單**單選欄（身分/性別/國籍/年齡/管道/疾病狀態/來源/一年內新診斷）滑鼠點選沒有生效**
  （#single-choice-select-binding）。checkbox 的 `command` lambda 把 `_select` 當自由變數參照，迴圈跑完後
  late-bind 到**最後一個單選欄**的 `_select`——於是任何單選欄的滑鼠點擊都設到錯的欄位，被點的欄位值永遠是空、
  不會寫入 XLSX（連帶：身分沒設成「病人」→ 寫入時略過所有「病人才填」欄＝國籍/年齡/管道/疾病/來源/癌別/新診斷
  全空）。鍵盤數字選擇因走 default-arg 早綁定的 `_digit_select` 不受影響，所以只有滑鼠點擊壞、且既有單元測試
  （直接設變數）測不到。改用 default 參數早綁定 `_select`；新增**真的 invoke checkbox** 的回歸測試。影響手動建單
  與校正既有紀錄兩者。
- `build/package.py` 不再於打包時刪掉 `build/verify_roundtrip.py`：`_clean_dir(BUILD_DIR, keep=…)` 會清掉
  保留清單外的 build 檔，新加的查核腳本漏列其中而被一併刪除；已加入保留清單。
- 試用回饋：寫入含內嵌圖片的官方模板不再間歇性崩潰／產生損毀檔（#xlsx-image-save）。官方模板每個分頁都帶
  一張圖（服務紀錄表 logo＋各月分頁，共 14 張）；openpyxl 載入（非 read-only）後圖片資料是**延遲**從來源 zip
  讀取的，該 zip 會被 GC 關閉，於是 `workbook.save()` 在寫圖階段拋 `ValueError: I/O operation on closed file`
  並**寫到一半留下損毀的 xlsx**（連 `[Content_Types].xml` 都缺）。此為非確定性（GC 時機），實際害使用者「確認
  並寫入」失敗、看不到正確結果。修法：`WorkbookWriter` 載入後立即把每張圖的**編碼位元組快取**並覆寫
  `image._data()` 回傳該快取，save 不再讀已關閉的 archive；**且因為快取的是 bytes（不是會被首次 save 消耗/關閉
  的單一 BytesIO 串流），同一 session 連續寫多筆（多次 save）也不會損毀**。logo 完整保留。

- 試用回饋：服務項目寫入 XLSX 全面逐欄修正（#service-write-mapping）。原本 `_write_services` 只認 6 個
  服務 code 的中文標籤（`LABEL_BY_CODE`），其餘 code（如 `fatigue_strength`）會把**英文 code 原樣**寫入、
  且因沒有編號而被塞到該類**第一個空欄**——例如 4.疲憊與體力 應寫在「諮詢-症狀與副作用照護4」(AE)，卻變成
  「諮詢-症狀與副作用照護1」=`fatigue_strength`。改為由 `form_layout` 推導**完整**對應：每個選項依其在表單的
  1-based 次序（＝個案總表欄位編號）寫到正確欄位、寫入正確的「N.中文」標籤。重複偵測的反向解析
  （`_service_summary_from_row`）一併改用同一索引把標籤反解回 code，確保重開檔的摘要與 `Services.summary()`
  對所有選項都一致。新增窮舉測試（選滿所有服務選項、逐欄驗證）。
- 試用回饋：「開新報表」「匯入資料夾」不再各問兩次資料夾（#single-folder-prompt）。開新報表＝只選來源報表
  (XLSX)，工作檔預設寫到 `output/匯入中.xlsx`；匯入資料夾＝只選照片/PDF 來源資料夾，辨識輸出預設 `output/`。
  輸出位置改為**固定可預測**：packaged exe 取 exe 所在資料夾的 `output/`、dev 取 cwd 的 `output/`（原本相對
  cwd 會讓 exe 把檔寫到 `dist/output/` 而非預期位置）；開新報表後狀態列顯示**完整絕對路徑**，並在「檔案」選單加
  「開啟輸出資料夾」。輸出根可由 `output_root` 覆寫（測試隔離用）。
- 試用回饋：校對表單選項格線比照原服務表排列（#review-option-grid）。原本所有欄位的選項都用固定 4 欄換行，
  與表單對不齊（例如轉介院內/院外、管道、癌別在原表是一行 5 欄 B–F；性別在 B 欄直排）。改為依每個選項的
  `Option.cell` 還原其在表單的列/欄位置：諮詢類 4 欄、轉介/管道/疾病/癌別 5 欄、性別/國籍/年齡直排——與紙本
  表單一致。新增純函式 `option_grid_positions`。
- 試用回饋：校對時「對圖」框選對齊（#review-field-align）。聚焦欄位時來源照片會自動框到該欄位所在的表單列。
  原本那組欄位→影像區塊座標是 Phase 0 對單張照片**手調的猜測**，且**顯示端從未套用去傾斜**，所以框到的位置
  與實際欄位有偏移。改為：欄位區塊用「服務紀錄表」分頁的**真實列高幾何**推導（全寬、每欄對應其表單列）；
  聚焦時用操作員的**四角校正**把區塊以**雙線性映射**轉回**原始照片**框選——預覽維持原圖、無 warp 變形。沒有
  校正檔時退回原行為、不倍差。`field_region` 改用幾何表（與辨識用的 VLM 切片 band 解耦），新增純函式
  `map_band_to_raw`。
- 試用回饋：「確認並寫入」的阻擋條件改清楚（#confirm-required-fields）。原本按鈕在沒載入 XLSX／沒有當前
  紀錄時被**靜默禁用**（灰掉又沒任何訊息，操作員不知道為何不能按）。現在按鈕常駐可按，按下後才檢查並跳出
  明確錯誤視窗：缺工作檔跳「缺少工作檔」、姓名留空跳「姓名未填」。寫入驗證一併放寬——**只有「缺 XLSX」與
  「缺姓名」會擋下**，其餘欄位（服務日期、身分、性別、病人欄位、服務項目、重複）皆 optional，依當前填寫
  狀態寫入、缺的欄位留空；`WorkbookWriter` 容忍空值/未選 enum 不再崩，重複改記為 warning 不擋寫入。
  「強制寫入」連姓名都可留空（最終覆寫手段）。
- (#57) 校正原圖預覽改用 Pillow（LANCZOS）渲染：原本 `tk.PhotoImage` + `subsample` 是最近鄰抽點、畫面糊且
  只吃 PNG，滾輪放大也只是把抽點過的圖再放大。現在 `ImageViewer` 持有全解析度 PIL 影像、以「可見區域裁切
  ＋LANCZOS 重繪」呈現（輸出限制在面板大小、記憶體有界）：fit 視圖清晰、放大能看到更多細節、並支援 JPG。
  辨識仍吃全解析度原圖，本來就與預覽無關——此 bug 只是顯示層。
- 辨識搬到背景執行緒，UI 不再凍結：原本擷取/批次/連拍辨識都在 Tk 主執行緒同步跑，整段（首次載入模型可達數十秒）
  視窗會白屏/「沒有回應」被誤認為當機。現在辨識在 worker thread 跑、結果用 `self.after` 回主執行緒；處理中
  對話框改用會動的不確定進度條＋「取消」鈕（按下於下一張影像邊界生效，已擷取影像保留可重試）。headless 測試
  以 `_recognition_threaded=False` 走 inline 保持同步可測。
- 掃描站上手與回饋（手key 操作員對抗式 review）：
  - 「選擇攝影機」找不到時改跳明確對話框，第一條就點出「鏡頭被其他程式（如 Windows 相機）占用也會找不到，
    請先關閉」，不再只閃一行 footer。
  - 同步擷取／連續拍照擷取期間先顯示「擷取中…／拍攝中…」並強制重繪，避免凍結被誤認成當機。
  - 單張「擷取並辨識」加上與連拍一致的快門聲＋綠閃即時回饋。
  - 冷啟動狀態列改為「請先選擇模板…再選攝影機」引導；預覽占位文字改成操作步驟（去除開發用「JSON 模擬」字樣）。
  - 未開始連拍就按「結束連拍並辨識／取消連拍」時給明確提示（請先按連續拍照），不再毫無反應。
  - 工具列依工作階段重新分組：設定（模板/匯入/選攝影機）→ 掃描（擷取/連拍那組）→ 校正（上下筆/寫入），
    加群組標題與分隔線，預覽控制（旋轉/放大/縮小）移到最右，不再是 17 顆同樣的鈕擠成一排、順序又交錯。
  - 按鈕依狀態啟用/禁用：「結束連拍並辨識」看**有沒有待辨識照片**才亮（不綁在連拍進行中）；取消連拍/連拍刪除
    上一張/重設基準在連拍進行中可按；連拍中其他鈕禁用避免誤點；確認並寫入/強制寫入僅在連拍進行中禁用，其餘狀態
    常駐可按、按下才驗證（見上「確認並寫入阻擋條件」）。誤按「連續拍照」會先確認不丟失校正批次、無模板先提醒。（單張「擷取並辨識」與「匯入資料夾批次」閒置即可用，不需開連拍。）
  - 釐清三條辨識路徑的按鈕名稱：單張＝「擷取並辨識」、連拍批次＝「結束連拍並辨識」（原「完成辨識」太像通用辨識）、
    既有檔案＝「匯入資料夾批次」；「復原上一張」改為「連拍刪除上一張」標明只在連拍中作用。
  - 「旋轉」鈕顯示目前角度（如「旋轉 90°」）：旋轉設定會持久化到下次啟動，現在按鈕本身就看得出當前角度，
    不再只靠一閃即過的狀態列。
  - 常駐「連續模式中」狀態橫幅（與底部狀態列分開，不被旋轉/縮放訊息蓋掉）：等基準(n/N)／基準完成請放表單／
    已擷取 N 張請拿開；相機中斷或連續模糊暫停時顯示橘紅提示。空桌基準鎖定時加快門聲＋綠閃確認。
  - 「復原上一張」改為就地重拍同一張（重設偵測狀態），不再復原後卡住無法重拍。
  - 攝影機連線中斷時保留已選裝置（可一鍵重連、不用重選），並暫停連拍；缺 OpenCV 的錯誤訊息改為操作員看得懂
    的中文＋附技術細節。
- 相機列舉新增 Media Foundation 後備：原本只用 DirectShow 探測，導致只在 MSMF 列舉的 UVC webcam
  （Windows 相機看得到、本程式卻「找不到攝影機」）被漏掉。改為先跑快速 DirectShow pass（對缺席 index
  仍即時失敗），若完全找不到才跑較慢的 MSMF/預設後備 pass（限前幾個 index），常見情況維持快速。
- (#R6) 連續拍照基準強化：基準改為收集 N 張（預設 3）連續靜止影格取平均，避免單幀雜訊；動作偵測改用
  `mean_normalized_diff`（去 DC 後差異），對均勻亮度/曝光偏移免疫；辨識結果零筆時同步清除已拍清單，
  避免空結果循環重試。
- 修正 PR #40 程式碼審查指出的 4 處：`recognition/backend.py` `VisionOcrBackend` 預設 `model_name` 對齊
  `qwen3-vl:2b`（與 `factory.DEFAULT_MODEL` 一致，避免漏進 `ocr.model`）；`training/eval_scan._norm` 改為明確
  `None`/`""` 判斷（不再把 `0`/`False` 誤當缺值）；`plugins/paddleocr/name_crop._trim_top_right_bleed` 改為只裁頂端
  **連續**暗列（遇第一個乾淨列即停，不再過度裁切到姓名）；`scan.prepare_records_from_folder` docstring 修正
  `on_progress` 語意（傳入的是處理中檔案的 1-based index，非已完成數）。
- 校正流 UX 收斂（End-user 對抗式 review）：
  - 新增 `F8`＝跳到姓名候選清單（方向鍵瀏覽、`Enter` 套用、`Esc` 退回姓名欄）。
  - 高信心（0 待確認）的乾淨一筆載入時不再把游標搶進第一欄、也不重新框圖，可直接 `Enter` 確認。
  - `Esc` 取消：未編輯時不再整筆重畫（只回報「無可取消的編輯」）；有編輯時就地還原欄位值，
    不再連帶重置影像視角／roster／焦點。
  - 姓名 roster 候選改為「瀏覽 vs 套用」分離——方向鍵／單擊只移動高亮，`Enter`／雙擊才套用
    （不再一移到候選就覆寫姓名）；套用後即時清掉該欄 ⚠、更新「待確認 N」、並把焦點送回姓名欄。
  - 覆寫確認對話框預設聚焦「否」（連按 `Enter` 不會誤覆寫已寫入列）；確認並寫入 vs 強制寫入的
    覆寫提示文字分流；強制寫入若仍有未通過欄位，寫入後另跳提示。
  - 聚焦跨多版面切片的欄位（如 5 欄癌別 grid）時，影像框選改為涵蓋所有切片的聯集區域，不再只框第一欄。
- (#45) 選新模板後即時重置常駐進度與徽章（不再殘留上一個工作檔的「已寫入 X／列號」）；啟動與
  載入空名單時顯示「尚未載入資料」基準，角落不再空白。
- (#46) 資料完整性守門：姓名待確認且為空時，「確認並寫入」會擋下並提示先填姓名（強制寫入仍可覆蓋），
  避免把空姓名寫入並悄悄清掉待確認旗標。
- (#47) 來源圖 `set_zoom` 縮小時重新夾住 origin，修正從已平移位置縮小後右/下邊緣露出底色的問題。
- roster 無建議時顯示「（無建議名單）」而非空白清單。

### Added
- 手動建單（#manual-blank-record）：`開新報表` 選模板後**自動就給一張空白紀錄**可直接填寫、按「確認並寫入」
  存檔——**不需匯入 JSON 或掃描，也不必先按任何按鈕**（修正試用時「開新報表後仍要求載入 JSON」的問題）。另加
  「新增空白」（工具列按鈕＋編輯選單）可隨時再建下一筆；`record_id` 自動編號 `manual-NNNN`。先前紀錄只能從
  匯入JSON/掃描 來、沒有純手動輸入的路徑。後續若 匯入 JSON/掃描 會自然取代這些手動空白紀錄。
- `build/verify_roundtrip.py`：可稽核的端到端寫入自我查核。自產 golden JSON（含曾出包的刁鑽案例）→ 走真
  `ConfirmForm` 讀入/寫出 → `ImportSession` 寫真模板 XLSX → 讀回逐欄比對 JSON（欄位/label 正確、無 code 外洩、
  檔案有效、圖片保留）。亦以 `test_end_to_end_roundtrip_self_check` 納入測試套件（無 Tk 顯示時自動略過）。
  交付任何動到 表單/record/寫入 的變更前先跑它，讓查核可重現、不再仰賴人工逐筆檢查。

### Changed
- (#61) 預設辨識引擎改為 **PaddleOCR plugin**（地端、快）：實機對照地端 2B vision-VLM 約 534s/張且讀不出手寫
  姓名/病歷號，PaddleOCR 約 10–14s/張（≈50×）且能讀出 MRN/性別/身分/勾選等結構化欄位（手寫姓名兩者都需人工
  確認，校正 UI 已支援）。`app._resolve_recognition_backend` 預設改走 plugin（與 CLI 一致），VLM 改為 opt-in
  `OCR_BACKEND=vision`；plugin 未安裝且非明確指定時自動 fallback 回 VLM。`build/package.py` 保留 `dist/plugins`
  並在缺席時呼叫 `build_paddle_plugin.py` 一併打包。（Unlimited-OCR/大型 VLM 需 NVIDIA CUDA，本機為 AMD 故不適用。）
- (#60) 影像前處理改為可選模式（環境變數 `OCR_VLM_PREPROCESS`）：`autocontrast`（**預設＝原行為**）／`clahe`／
  `binarize`／`none`，每個 section crop 套用。`tiling` 新增 `resolve_preprocess_mode`/`enhance_crop`。實機對照
  （`scan-capture-7`，2B 模型，各約 9 分鐘）顯示**各模式差異小且皆未讀出手寫姓名/病歷號**（name 讀到的是印刷標籤
  「病人」、MRN 全空）；`binarize` 僅多抓到 gender＋癌別勾選。結論：前處理非瓶頸，**2B 模型才是**（見 #61）；
  預設維持 `autocontrast`，其他模式保留供後續評估。
- (#58) 移除「姓名校正」面板（放大姓名裁圖＋roster 建議名單＋F8 跳清單）：實際使用判斷多餘，左側 ImageViewer
  ＋滾輪縮放＋拖曳平移已足以核對手寫姓名。保留「姓名待確認且為空時擋下確認並寫入」的資料完整性守門；姓名仍是
  一般表單欄位。同步移除 `review_workflow.rank_roster_candidates`（僅此面板使用）。名單資料層（name_suggestion／
  correction_store／辨識端 roster 比對）不受影響。
- (#56) 上方改為下拉式選單列（檔案／掃描／編輯／檢視／說明），工具列只留五顆最常用按鈕：開新報表（選 XLSX
  模板）／匯入資料夾／上一筆／下一筆／確認並寫入；其餘動作（選攝影機、各擷取/連拍、強制寫入、放大/縮小/符合
  視窗/旋轉、快捷鍵）分門別類進選單。按鈕 enable/disable 狀態機改成可同時驅動工具列按鈕與選單項目；旋轉角度
  顯示在「檢視」選單的旋轉項標籤上。
- 校正介面美感與可發現性：
  - 狀態徽章改為彩色（已寫入綠／被擋下紅／待處理灰）而非同色純文字。
  - 聚焦中的欄位標題改為粗體，鍵盤導覽時看得出當前欄位（與 ⚠ 紅字／淡灰分屬不同視覺通道）。
  - 工具列新增「快捷鍵」說明鈕（彈出完整快捷鍵列表），主要按鈕加上 hover 提示（含 確認 vs 強制寫入 差異）。
  - (#47) 新增靜態來源圖的「放大／縮小／符合視窗」鈕（先前只有滑鼠滾輪可縮放），與相機縮放分流。
  - 細節：「待確認 N」加註「（Ctrl+Tab 跳轉）」、全部確認時顯示「本筆已確認 ✓」；底部進度/徽章/待確認
    重新分組並加分隔線；選項格改等寬欄對齊；區塊標題不再外洩內部 id（如 `top`）。
- (#53) 上方工具列採用掃描站「分組常駐」設計（設定／掃描／校正 三組常駐按鈕＋分隔線），並原生整合連續拍照；
  不採用 #44 的掃描/校正模式切換——兩套並行開發後，以實機操作員觀察版的分組常駐為主軸。

### Added
- (#59) 表單偵測＋透視校正（opt-in，環境變數 `OCR_VLM_DEWARP=1`）：辨識前先在照片中偵測表單四角並
  `warpPerspective` 攤平，使版面的 normalized section band 對齊真實欄位（原本假設照片正好框滿整張表單，
  歪斜/有邊距時會裁偏）。新增 `recognition/document_detect.py`，整合進 `tiling.crop_sections(correct_perspective=...)`，
  並在 `crop_sections` 加 EXIF 方向校正。偵測採**保守門檻**避免「開了反而更糟」：四邊形需貼齊頁面邊緣（排除
  表單內部表格）、輸出長寬比需接近 A4 直式（否則橫放/側放退回原圖而非把版面轉錯）、角度/面積/最小輸出解析度
  檢查，並在縮圖上偵測以省時。任何偵測不到、已是滿版掃描、或 cv2/Pillow 例外都**退回原圖**（安全 fallback，
  不會比關閉時更差，也不會因單張壞圖中斷整批）。預設關閉，待留出集/實機照片驗證準確率提升後再決定是否預設開啟。
- (#59) 固定相機透視校正（calibration）：實機照片是淺色表單在淺色桌面、邊界無對比，自動偵測抓不到——改為
  一次性人工標記。掃描選單新增「校正透視（去除照片傾斜）…」：載入一張代表性照片、依序點選表單四角（左上→
  右上→右下→左下），存成 `~/.ocr_from2xlsx/dewarp_calibration.json`（正規化四角）。辨識開啟 `OCR_VLM_DEWARP`
  時，**有校正檔就用固定四角攤平（不再自動偵測、不套長寬比閘，信任操作員標記）**，沒有才退回自動偵測。
  `document_detect` 新增 `load_calibration`/`save_calibration`/`calibration_path`。
- (#42, #43) 校正改鍵盤優先＋例外導向審核：載入一筆即自動聚焦第一個待確認（⚠）欄位並捲入視野，高信心
  欄位淡化、底部顯示「待確認 N」；快捷鍵 `Enter`/`Ctrl+Enter`＝確認並寫入、`F2`/`Ctrl+Shift+Enter`＝強制
  寫入、`PgDn`/`PgUp`（或 `Ctrl+→/←`）＝下/上一筆、`Esc`＝取消本筆編輯、`Ctrl+Tab`/`Ctrl+Shift+Tab`＝在
  待確認欄位間循環；單選欄可用數字鍵（1–N）選項、多選欄空白鍵切換；文字欄輸入數字仍為文字。
- (#45) 常駐進度與每筆狀態：底部顯示「已寫入 X / 共 N」＋目前列號，並依 `written_indices`／最後寫入結果
  顯示每筆狀態徽章（已寫入／待處理／被擋下），往回看也知該筆是否已寫入。
- (#46) 強化手寫姓名校正：表單上方固定「姓名校正」面板，放大顯示 `record.ocr.name_crop`（找不到裁圖時
  顯示提示），並列出 roster 建議名單（來自 correction store）為可點選候選；選中即填入姓名並清除
  `name.unconfirmed`。
- (#48) 寫入容錯：可重開「已寫入」的一筆並覆寫原列——確認並寫入/強制寫入時若該筆已寫入，跳「將覆寫第 N
  列」確認，確定後以 `accept_scan(overwrite_row=...)` 覆寫該列（先清空該列再寫，不產生重複列），取消則不
  寫入；覆寫後停留該筆不前進以便核對。
- (#47) 影像驗證升級：來源圖預覽改用 Canvas 檢視器，支援滑鼠拖曳平移＋滾輪縮放（整數倍放大，記住本
  session 縮放），取代原本只能中心裁切的放大；聚焦某欄位時依辨識版面的 section band 幾何把圖框到該欄
  位所在區域（重用 #42/#43 的聚焦面）；live 相機預覽維持 fit-to-pane。

### Changed
- 連續拍照偵測改用**空桌基準差異法（中央 ROI）**：原本以「與上一張已拍表單的差異」判定新張，對同版型一疊會漏拍第二張；改為與本 session「空桌基準」比對、淨空循環去重，並修正中文路徑寫檔（imencode+write_bytes）、連續模糊改**暫停**、合焦收斂改雙向 abs、相機中斷/辨識失敗保留已擷取影像可續辨識，辨識完成後跳通知再進逐張校正。校正進度 resume 另立 issue #37。
- (#31) 審核表單單選欄改用 checkbox：原本的 radio + 「清除」按鈕改為**互斥 checkbox**——點選一項即選取（自動取消
  其他），再點已選的即清除，因此不再需要清除按鈕。資料仍是單一值（StringVar 不變），collect/寫回語意不變。
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
- (#32) 右側審核選項區現可用滑鼠滾輪上下捲動：原本 canvas 只綁了捲軸、沒綁 `<MouseWheel>`，且表單子
  widget 蓋住 canvas，導致滑鼠在選項上滾動無效。現在 wheel handler 遞迴綁到表單每個 widget，滑鼠在哪都能捲。
- (#29) 「確認並寫入」被 validation 擋下時不再靜默：原本缺必填（vision 預填常缺 service_date/來源等）會回
  `blocked` 但只在狀態列一行帶過，使用者誤以為沒寫入。現在 blocked 會跳明確對話框列出缺/錯欄位並提示
  「補齊後再確認，或用『強制寫入』」；成功寫入則於狀態列顯示工作檔路徑與列號。
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
- 連續拍照（hands-free 自動掃描）：app 新增「連續拍照」，相機偵測到畫面穩定且合焦即自動拍照（快門聲＋計數回授）、
  「拿開再放」換頁不重複拍同一張；累積整疊後「完成辨識」走既有批次辨識＋逐筆審核，另含「復原上一張」/「取消連拍」。
  新增純狀態機 `autocapture`（可單元測試）、`prepare_records_from_images` 進度回呼、bundled 快門音。偵測門檻
  以 `AUTOCAPTURE_*` 環境變數調校。
- (#30) 圖片/PDF 批次處理模式：新增 app「匯入資料夾批次」鈕——選一個含圖片/PDF 的資料夾，**批次辨識完所有檔**
  後載入審核流**逐筆人工確認**；審核時左側面板自動改顯示該筆的**原始圖/PDF 頁**（停用 webcam）。新增
  `scan.prepare_records_from_folder`（glob 圖片/PDF、逐檔走既有 image/PDF 準備流程、合併成單一 batch、record_id
  重編唯一、進度回呼），批次期間 modal 顯示 `done/total` 進度。辨識後端沿用 vision 預設（缺則 plugin）。
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
- 可攜 release 打包（release stage）：新增 `build/build_vlm_runtime.py`，把本機 Ollama runtime ＋**僅預設模型**
  （qwen3-vl:2b）的 blobs 組成 `dist/vlm/` 可攜 bundle（本機複製、不重抓）；新增 `recognition/vlm_server.py`
  解析 runtime（env→user→bundle）並在需要時起 bundled `ollama serve`；**app 預設**在偵測到 bundle/既存 server
  時即自動起 server 並走 vision 預填（`OCR_BACKEND=plugin` 可退回舊路徑、`=vision` 可強制），讓出貨 exe 雙擊即用
  自帶模型。實測 bundle 以自帶模型在獨立 port 辨識成功（identity→patient），完全不依賴系統 Ollama。模型/runtime 不進 git。
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
