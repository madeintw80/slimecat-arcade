# SlimeCat 遊戲區 🐱🟢

復刻「史萊姆好玩遊戲區」精神的本機小遊戲樂園 —— 附一座**會自己生產新遊戲的工廠**。

## 怎麼玩

直接雙擊 `index.html`（用瀏覽器開）→ 進大廳 → 點遊戲卡片開玩。手機瀏覽器開同一個檔也能玩（觸控支援）。
線上版：https://madeintw80.github.io/slimecat-arcade/

## 工作室怎麼運作（v2.2：會學習的生產線，一週一款）

目標不是「生很多遊戲」，是**一款比一款好玩**。每週六 02:00 排程
`SlimeCat Factory Daily`（任務名沿用）跑 `factory/make_game.py` 的完整學習迴圈
（沿革：每日一款 7/4 → 三天一款 8/9 → 一週一款 9/5：產量換品質，省下的額度做大做好）：

1. **抓趨勢**：`fetch_trends.py` 抓 App Store 台灣免費遊戲排行榜 Top 100
2. **解構**（策劃課）：claude 挑一款熱門遊戲，拆解「為什麼好玩、為什麼上癮」
   （near-miss？歸因於己？指數獎勵？）→ 筆記永久存到 `knowledge/deconstructions/`
3. **設計＋實作**（開發課）：帶著三份資料生成遊戲——
   `knowledge/fun_principles.md`（設計聖經）＋這次的解構筆記＋`knowledge/learnings.md`
   近六週的設計類教訓（玩家留言／修復根因／自評改進點，**權重最高**；檢討會的流程建議不餵開發者）。
   美術風格自由（2026-09-05 起不綁史萊姆貓）。
4. **品管**：`validate_game.py` 用 Playwright 實測（噴錯不上架，自動重生一次）
5. **出廠自評**（評審課）：claude 評審按五維量表打分（上手/juice/目標/難度/再一局，
   滿分 50；半分四捨五入），同時交出「怎麼玩／設計決策／第 3 分鐘壓力源／值不值得做大」。
   分數只做內部訊號，**不上大廳**。
6. **打磨**（低分才觸發）：自評低於 40/50 → 只修評審點名的**第一條缺陷**，修訂版品管通過就採用
   （`make_game.py` 的 `POLISH_BAR` 可調；0=關、50=每款必磨）
7. **上架＋通知**：登記名錄、部署、Telegram 推**兩則介紹**（①靈感／機制／變形／怎麼玩＋截圖
   ②工廠備註：設計決策／壓力源／評審看法／打磨結果／值不值得做大／本次用量）到
   SlimeCat Studio 群組（`factory/studio_setup.py` 設定；沒設就推 Boss 私訊）

撞到 claude 訂閱額度不會停產：照額度重置時間自動建一次性排程補跑（同日最多 2 次）。

### 回饋迴圈（讓它越來越強的關鍵）

```bash
# 玩完評分（1-10 + 評語）——玩家評分 > AI 自評 > 理論
python C:/Users/User/projects/SlimeCatArcade/factory/rate_game.py 彈跳 8 手感好但後期太簡單

# Telegram 也可以：「遊戲評分 彈跳 8 手感好但後期太簡單」
# 立刻加產一款：「生一個新遊戲」（Telegram）或跑 factory/produce_now.py
```

大廳首屏與精選由**真實數據**排序（網頁玩家評分＞回訪率＞活躍停留），卡片顯示
「玩家 8/10（1 人評）」「玩過 15 次 · 一局約 4 分鐘」這類真實訊號；數據每天 11:30 隨留言排程刷新。
玩家在大廳「評分」留言 → 每天 11:30 `daily_feedback.py` 分流（能改的直接改款上線、模糊的記筆記）
→ 官方回覆發布回大廳。每週日 18:00 `weekly_review.py` 檢討會回頭修設計聖經。

## 常用指令

```bash
# 立刻手動生一款（不等排程）
python C:/Users/User/projects/SlimeCatArcade/factory/make_game.py

# 只看今天排行榜抓到什麼
python C:/Users/User/projects/SlimeCatArcade/factory/fetch_trends.py

# 單獨測某款遊戲有沒有問題
python C:/Users/User/projects/SlimeCatArcade/factory/validate_game.py games/<id>/index.html

# 改過 games.json 之後重建大廳名錄（會順便把 analytics_summary.json 的數據併進 games.js）
python C:/Users/User/projects/SlimeCatArcade/factory/rebuild.py

# 重建排程（改星期／時間編輯 setup_schedule.py 的 RUN_DAY / RUN_AT 再跑一次；它也是 run_factory.bat 的唯一來源）
python C:/Users/User/projects/SlimeCatArcade/factory/setup_schedule.py

# 設定新品推播群組（Boss 建群＋加 bot＋群內打「/hi」後）
python C:/Users/User/projects/SlimeCatArcade/factory/studio_setup.py --discover
python C:/Users/User/projects/SlimeCatArcade/factory/studio_setup.py <chat_id>
```

## 下架不好玩的遊戲

```bash
python C:/Users/User/projects/SlimeCatArcade/factory/retire_game.py <遊戲名>     # --revive 復活
python C:/Users/User/projects/SlimeCatArcade/factory/publish_site.py "下架調整"
```

## 排程管理

```
暫停生產：schtasks /Change /TN "SlimeCat Factory Daily" /Disable
恢復生產：schtasks /Change /TN "SlimeCat Factory Daily" /Enable
立刻生一款：schtasks /Run /TN "SlimeCat Factory Daily"
```

三條排程：`SlimeCat Factory Daily`（每週六 02:00 生產）／`SlimeCat Daily Feedback`（每天 11:30 留言）／
`SlimeCat Weekly Review`（每週日 18:00 檢討）。撞額度時會多出一次性的 `SlimeCat Retry <kind>`。
生產紀錄在 `factory/factory.log`；每款遊戲截圖在 `factory/shots/`；每次 claude 呼叫的用量在 `factory/usage.jsonl`。

⚠️ 工廠靠 `claude -p`，CLI token 過期（401）會停產並在 log 標明 —— 跑
`scripts/claude_relogin.bat` 重登即可。

## 檔案結構

```
SlimeCatArcade/
├── index.html          # 遊戲大廳（真實數據排序）
├── games.js            # 大廳讀的名錄（自動產生，別手改；含每款 stats）
├── games.json          # 名錄真相來源（genre 固定 14 類）
├── games/<id>/index.html   # 每款遊戲一個資料夾（單檔遊戲）
├── run_factory.bat / run_feedback.bat / run_weekly.bat   # 排程進入點（由 factory/setup_*.py 產生）
└── factory/
    ├── make_game.py        # 生產主流程（解構→設計→品管→自評→打磨→上架→兩則介紹）
    ├── weekly_review.py    # 檢討會（近三週教訓＋整併聖經＋DECISIONS＋樣本數守則）
    ├── daily_feedback.py   # 每日留言分流＋改款＋回覆＋刷新大廳數據
    ├── fix_game.py         # AI 修復（回報／留言驅動）
    ├── original_mode.py    # 原創模式（機制原子庫抽組合）
    ├── fetch_trends.py     # App Store 榜單
    ├── validate_game.py    # Playwright 品管
    ├── analytics_pull.py   # 拉遊玩數據成績單
    ├── rate_game.py        # 玩家評分入口（回饋迴圈）
    ├── produce_now.py      # 立刻加產一款（觸發排程）
    ├── studio_setup.py     # 新品推播群組設定
    ├── rebuild.py          # games.json（＋數據）→ games.js
    ├── setup_schedule.py / setup_weekly.py / setup_feedback.py   # 排程安裝器（冪等）
    ├── history.json        # 用過的靈感（避免重複）
    ├── trends.json         # 最近一次榜單快取
    ├── shots/              # 遊戲截圖
    └── knowledge/          # 工作室的大腦（會隨時間變厚）
        ├── fun_principles.md    # 設計聖經：上癮機制/經典解構/出貨清單/評審量表/檢討會實證修訂（累積）
        ├── learnings.md         # 玩家留言 + 修復根因 + AI 自評教訓（生產前讀近六週）
        ├── mechanism_atoms.md   # 機制原子庫（原創模式原料）
        └── deconstructions/     # 每款靈感來源的解構筆記
```

## 下一步（v3 路線圖，見 CHECKPOINT.md / TASKS.md）

- Phase 1：v3 多階段生產線（企劃書→引擎→內容包）＋Steam 榜靈感＋「解構 <遊戲名>」Telegram 指令
- Phase 2：Echo（Codex）接獨立評審＋整合稽核、每階段用量對帳、模型／effort 定案
- Phase 3：旗艦化「做大 <名>」
