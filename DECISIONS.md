# DECISIONS

## 2026-08-09 — 三天一產＋額度換品質（Boss 拍板、Batnini 落地）

- 生產節奏由每日 12:00 改為**每 3 天 12:00**（schtasks `/SC DAILY /MO 3`；任務名 `SlimeCat Factory Daily` 保留不改，produce_now/produce_batch 手動觸發不受影響）。
- 模型全鏈升一級：解構 sonnet→opus、實作 opus→**fable**（Mythos 級最前沿，CLI 別名實測可用）、自評 haiku→sonnet；`GEN_TIMEOUT` 2700→3600s。
- 新增**打磨迴圈**：自評 < `POLISH_BAR`(40) → 評審改進點餵回開發者修一版 → 重跑品管＋評分、分數有變高才換版（Boss 原話「只有我自己在玩」→ 不搞每款必磨，走低分才磨；0=關閉、50=每款必磨）。
- **不設出貨門檻**：打磨後不論幾分照樣上架。
- 額度估算：每週 ~35 萬 tokens（原每日制 ~65 萬），歷史分佈下約 65% 的款會觸發打磨。
- 留言處理（每日 11:30）與檢討會（週三/週日 18:00）排程**不變**。

## 2026-07-15 — 大廳採 A「遊戲雜誌」

- PM 從 A 遊戲雜誌、B 玩具收藏櫃、C 工廠出刊中選定 A。
- 首屏先回答「今天玩哪一款」，順序為今日主打 → 本週口碑精選 → 玩法分類 → 全部遊戲。
- 每款遊戲保留自己的畫面；品牌共通語言使用米白紙張、墨綠、史萊姆綠與少量莓紅／黃色。
- 遊戲工廠故事保留在品牌文案與更新日誌，不搶過遊戲本身。

## 2026-07-15 — 本次修改與 push 授權

- PM 明確授權 Echo 直接修改正式 repo、commit 並 push。
- 授權限本次大廳 UI 與協作文件；不包含工廠、排程、分析端點、遊戲內容、機密或其他對外操作。

## 2026-09-05 — v3「一週一款・大型化・靈感探索器」Phase 0（Boss 拍板、Batnini 落地）

- **1C 生產節奏**：每週六 02:00 一款（`setup_schedule.py` `/SC WEEKLY /D SAT`，任務名 `SlimeCat Factory Daily` 保留）；檢討會改**每週日 18:00 一次**（週三取消）；留言處理每天 11:30 不變。
- **2B 生產線走 v3 多階段**（Phase 1，Claude-only 先跑；Echo 接「獨立評審＋整合稽核」＝Phase 2，不共同寫程式）。
- **3A 美術完全自由**：不再綁定史萊姆貓宇宙（站名不變）；解構／實作／原創三處 prompt 已改。
- **4B Telegram 兩則介紹**：①靈感／機制／變形／怎麼玩（附截圖）②工廠備註（設計決策／第 3 分鐘壓力源／評審看法／打磨結果／值不值得做大／本次用量）。
- **5C 做大**＝Boss 手動「做大 <名>」為主、數據只提示（評審 `scale_up` 欄）；旗艦化直接開 session 手工做。
- **6B+C 靈感加 Steam 榜＋「解構 <遊戲名>」指令**（Phase 1）。
- **7A 大廳首屏改真實數據排序**：玩家評分＞回訪率＞活躍停留；拿掉「品質 N/50」；本週新作保底精選第一格。
- **8A 檢討會與打磨迴圈重整**：餵料分流（開發者只看近六週非檢討會教訓；檢討會只看近三週）、檢討會讀 `DECISIONS.md`、樣本數守則、聖經 17 節修訂整併成第六節（超過 20 條自動整併）、流程建議另存 `process_notes.md` 不餵開發者；打磨改「只修第一條缺陷、品管過就採用」（不再拿分數當裁判，觸發門檻 `POLISH_BAR=40` 不變）。
- **照建議自行決定**：撞額度自動補跑（`schedule_retry`，同日最多 2 次）、評審半分四捨五入、`claude -p` 改 `--output-format stream-json` 收全段（8/30 停產根因＝多則訊息只回最後一則）、genre 固定 14 類（既有 59 款已遷移、原字串存 `genre_raw`）、評審讀碼上限 45k→160k 字、文件 PM→Boss、heartbeat 門檻 80h→186h、推播群組＝同一 Batnini bot 送 `studio_chat.json` 的群組（Boss 建群後用 `studio_setup.py` 設）。
- **維持不變**：不設出貨門檻、不凍結新作、不自動下架（8/9 決議續用）；模型 opus/fable/sonnet 三段（全 fable 分級 effort 留 Phase 2 對帳後定）。

## 2026-09-05 — v3 Phase 1／2：多階段生產線＋Steam 靈感＋解構指令＋Echo 評審（Boss 拍板 1A／2A／3C，Batnini 落地）

- **1A 試產範圍**：v3 做完立刻全鏈試產一款並上架（含 push＋兩則介紹，沿用「不設出貨門檻」），成功即把 `setup_schedule.py` 的 `ENTRY` 指向 `make_game_v3.py` 重跑（9/12 02:00 首航＝v3）；`produce_now`／`produce_batch`／`original_mode` 一併切 v3。
- **2A 靈感混榜**：App Store 台灣 Top 40＋Steam 熱銷 Top 10／新品熱門 Top 15 一榜合併給策劃自己挑（`fetch_trends.py` 抓 featuredcategories＋appdetails 補簡介類型、濾 DLC／成人／純工具）；Steam 條目標「PC 大作要濃縮成一個核心迴圈」；解構筆記多 `ORIGIN:` 標頭。
- **3C 大型化規模**：由企劃書依機制自訂，硬上限＝大型（內容包最多 4 種×30 筆、引擎 2,600 行、單局 3～10 分鐘，`v3/stages.py` 的 `CAPS`）。
- **Echo 角色（Phase 2）**：獨立評審（五維＋改進點＋工廠備註素材）＋整合稽核（`audit.contract_issues`／`audit.bugs`）；稽核缺陷一律 patch 修（bug 優先最多 2＋合約缺陷 1）、都沒有才看 `POLISH_BAR` 40 修評審第一條；Echo 不可用 fail-open 回 sonnet、生產不停；不改 BRAIN.md 白名單（SlimeCat 保護模式、Echo 唯讀）。Echo 模型＝先讀 `~/.codex/config.toml` 現役再退 `gpt-5.6-sol`（codex-cli 0.144.1 跑不了 gpt-6-astra，升級交 Echo 決定，handoff 9/5）。
- **照建議自決**：模型／effort 首輪配置＝企劃書 fable `high`（原定 `max`，首航第 1 次實測 1050 秒／66k 輸出 tokens／$5.16 且合約 JSON 壞掉→當場改 high＋篇幅上限）／引擎 fable `xhigh`／內容包 sonnet／評審 Echo high／打磨 fable `high`，**跑三～四款後用 `usage_report.py --runs` 對帳再定案**；「解構 <遊戲名>」帶參數走模型路由、不做鍵盤按鈕（bridge 分冊關鍵字加「解構」「用量」即可）；打磨與品管修復改 SEARCH/REPLACE patch 交稿（套不上整包放棄、沿用原版）；每輪產出落 `factory/runs/`（gitignored）、企劃書永久存 `knowledge/plans/`（公開）；撞額度續跑指標 `v3_resume.json`；成品 GAMEMETA 由合約組、不再靠模型交標頭；games.json 新欄 `pipeline`／`packs`／`reviewer`。
- **首航當場加的護欄（Batnini 自決）**：`claude -p` 預設輸出上限 64k tokens（思考也算）把 xhigh 引擎截斷、CLI 自動重試燒到 $15 → `run_claude` 子程序設 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`（fable 實測接受）＋每階段 `--max-budget-usd` 保險絲（企劃書 4／引擎 9／內容包 1.5／評審 1.5／打磨 4）；引擎 effort xhigh→`high`、行數上限 2,600→2,000（緊縮重試 1,400／medium）；企劃書 effort max→`high`＋篇幅 3～5k 字；合約 JSON 只認最外層、壞掉存 `failed_outputs/`。
- **維持不變**：不設出貨門檻、不凍結新作、不自動下架；v2.2 單線 `make_game.py` 保留當退路（`ENTRY` 改回即可）；留言 11:30／檢討會週日 18:00 不動。

## 2026-09-05 — 新品推播不建群組（Boss 拍板 21:05）

- **不建「SlimeCat Studio」群組**：所有工廠推播（含每週新作兩則介紹）全走 Boss 私訊，理由＝目前自己看就好、不需要分流。`factory/studio_chat.json` 不建，`send_public` 走預設對象，程式不用改。
- `factory/studio_setup.py` 保留當選配：哪天想拉朋友進群一起看新遊戲，照檔頭四步設定即可，隨時 `--clear` 改回私訊。
- Echo bot 不加群：Telegram bot 收不到別的 bot 發的訊息，加了也看不到介紹；Echo 評審已透過 codex exec 進生產線，結果直接讀 `factory/runs/<run_id>/review.json`。
- 附帶勘誤：`studio_setup.py` 檔頭寫「修復完成」也進群，實際 `fix_game.py` 用 `tg.send` 走私訊；改 `fix_game.py` patch 交稿時一併校正說明。

## 2026-09-06 — 大廳加「排序」開關（Boss 提、Batnini 落地）

- **Boss**：網站至少要有依遊戲日期排序。清單其實一直是出廠日新→舊，但卡片沒印日期、也沒有開關，看不出來。
- **落地**：分類列右側加「排序：最新／熱門」（最新＝出廠日新→舊、預設；熱門＝與首屏同一套 `popScore`），選擇記在 `localStorage.sc_sort` 下次沿用；每張卡片 topline 印出廠日期。首屏主打／精選欄不受影響。
- **順手**：`stats.js` 在 localhost／127.0.0.1／file:// 一律不回報，本機預覽與 Playwright 品管（file://）不再灌進真實數據。
- 驗證：本機預覽 port 3462，最新／熱門切換與記憶、59 張卡片都有日期、手機 375px 無橫向溢出、無 console 錯誤。上線＝push 後 GitHub Pages 生效，待 Boss 拍板。

