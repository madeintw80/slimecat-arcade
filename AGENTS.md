# AGENTS.md

## Project mode

- `SlimeCatArcade` 是公開網站加每日自動生產排程的生產專案，採保護模式。
- 任一 agent 修改前先讀 `PROJECT.md → CHECKPOINT.md → TASKS.md → DECISIONS.md`，再跑 `git status` 與 `git log -5`。
- 同一時間只有一位 Task Lead 可寫；發現不明 working tree 變更或另一位 agent 標記 `in_progress` 時停手回報 PM。
- Echo 預設唯讀；只有 PM 對該次具體工作明確授權時可修改。push、deploy、排程、對外通知仍需 PM 明確授權。

## Protected areas

- UI 工作不得順便更動 `factory/`、`apps_script/`、排程、分析端點、遊戲規則或遊戲內容。
- `games.json` 是遊戲名錄 SSOT；`games.js` 由工廠重建，禁止手改。
- 禁讀禁寫 `.env`、auth、token、secret、credential、password 類檔案。
- 禁止在 repo、log、handoff 或對話輸出放入任何機密。

## UI verification

- 大廳 UI 修改至少驗證 390×844 與 1280×720。
- 確認遊戲連結、分類、評分彈窗、更新日誌、縮圖 fallback、empty/error state 與 console errors。
- 不得破壞 `sc_config.js`、`stats.js`、`games.js` 的載入順序與既有匿名分析／評分資料契約。

## Completion

- 完成後更新 `CHECKPOINT.md`、`TASKS.md`、必要時 `DECISIONS.md`。
- 建立語意清楚的 commit；只有 PM 明確授權時才 push。
