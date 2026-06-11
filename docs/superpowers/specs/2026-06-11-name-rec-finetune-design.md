# 手寫中文姓名辨識模型微調訓練引擎設計

**Date:** 2026-06-11
**Status:** Draft (brainstorming approved; pending spec review)

---

## 背景

現行手寫中文姓名路徑：PaddleOCR mobile 全頁辨識（手寫弱，README 已記錄參考表單的「葉心安」抓不到）→ 選配雲端姓名 agent → roster fuzzy match（吃 `name_corrections.jsonl` 的人工確認）→ GUI 人工確認。其中「學習」只有 roster 累積比對，底層 OCR 能力不會變強。

mark classifier 子專案（PR #16）已建立完整的「合成 bootstrap → 訓練 → eval-gate → runtime 權重部署 → 真實修正回補」閉環語彙。本子專案把同一套閉環擴展到手寫姓名：**以 PaddleOCR 官方訓練管線微調 PP-OCRv5_mobile_rec，產出姓名專用 rec 模型**，建立可重複的訓練引擎並落地 v1。

決策前提（已與使用者確認）：

- **開放集**：辨識任意姓名，不限病人名單；沿用官方中文字典保持開放集輸出能力。
- **CPU-only**：本機無 GPU、paddle 為 CPU build；訓練慢可接受（數小時～過夜），重點是引擎可重複。
- 目標是「訓練引擎建起來＋v1 可辨識名字」，不是一步到位的高精度。

## 目標

- 建立可重複的姓名 rec 微調引擎：語料生成 → 微調 → 評測 → gate → 部署，全部指令化。
- v1 姓名模型：合成手寫姓名語料微調，於留出集上 exact-match 明顯優於現行 mobile 全頁模型對姓名裁圖的表現（現況趨近 0）。
- plugin 以**第二顆姓名專用 rec 模型**對 `name_crop` 辨識；模型缺席時行為與現狀完全相同。
- 真實人工修正（`name_corrections.jsonl` 已存裁圖路徑＋確認值）可收割進語料供重訓。
- 安全不變：模型輸出僅為建議，一律 `name.unconfirmed`，GUI 人工確認為最終防線。

## 非目標（YAGNI）

- 不動 det（偵測）模型——姓名裁圖由既有 `name_crop` 提供。
- 不替換全頁 rec 模型；不改 `ocr_plugin.v1` 契約。
- 不改姓名 agent 與 roster 機制（它們維持下游建議者角色）。
- 不做 GPU 支援、分散式訓練、自動排程重訓。
- 不在本 spec 實作 confirm 流程的自動觸發（與 mark 閉環同樣留待後續）。

## 風險驅動的第一步：引擎 smoke（Phase 1 gate）

最大風險是「官方訓練管線在 Windows + CPU 上跑不順」。因此實作的第一個任務固定為**煙霧驗證**：

> 取 PaddleOCR 官方 repo（pin 在已驗證 tag，clone 到 gitignored `training/vendor/PaddleOCR/`）＋ PP-OCRv5_mobile_rec 預訓練權重，用 ~50 張合成姓名裁圖跑 1 epoch 微調 → 匯出 inference 模型 → 用 pip 版 `paddleocr` 指定 `text_recognition_model_dir` 載入並辨識一張裁圖。

煙霧通過才繼續蓋語料產生器與閉環；不通過則回頭評估 PaddleX fine-tune API 或調整路線（設計的其餘部分不受影響，因為訓練引擎被包在薄殼後面）。

## 位置與環境

訓練全部離線、在 `.venv-paddle`（paddlepaddle 3.0 CPU + paddleocr）執行；官方訓練 repo 與預訓練權重由 fetch script 取得，皆 gitignored。

```
training/
  fetch_paddleocr_train.py   NEW. clone/更新官方 repo 至 pinned tag、下載預訓練權重（離線後可重複用）。
  gen_names.py               NEW. 姓名語料產生器：常見姓氏 × 名用字池 → 2-4 字姓名，
                                  手寫字型渲染 + 既有 augmentation，輸出裁圖 + label txt（PaddleOCR rec 格式）。
  train_name_model.py        NEW. 微調薄殼：組 yml config（CPU、epochs、語料路徑）→ 呼叫官方 train →
                                  匯出 inference 模型目錄；參數與輸出皆指令化、可重複。
  eval_name_model.py         NEW. 留出集評測：exact-match 率 + 字元準確率（edit distance）；輸出 report.json/md。
  retrain_name.py            NEW. gate + 部署：候選 vs 現行模型在固定留出集評測 →
                                  exact-match 提升且字元準確率不退化才原子部署 runtime 模型目錄；稽核 JSONL。
  harvest_name_corrections.py NEW. 把 name_corrections.jsonl（crop_path + final_value）轉成 rec label 格式併入語料。
  vendor/PaddleOCR/          (gitignored) 官方訓練 repo。
  out/namev1/                (gitignored) 語料、留出集、候選模型、deploy staging。

plugins/paddleocr/
  name_rec/                  NEW(離線產). bundle 內附 v1 姓名 rec inference 模型目錄（det 不附）。
  main.py                    MODIFY. name_crop 存檔後，若姓名模型可解析則以其辨識並填 record.name；
                                  解析順序 NAME_REC_MODEL_DIR env → ~/.ocr_from2xlsx/name_rec/ → bundle name_rec/ → 無（現狀）。
build/build_paddle_plugin.py MODIFY. bundle 一併打包 name_rec/（存在時）。
```

## 語料設計

- **姓名池**：內嵌常見台灣姓氏表（~100）＋ 名用字池（~1500 常用名字用字，內嵌靜態清單），隨機組 2-4 字姓名；固定 seed。v1 規模約 3000 姓名 × 2-3 字型變化 ≈ 6000-9000 張裁圖。
- **渲染**：重用 `training/fonts` 手寫字型（`fetch_fonts.py`）＋系統楷體 fallback、重用旋轉/模糊/噪點 augmentation；裁圖尺寸對齊 `name_crop` 實際輸出分布。
- **切分**：訓練批（seed 固定）／乾淨驗證批（早停與調參用）／**固定留出集（gate 專用，永不進訓練）**——沿用 mark 子專案三批慣例。
- **真實修正**：`harvest_name_corrections` 把人工確認資料轉進語料；冷啟動時為 0，不影響 v1。
- 標籤格式用 PaddleOCR rec 標準 `path\tlabel` txt；字典沿用官方中文 dict（開放集）。

## 訓練與部署

- 微調自 PP-OCRv5_mobile_rec 預訓練權重；CPU 參數保守（小 batch、少 epochs、必要時凍結 backbone 只調頭部——以 smoke 結果定）。
- `retrain_name` gate 規則：候選與現行（無現行則與「pip 內建 mobile rec 直接辨識裁圖」的 baseline）比——**exact-match 提升且字元準確率不退化才部署**；每次決策 append 稽核 JSONL（與 `mark_audit.jsonl` 同格式精神）。
- 部署採原子目錄替換（暫存目錄 + rename）；runtime 位置 `~/.ocr_from2xlsx/name_rec/`（沿用 `OCR_FROM2XLSX_HOME`）。
- v1 通過 gate 後，同一份模型目錄 commit 進 `plugins/paddleocr/name_rec/` 作 bundle baseline（模型 ~10MB 級，可接受；過大再改 release asset，YAGNI）。

## plugin 整合與安全

- `main.py`：`_resolve_name_rec_dir()` 解析順序同權重慣例；可解析時對 name_crop 跑姓名 rec，結果填 `record.name` 並維持 `name.unconfirmed` 警告；任何失敗（模型壞、OSError）→ 退回現狀路徑。
- agent / roster / GUI confirm 全部不動：姓名模型只是把「OCR 候選」這一層變強，下游建議與確認機制照舊。
- 推論端依賴不變：pip 版 paddleocr 本就支援指定 rec 模型目錄，bundle 不需新增套件。

## 測試策略

- **純單元（CI，`.venv`）**：gen_names 取樣涵蓋與 seed 重現性（不渲染）；label txt 讀寫與路徑安全；gate 決策規則（提升/退化/混合案例，含拒用保留現行）；`_resolve_name_rec_dir` 解析順序。
- **marker / 訓練環境（`.venv-paddle`）**：渲染 smoke（小批）；引擎 smoke（1 epoch 微調 + 匯出 + 重載辨識）；eval 端到端小批。
- plugin 整合：模型目錄缺席 → 行為與現有測試完全一致（回歸保護）；提供假模型目錄時填 name 並保留 unconfirmed。
- 既有測試與 policy 全綠。

## 成功準則

- [ ] Phase 1 引擎 smoke 通過：微調→匯出→pip 載入辨識，全程指令可重複。
- [ ] v1 模型在固定留出集 exact-match 顯著優於 mobile rec baseline（baseline 預期趨近 0），字元準確率有報告數字。
- [ ] gate 有測試證明：退化候選被拒、現行模型/目錄不被破壞。
- [ ] plugin 無模型時行為不變；有模型時 name 為建議值且仍 `name.unconfirmed`。
- [ ] `name_corrections.jsonl` 可收割成訓練語料（格式轉換有測試）。
- [ ] CHANGELOG / README / policy 全部同步。

## 風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
| --- | --- | --- | --- |
| 官方訓練管線 Windows+CPU 跑不順 | 中 | 高 | Phase 1 smoke 先行；薄殼隔離引擎，必要時換 PaddleX API |
| 字型合成 ≠ 真實手寫，遷移有限 | 高 | 中 | 預期管理（v1 是引擎落地）；修正收割回補；人工確認為底線 |
| CPU 訓練時間過長 | 中 | 中 | mobile 架構＋窄域語料＋少 epochs/凍結 backbone；煙霧先量單 epoch 時間 |
| bundle 體積膨脹 | 低 | 低 | mobile rec ~10MB 級；超標再改下載式（YAGNI） |
| 名用字池涵蓋不足（罕見字） | 中 | 低 | 開放集字典保留輸出能力；罕見字靠人工確認與修正回補 |
