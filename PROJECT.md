# PROJECT

## Product

SlimeCat 遊戲區是一個公開靜態小遊戲樂園；大廳展示工廠產出的遊戲，排程（**每週六 02:00 一款**，2026-09-05 起；前為三天一款）會持續新增或修正作品。大廳首屏與精選由**真實玩家數據**排序（玩家評分＞回訪率＞活躍停留），AI 自評分數不對外顯示（Boss 2026-09-05 拍板 7A）。

## Architecture

- `index.html`：公開大廳 UI、分類、遊戲連結、評分與更新日誌。首屏＝真實數據第一名（沒數據時＝最新一款）、精選＝第 2~4 名＋本週新作保底一格。
- `games.json`：遊戲名錄 SSOT。`genre` 固定 14 類（`factory/make_game.py` 的 `GENRES`；2026-09-05 遷移前的自由文字保留在 `genre_raw`）。
- `games.js`：由工廠從名錄產生（`factory/rebuild.py`），每款可附 `stats`（opens／devices／med_session_sec／return_rate／web_score_med／web_raters），來源 `factory/analytics_summary.json`（每天 11:30 留言排程順便刷新）。
- `games/<id>/index.html`：各款獨立遊戲。
- `stats.js`：匿名開啟／活躍時間分析；未設定端點時自動休眠。
- `sc_config.js`：分析設定載入點，UI 改造不得碰。
- `factory/`：自動生產（每週六 02:00）、品管、低分打磨（只修評審第一條缺陷、品管通過就採用）、留言迴圈（每天 11:30）、檢討會（每週日 18:00）與發佈流程，屬保護範圍。
- `factory/studio_chat.json`（gitignored）：SlimeCat Studio 群組 chat_id，新品兩則介紹推這裡；沒設就推 Boss 私訊。用 `factory/studio_setup.py` 設定。

## Run locally

```powershell
python -m http.server 8877 --bind 127.0.0.1
```

開啟 `http://127.0.0.1:8877/`。（Claude Code 瀏覽器預覽用 `.claude/launch.json` 的 `slimecat-lobby`，port 3462。）

## UI contract

- 大廳以 `GAMES` 陣列渲染。2026-09-05 起每款可帶 `stats` 物件（沒數據就沒有這欄，UI 必須能退回「新鮮出廠／你玩過 N 次」）與 `howto`（一句話怎麼玩，評審產出）。
- 大廳不顯示 `ai_score`；排序邏輯在 `popScore()`（玩家評分×8＋回訪率×30（opens ≥5）＋停留×15（opens ≥2，300 秒封頂）＋開啟量微調；權重用 9/2 實際數據校過，喵骰連鎖陣／貓客滿樓／貓灶封潮夜前三）。
- 遊戲連結保留 `updated_at` query string，避免修正後仍讀舊快取。
- 遊玩次數沿用 `plays_<id>`；最近玩過另存本機 `sc_recent`，不上傳個資。
- 玩家評分沿用 `sc_myrate_<id>` 與既有 `navigator.sendBeacon` payload。

## Deploy

GitHub Pages 由 `main` 提供公開站。工廠的 `publish_site.py` 只 add 站點內容白名單再 push（排程自動部署＝既有授權）；程式碼變更要人看過再 commit。push 屬對外動作，必須有 Boss 明確授權。
