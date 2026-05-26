# Changelog

本專案所有重大變更都會記錄在此檔案。

格式基於 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，
本專案遵循 hamanpaul project policy v1.0.0。

## [Unreleased]

### Added
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
