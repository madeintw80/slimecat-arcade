# PROJECT

## Product

SlimeCat 遊戲區是一個公開靜態小遊戲樂園；大廳展示工廠產出的遊戲，每日排程會持續新增或修正作品。

## Architecture

- `index.html`：公開大廳 UI、分類、遊戲連結、評分與更新日誌。
- `games.json`：遊戲名錄 SSOT。
- `games.js`：由工廠從名錄產生，供大廳同步讀取。
- `games/<id>/index.html`：各款獨立遊戲。
- `stats.js`：匿名開啟／活躍時間分析；未設定端點時自動休眠。
- `sc_config.js`：分析設定載入點，UI 改造不得碰。
- `factory/`：每日自動生產、品管、評分回饋與發佈流程，屬保護範圍。

## Run locally

```powershell
python -m http.server 8877 --bind 127.0.0.1
```

開啟 `http://127.0.0.1:8877/`。

## UI contract

- 大廳以 `GAMES` 陣列渲染，不改遊戲資料 schema。
- 遊戲連結保留 `updated_at` query string，避免修正後仍讀舊快取。
- 遊玩次數沿用 `plays_<id>`；最近玩過另存本機 `sc_recent`，不上傳個資。
- 玩家評分沿用 `sc_myrate_<id>` 與既有 `navigator.sendBeacon` payload。

## Deploy

GitHub Pages 由 `main` 提供公開站。push 屬對外動作，必須有 PM 明確授權。
