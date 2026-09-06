# CHECKPOINT

Updated: 2026-09-06 20:35 Asia/Taipei
Task Lead: Batnini
Status: complete（9/6 小改：大廳「排序：最新／熱門」開關＋卡片出廠日期＋`stats.js` 本機不回報，本機預覽驗證過、20:32 push 上線並實讀線上版確認；v3 Phase 1／2 已落地）；Phase 3 旗艦化待 Boss 開工
Branch: main
Last verified commit: 本次 Phase 1／2 程式 commit（見 git log 最新一筆）；工廠自動 commit＝《喵淵吞吞樂》上架＋內容包重生＋打磨；前次基線＝Phase 0 `c983a4b`／`ddf2d03`

## Boss requested（2026-09-05 拍板，完整清單見 DECISIONS.md 同日兩條）

Phase 1：v3 多階段生產線（Claude-only）＋Steam 榜靈感＋「解構 <遊戲名>」指令；Phase 2：Echo 接獨立評審＋整合稽核＋每階段用量對帳。
Kickoff 決策：1A 全鏈試產並上架→成功切排程、2A 靈感一榜合併策劃自己挑、3C 規模由企劃書自訂（上限＝大型）；其餘照建議自決。

## Completed（Phase 1／2）

- `factory/v3/`：`pipeline.py`（`produce_v3`＝企劃書→引擎→內容包→組裝→品管→評審→打磨→上架；`regen_content` 重生內容包；`polish_released` 再打磨）、`stages.py`（各階段 prompt／解析／驗證、模型與 effort、`CAPS`、`BUDGET_USD`、跨包引用 `ref_fields`／`order_packs`／`find_bad_refs`）、`echo_review.py`（Echo 委派、模型退路、fail-open）、`qa.py`（煙霧＋壓力 12 秒＋SC_CONTENT 檢查）、`patch.py`（SEARCH/REPLACE 整行錨定＋去尾空白退路）、`run.py`（`factory/runs/<id>/` 落檔、`run.json`、續跑指標）。
- 入口 `factory/make_game_v3.py`（`--pick`／`--decon`／`--resume`／`--regen … --packs`／`--polish`／`--no-publish`／`--no-echo`）；`decon_now.py`（解構不生產）；`usage_report.py`（用量對帳）；`tests/test_v3.py`（離線 60+ 項＋`--live` haiku 探針）。
- `make_game.py`：`run_claude` 加 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`＋`--max-budget-usd`＋`OutputLimitError`；`stage_deconstruct(pick=)` 兩榜合併＋`ORIGIN:`；`trend_chart`／`save_decon`（md＋.json 側檔）；`notify_release(extra=)`。`fetch_trends.py` 加 Steam（熱銷 10＋新品 15、appdetails 補簡介類型、濾 DLC／成人／工具）。
- 切換：`setup_schedule.py` `ENTRY=make_game_v3.py`（已重跑，下次 9/12 02:00）；`produce_batch.py`（`ENTRY`、單款上限 2.5h）；`produce_now.py` 文案；`original_mode.py` 走 `pipeline.produce_v3`。
- Telegram：skills/slimecat 分冊加「解構 <遊戲名>」「遊戲用量」；CLAUDE.md 意圖列＋Registry 更新；menus.md SlimeCat 區塊更新；bridge 分冊關鍵字加「解構」「用量」（下次重啟生效）。
- 文件：README／DESIGN v3 八階段／PROJECT／AGENTS／TASKS／DECISIONS；memory `project_slimecat_arcade`＋`feedback_codex_cli_model_fallback`＋`feedback_claude_p_output_cap_budget`；brain/lessons 兩條；handoff `2026-09-05-1705-batnini-to-echo-slimecat-v3-echo-review.md`；checkpoint `slimecat-v3-kickoff.md`。

## Verification

- 離線回歸 `factory/tests/test_v3.py`：全部通過（合約解析含髒 JSON／別名鍵、內容包驗證、跨包引用、組裝跳脫、patch、評審解析、Run 續跑、Playwright 壓力測試好壞引擎、GAMEMETA 標頭）；`--live` haiku 企劃書＋內容包探針通過。
- Echo smoke（喵鉤撈撈樂）：61 秒、42/50、稽核抓到真 bug（UTC 換日）；模型退路 gpt-6-astra→gpt-5.6-sol 實測觸發。
- **首款 v3《喵淵吞吞樂》run `v3-20260905-165201`（靈感 Hole Stars: 謎題挑戰，App Store）**：企劃書合約（16 模組、內容包 房間 12／圖鑑 30／貪吃卡 24／功勳 20、驗收 12 條）→ 引擎 640 行／60k 字元（fable high、85k 輸出 tokens、953 秒、$4.86）→ 四包內容過驗證 → 品管過 → Echo 27/50（稽核：房間包引用 24 個不存在的圖鑑 id → 首房軟鎖）→ 打磨 patch 沒套上（模型去改內容 JSON）→ 照「不設出貨門檻」上架＋部署＋兩則介紹（第 60 款）→ `--regen scenes`（跨包引用驗證後一次過、品管過、Echo 再評 38/50）覆蓋上線＋更新日誌 → `--polish`（引擎 4 個邏輯 bug）進行中（結果看 factory.log／games.json changelog）。
- 排程：`schtasks /Query` Factory 下次 2026/9/12 02:00（每週六）、`run_factory.bat` 指向 `make_game_v3.py`；Weekly Review 9/6 18:00、Daily Feedback 不變。

## Decisions and assumptions

- 首航踩雷全部改成護欄（DECISIONS 9/5 第二條末段）：輸出上限 128k＋花費保險絲；企劃書 max→high（1050 秒／$5.16 截斷）；引擎 xhigh→high、2,600→2,000 行（緊縮 1,400／medium）；合約 JSON 只認最外層；內容包依引用排序＋可用 id 清單＋跨包驗證；patch 不動內容包區塊。
- 首航總花費約 $32（含 $15 失敗引擎、企劃書兩次 $8.5、續跑 $7.9、重生＋再評＋打磨約 $3）；護欄後估一款 $8～10。
- 內容包「rules」是散文、沒有機械驗證（再評指出 r01 有 wander 物件、房東尺寸未隨房序上升）：靠評審稽核＋打磨，或之後把可驗證的規則寫進 schema。

## Next actions

1. 9/6（日）18:00 檢討會新版首跑；9/12（六）02:00 v3 排程首航看 factory.log（企劃書合約、引擎行數與 tokens、內容包引用驗證、Echo 評審、用量行）。
2. 跑三～四款後 `python factory/usage_report.py --runs` 對帳，定 effort／模型（`v3/stages.py` 常數）。
3. Boss：Bridge 重啟吃分冊關鍵字；Echo：評估升級 codex CLI。（建群「SlimeCat Studio」9/5 21:05 Boss 拍板不建，推播全走私訊；`studio_setup.py` 留著當選配）
4. Phase 3 旗艦化「做大 <名>」＝手動開 session。

## Risks / blockers

- Echo 評審讀 60k 字元原始碼約 2～3 分鐘、gpt-5.6-sol；Echo 若整個不可用→sonnet（分數口徑會不同，對帳時分開看 `reviewer`）。
- 引擎 640 行卻 60k 字元（長行）：patch 的 SEARCH 段要對到整行，模型改長行容易對不上；再打磨若失敗會維持現版。
- 品管壓力測試只保證「不炸＋內容載入」，不保證可通關；可通關性靠 Echo 稽核＋玩家留言。
- `factory/runs/` gitignored：本機才有完整落檔；企劃書副本在 `knowledge/plans/`（公開 repo）。
