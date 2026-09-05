# TASKS

## In progress（v3 一週一款・大型化・靈感探索器）

- [x] Phase 0（2026-09-05，Batnini）：小修＋7A 大廳真實數據排序＋8A 檢討會／打磨重整＋排程週六 02:00／週日 18:00＋群組推播＋兩則介紹。
- [ ] Phase 1：v3 多階段生產線（Claude-only）＋Steam 榜靈感＋「解構 <遊戲名>」Telegram 指令。下一輪生產 9/12（六）02:00 跑的是 v2.2 管線；v3 請在新模組開發、完成後才切換 bat／排程。
- [ ] Phase 2：Echo 接「獨立評審＋整合稽核」（codex exec read-only、Python 落地、fail-open 回 sonnet）＋每階段用量對帳（跑四款後比）＋全 fable 分級 effort 定案。
- [ ] Phase 3：旗艦化「做大 <名>」走 session 手工做（候選：貓客滿樓無限模式、貓灶封潮夜關卡／波次）。
- [ ] Boss：建 Telegram 群組「SlimeCat Studio」＋加 bot＋群內打「/hi」→ `python factory/studio_setup.py --discover` → `python factory/studio_setup.py <chat_id>`。

## Completed

- [x] Boss 選定 A「遊戲雜誌」（2026-07-15）。
- [x] 重做 SlimeCatArcade 大廳資訊架構與響應式 UI。
- [x] 保留遊戲開啟、點擊統計、評分、留言與更新日誌。
- [x] 補齊分類、最近玩過、縮圖 fallback 與完整狀態。
- [x] 驗證 390×844、1280×720 與核心互動。
- [x] 建立五份協作 SSOT。
- [x] 2026-08-09 三天一產＋低分打磨。
- [x] 2026-09-05 Phase 0（見 CHECKPOINT.md）。

## Later

- [x] 累積真實玩家資料後，口碑精選改用外部留存指標 → 2026-09-05 已改（popScore）。
- [x] genre 大分類 mapping 移到可測試的獨立設定 → `make_game.GENRES`＋`index.html` `GENRE_MAP`。
- [ ] 大廳→遊戲點擊事件上傳（現在看不到「大廳 7 秒漏客」的漏斗）。
- [ ] 打磨／修復改「輸出 patch」不重印整檔（大型遊戲會爆輸出上限；v3 生產線一起做）。
