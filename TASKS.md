# TASKS

## In progress（v3 一週一款・大型化・靈感探索器）

- [x] Phase 0（2026-09-05，Batnini）：小修＋7A 大廳真實數據排序＋8A 檢討會／打磨重整＋排程週六 02:00／週日 18:00＋群組推播＋兩則介紹。
- [x] Phase 1（2026-09-05，Batnini）：v3 多階段生產線 `factory/v3/`（企劃書合約→引擎→內容包→組裝→品管壓力測試→評審→patch 打磨→上架，每輪落檔 `factory/runs/`、撞額度續跑）＋Steam 榜靈感（`fetch_trends.py`）＋「解構 <遊戲名>」指令（`decon_now.py`，Telegram 分冊／CLAUDE.md 路由／menus 已加）。
- [x] Phase 2（2026-09-05，Batnini）：Echo 獨立評審＋整合稽核（`v3/echo_review.py`，read-only 委派、fail-open 回 sonnet、模型退路）＋每階段用量對帳工具（`usage_report.py`、TG「遊戲用量」）。
- [ ] Phase 2 對帳（跑三～四款 v3 後）：`python factory/usage_report.py --runs` 比各階段成本 vs 評審／玩家數據，定案 effort 與模型（改 `v3/stages.py` 頂端常數；候選：企劃書 max 是否值得、內容包 sonnet vs fable low、評審 Echo effort）。
- [ ] Phase 3：旗艦化「做大 <名>」走 session 手工做（候選：貓客滿樓無限模式、貓灶封潮夜關卡／波次；v3 首款若評審 `scale_up.worth` 也列候選）。
- [x] Boss：建 Telegram 群組「SlimeCat Studio」→ **2026-09-05 21:05 Boss 拍板不建**，所有推播（含新作兩則介紹）全走 Boss 私訊（DECISIONS 9/5 第四條）；`factory/studio_setup.py` 留著當選配，想拉朋友再設。
- [ ] Echo：評估升級 codex CLI（0.144.1 跑不了 config 的 gpt-6-astra，目前退 gpt-5.6-sol；handoff `2026-09-05-1705-batnini-to-echo-slimecat-v3-echo-review.md`）。
- [ ] Boss：bridge 分冊關鍵字（解構／用量）要等 Batnini Bridge 下次重啟才生效（CLAUDE.md 路由已即時生效）；方便時雙擊 `scripts/batnini_bridge.bat` 或等機器重開。

## Completed

- [x] Boss 選定 A「遊戲雜誌」（2026-07-15）。
- [x] 重做 SlimeCatArcade 大廳資訊架構與響應式 UI。
- [x] 保留遊戲開啟、點擊統計、評分、留言與更新日誌。
- [x] 補齊分類、最近玩過、縮圖 fallback 與完整狀態。
- [x] 驗證 390×844、1280×720 與核心互動。
- [x] 建立五份協作 SSOT。
- [x] 2026-08-09 三天一產＋低分打磨。
- [x] 2026-09-05 Phase 0／1／2（見 CHECKPOINT.md、DECISIONS.md）。

## Later

- [x] 累積真實玩家資料後，口碑精選改用外部留存指標 → 2026-09-05 已改（popScore）。
- [x] genre 大分類 mapping 移到可測試的獨立設定 → `make_game.GENRES`＋`index.html` `GENRE_MAP`。
- [x] 打磨／修復改「輸出 patch」不重印整檔 → v3 `v3/patch.py`（打磨與品管修復）；`fix_game.py`（留言修復）仍重印整檔，待改用同一套 patch。
- [ ] 大廳→遊戲點擊事件上傳（現在看不到「大廳 7 秒漏客」的漏斗）。
- [ ] `fix_game.py` 改 patch 交稿（沿用 `v3/patch.py`），大型 v3 遊戲的留言修復才不會爆輸出上限。
- [ ] 大廳卡片顯示 v3 規模（`packs` 欄已在 games.js，可秀「12 關／8 升級」）。
