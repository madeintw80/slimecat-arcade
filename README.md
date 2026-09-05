# SlimeCat 遊戲區 🐱🟢

復刻「史萊姆好玩遊戲區」精神的本機小遊戲樂園 —— 附一座**會自己生產新遊戲的工廠**。

## 怎麼玩

直接雙擊 `index.html`（用瀏覽器開）→ 進大廳 → 點遊戲卡片開玩。手機瀏覽器開同一個檔也能玩（觸控支援）。
線上版：https://madeintw80.github.io/slimecat-arcade/

## 工作室怎麼運作（v3：一週一款・大型化・靈感探索器）

目標不是「生很多遊戲」，是**一款比一款好玩、而且做大做好**。每週六 02:00 排程
`SlimeCat Factory Daily`（任務名沿用）跑 `factory/make_game_v3.py` 的多階段生產線
（沿革：每日一款 7/4 → 三天一款 8/9 → 一週一款 9/5：產量換品質，省下的額度做大做好；
v2.2 單線管線 `make_game.py` 保留當退路）：

1. **抓趨勢**：`fetch_trends.py` 抓 App Store 台灣免費遊戲榜 Top 100 ＋ **Steam 熱銷／新品熱門**
   （繁中名稱＋簡介＋類型；濾掉 DLC／成人作）——兩份榜合併給策劃自己挑
2. **解構**（策劃課）：claude 挑一款熱門遊戲，拆解「為什麼好玩、為什麼上癮」
   （near-miss？歸因於己？指數獎勵？；Steam 的 PC 大作要濃縮成一個核心迴圈）
   → 筆記永久存到 `knowledge/deconstructions/`（同名 `.json` 側檔記標頭）。
   Telegram 打「解構 <遊戲名>」可以只解構不生產（`decon_now.py`）
3. **企劃書＋模組合約**（fable，effort high；max 首航實測 17 分鐘／$5 且合約壞掉，不划算）：把解構筆記展開成可分工的企劃書＋ JSON 合約——
   引擎要有哪些模組、每種內容包（關卡／波次／升級／圖鑑）的欄位 schema／數量／設計原則／範例、
   跨局進度存什麼、8～12 條可觀察的驗收清單。規模由企劃書依機制自訂（上限：內容包 4 種×30 筆、引擎 2,600 行）。
   企劃書永久存到 `knowledge/plans/`
4. **引擎**（fable，effort xhigh，**單一作者**）：一次寫完單檔引擎；內容不寫死，從 `window.SC_CONTENT` 讀；
   檔內附 `<!--CONTENT-NOTES-->`（它真正支援的欄位與範圍）與 `window.SC_HOOKS`（品管自動化用）。
   先用合約範例跑煙霧測試，壞了重生（不浪費後面的呼叫）
5. **內容包**（sonnet，逐包生成）：照合約 schema＋引擎 CONTENT-NOTES 填 JSON，型別／欄位／id／筆數驗證，不合重生一次
6. **組裝＋品管**：把內容包接進引擎 → Playwright 煙霧測試＋**壓力測試**（真的開始遊戲亂玩 12 秒，
   確認內容包載入、開場後不炸）；沒過先用 patch 修一輪
7. **評審＋整合稽核**（Phase 2）：先委派 **Echo**（Codex，read-only 沙盒）當獨立評審——五維量表＋
   稽核「合約寫了但成品沒做」與「確定會發生的 bug」；Echo 不可用就 fail-open 回 sonnet。
   分數只做內部訊號，**不上大廳**
8. **打磨**（patch 交稿，不重印整檔）：稽核有 bug／合約缺陷一律修；都沒有但自評低於 40/50 就修評審第一條；
   修訂版品管通過才採用（`POLISH_BAR` 在 `make_game.py`）
9. **上架＋通知**：登記名錄、部署、Telegram 推**兩則介紹**（①靈感／機制／變形／怎麼玩＋截圖
   ②工廠備註：設計決策／壓力源／評審看法／打磨結果／值不值得做大／本次用量／v3 階段與評審是誰）到
   SlimeCat Studio 群組（`factory/studio_setup.py` 設定；沒設就推 Boss 私訊）

每一輪的所有產出落在 `factory/runs/<run_id>/`（企劃書／合約／引擎／內容包／品管／評審／patch／用量）。
撞到 claude 訂閱額度不會停產：照額度重置時間自動建一次性排程補跑（同日最多 2 次），
補跑那輪**從斷點續跑**（`v3_resume.json` 指標），已完成的企劃書／引擎不用重付。

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
# 立刻手動生一款（不等排程；v3 生產線）
python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py
python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py --pick "Balatro"        # 點名靈感
python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py --decon <筆記路徑>      # 用既有解構筆記
python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py --resume <run_id>       # 從斷點續跑
python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py --no-publish --no-echo  # 開發用：不部署、評審不問 Echo
python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py --regen <run_id> --packs scenes   # 已上架：重生內容包（沿用引擎）覆蓋上線
python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py --polish <run_id>      # 已上架：用最新評審的稽核結果再打磨一輪

# 只解構不生產（Telegram「解構 <遊戲名>」同款）
python C:/Users/User/projects/SlimeCatArcade/factory/decon_now.py "遊戲名"

# 用量對帳（各階段 tokens／$／秒＋每輪 v3 run 小計；定 effort／模型用）
python C:/Users/User/projects/SlimeCatArcade/factory/usage_report.py --runs

# v3 回歸測試（離線；--live 多跑一次 haiku 探針）
python C:/Users/User/projects/SlimeCatArcade/factory/tests/test_v3.py

# 只看今天排行榜抓到什麼（App Store＋Steam）
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
    ├── make_game_v3.py     # v3 入口（排程跑這支）：抓榜→解構→v3 生產線→上架
    ├── v3/                 # v3 多階段生產線
    │   ├── pipeline.py     #   總管：企劃書→引擎→內容包→組裝→品管→評審→打磨→上架
    │   ├── stages.py       #   各階段 prompt／解析／驗證＋模型與 effort 設定
    │   ├── echo_review.py  #   Phase 2：委派 Echo 評審（fail-open 回 sonnet）
    │   ├── qa.py / patch.py / run.py   # 品管壓力測試／SEARCH-REPLACE patch／每輪紀錄與續跑
    ├── runs/<run_id>/      # 每輪產出（gitignored）
    ├── make_game.py        # 共用函式（run_claude／解構／上架／推播／撞額度補跑）＋v2.2 單線管線（退路）
    ├── decon_now.py        # 「解構 <遊戲名>」只解構不生產
    ├── usage_report.py     # 用量對帳
    ├── tests/test_v3.py    # v3 回歸測試
    ├── weekly_review.py    # 檢討會（近三週教訓＋整併聖經＋DECISIONS＋樣本數守則）
    ├── daily_feedback.py   # 每日留言分流＋改款＋回覆＋刷新大廳數據
    ├── fix_game.py         # AI 修復（回報／留言驅動）
    ├── original_mode.py    # 原創模式（機制原子庫抽組合）
    ├── fetch_trends.py     # App Store 榜單＋Steam 榜單
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
        ├── deconstructions/     # 每款靈感來源的解構筆記（＋.json 側檔）
        └── plans/               # 每款的企劃書＋模組合約
```

## 下一步（v3 路線圖，見 CHECKPOINT.md / TASKS.md）

- ✅ Phase 1：v3 多階段生產線（企劃書→引擎→內容包）＋Steam 榜靈感＋「解構 <遊戲名>」Telegram 指令
- ✅ Phase 2：Echo（Codex）接獨立評審＋整合稽核、每階段用量對帳（`usage_report.py`）；模型／effort 跑三～四款後定案
- Phase 3：旗艦化「做大 <名>」
