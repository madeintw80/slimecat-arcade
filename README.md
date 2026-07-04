# SlimeCat 遊戲區 🐱🟢

復刻「史萊姆好玩遊戲區」精神的本機小遊戲樂園 —— 附一座**會自己生產新遊戲的工廠**。

## 怎麼玩

直接雙擊 `index.html`（用瀏覽器開）→ 進大廳 → 點遊戲卡片開玩。手機瀏覽器開同一個檔也能玩（觸控支援）。

## 工作室怎麼運作（v2：會學習的生產線）

目標不是「生很多遊戲」，是**一款比一款好玩**。每天 12:00 排程
`SlimeCat Factory Daily` 跑 `factory/make_game.py` 的完整學習迴圈：

1. **抓趨勢**：`fetch_trends.py` 抓 App Store 台灣免費遊戲排行榜 Top 100
2. **解構**（策劃課）：claude 挑一款熱門遊戲，拆解「為什麼好玩、為什麼上癮」
   （near-miss？歸因於己？指數獎勵？）→ 筆記永久存到 `knowledge/deconstructions/`
3. **設計＋實作**（開發課）：帶著三份資料生成遊戲——
   `knowledge/fun_principles.md`（設計聖經）＋這次的解構筆記＋`knowledge/learnings.md`
   （玩家評分與歷次教訓，**權重最高**）
4. **品管**：`validate_game.py` 用 Playwright 實測（噴錯不上架，自動重生一次）
5. **出廠自評**（評審課）：claude 評審按五維量表打分（上手/juice/目標/難度/再一局，
   滿分 50），分數上卡片、改進點記進 learnings 餵下一款
6. **上架＋通知**：登記名錄、Telegram 推新品（含自評分）＋截圖

### 回饋迴圈（讓它越來越強的關鍵）

```bash
# 玩完評分（1-10 + 評語）——玩家評分 > AI 自評 > 理論
python C:/Users/User/projects/SlimeCatArcade/factory/rate_game.py 彈跳 8 手感好但後期太簡單

# Telegram 也可以：「遊戲評分 彈跳 8 手感好但後期太簡單」
# 立刻加產一款：「生一個新遊戲」（Telegram）或跑 factory/produce_now.py
```

大廳卡片會顯示：👤 玩家評分、🤖 AI 自評、玩過次數（本機點擊數）。
真正的點擊率/留存率等站點上線有外部玩家後，再接分析工具（Phase 3）。

## 常用指令

```bash
# 立刻手動生一款（不等排程）
python C:/Users/User/projects/SlimeCatArcade/factory/make_game.py

# 只看今天排行榜抓到什麼
python C:/Users/User/projects/SlimeCatArcade/factory/fetch_trends.py

# 單獨測某款遊戲有沒有問題
python C:/Users/User/projects/SlimeCatArcade/factory/validate_game.py games/<id>/index.html

# 改過 games.json 之後重建大廳名錄
python C:/Users/User/projects/SlimeCatArcade/factory/rebuild.py

# 重建排程（改時間就編輯 setup_schedule.py 的 RUN_AT 再跑一次）
python C:/Users/User/projects/SlimeCatArcade/factory/setup_schedule.py
```

## 下架不好玩的遊戲

1. 打開 `games.json`，刪掉那款的整段 entry
2. 跑 `python factory/rebuild.py`
3. （可選）刪掉 `games/<id>/` 資料夾

## 排程管理

```
暫停生產：schtasks /Change /TN "SlimeCat Factory Daily" /Disable
恢復生產：schtasks /Change /TN "SlimeCat Factory Daily" /Enable
立刻生一款：schtasks /Run /TN "SlimeCat Factory Daily"
```

生產紀錄在 `factory/factory.log`；每款遊戲截圖在 `factory/shots/`。

⚠️ 工廠靠 `claude -p`，CLI token 過期（401）會停產並在 log 標明 —— 跑
`scripts/claude_relogin.bat` 重登即可。

## 檔案結構

```
SlimeCatArcade/
├── index.html          # 遊戲大廳
├── games.js            # 大廳讀的名錄（自動產生，別手改）
├── games.json          # 名錄真相來源
├── games/<id>/index.html   # 每款遊戲一個資料夾（單檔遊戲）
├── run_factory.bat     # 排程進入點
└── factory/
    ├── make_game.py        # 生產主流程（解構→設計→品管→自評）
    ├── fetch_trends.py     # App Store 榜單
    ├── validate_game.py    # Playwright 品管
    ├── rate_game.py        # 玩家評分入口（回饋迴圈）
    ├── produce_now.py      # 立刻加產一款（觸發排程）
    ├── rebuild.py          # games.json → games.js
    ├── setup_schedule.py   # 排程安裝器
    ├── history.json        # 用過的靈感（避免重複）
    ├── trends.json         # 最近一次榜單快取
    ├── shots/              # 遊戲截圖
    └── knowledge/          # 工作室的大腦（會隨時間變厚）
        ├── fun_principles.md    # 設計聖經：上癮機制/經典解構/出貨清單/評審量表
        ├── learnings.md         # 玩家評分 + AI 自評教訓（生產前必讀）
        └── deconstructions/     # 每款靈感來源的解構筆記
```

## Phase 2 點子（還沒做）

- Google Play 榜單（`pip install google-play-scraper`）＋ 遊戲評測網站（claude -p 加 WebSearch）
- 上線 GitHub Pages 變公開網址 → 接真實分析（點擊率/留存率/平均遊玩時長）回饋設計
- 遊戲下架指令、大廳顯示遊戲截圖縮圖
- 「每週檢討」排程：讀全部評分數據回頭修 fun_principles.md 本身（後設學習）
