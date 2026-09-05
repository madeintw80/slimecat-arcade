# CHECKPOINT

Updated: 2026-09-05 16:10 Asia/Taipei
Task Lead: Batnini
Status: complete（Phase 0）；Phase 1／2 待新 session 開工
Branch: main
Last verified commit: 本次 Phase 0 commit（見 git log 最新一筆）；前次基線＝8/9 三天一產改制 `ed8eb8d`（9/3 健檢）

## Boss requested（2026-09-05 拍板，完整清單見 DECISIONS.md 同日條目）

一週一款（週六 02:00）、v3 多階段生產線（分 Phase）、美術自由、TG 兩則介紹、做大靠手動、Steam 榜＋解構指令、
大廳真實數據排序、檢討會與打磨重整；小修照建議自決。本 checkpoint 只涵蓋 Phase 0。

## Completed（Phase 0）

- `factory/make_game.py` v2.2：`run_claude` 改 `--output-format stream-json --verbose` 收齊所有文字塊（8/30 停產根因）、記用量 `usage.jsonl`、偵測額度（`QuotaError`＋`rate_limit_event.resetsAt`）；`schedule_retry` 撞額度建一次性 schtasks 補跑（同日最多 2 次，`retry_state.json`）；評審半分四捨五入、讀碼上限 160k、多交 `howto/design_choices/pressure_3min/scale_up`；打磨只修第一條缺陷、品管過就採用；`GENRES` 固定 14 類＋`normalize_genre`；美術自由；`recent_lessons` 餵料分流（近 42 天、跳過檢討會行）；`notify_release` 兩則介紹推 `studio_chat.json` 群組（沒設＝Boss 私訊）；`effort` 參數預留。
- `factory/weekly_review.py` v2.2：近 21 天教訓＋整併聖經＋DECISIONS.md＋樣本數守則；輸出 LEARN／PROCESS（→`process_notes.md`）／PRINCIPLE（→聖經第六節累積，>20 條自動整併）／SUMMARY；撞額度補跑。
- `factory/knowledge/fun_principles.md`：17 節「檢討修訂」整併為第六節（12 條設計條文）＋第七節數據判讀守則；流程／產能條文移出。
- `index.html`（7A）：`popScore` 真實數據排序、首屏＝第一名、精選＝2~4 名＋本週新作保底、拿掉「品質 N/50」、`GENRE_MAP` 固定分類、文案改週更。`factory/rebuild.py` 併 `stats` 進 games.js。`daily_feedback.py` 每天順便拉數據＋重建＋部署。
- `games.json`：59 款 genre 遷移到固定清單（20 款改寫，原字串存 `genre_raw`）。
- 排程：`SlimeCat Factory Daily` → 每週六 02:00（`setup_schedule.py` 同時是 `run_factory.bat` 的唯一來源，含心跳＋log 輪轉）；`SlimeCat Weekly Review` → 每週日 18:00；`_common/heartbeat.py` SlimeCat Factory 門檻 80h→186h。
- 新工具 `factory/studio_setup.py`（--discover／<chat_id>／--status／--clear）。
- 文件：PROJECT／AGENTS／TASKS／DECISIONS／README／DESIGN／skills/slimecat 分冊 PM→Boss、週更。

## Verification

- `py_compile` 9 支 PASS；回歸測試 `test_phase0.py` 26 項 PASS（genre 遷移對照、餵料分流、section 抽取、額度文字解析、評審半分／新欄位、weekly 解析與聖經累積、**真 haiku 呼叫** stream-json 收文字＋用量、補跑排程建→查→上限→刪）。
- `schtasks /Query`：Factory 下次 2026/9/12 02:00（每週六；9/5 本身是週六、12:00 那款已出）、Weekly Review 下次 2026/9/6 18:00（每週日）、Daily Feedback 不變。
- 大廳：本機預覽 1280×720／390×844 首屏、精選、分類、評分彈窗、console 無錯誤（見 session 截圖）。
- ⚠️ 完整生產鏈（stream-json 收整份遊戲、兩則介紹、打磨新判準）尚未實跑——**9/12（六）02:00 首航即驗證**（或 Boss 喊「生一個新遊戲」提前試產）；檢討會新版 **9/6（日）18:00** 先跑；工廠備註會附本次用量。

## Decisions and assumptions

- Phase 0 跑的仍是「解構→實作→品管→自評→打磨」單線；v3 多階段（企劃書／引擎／內容包）留 Phase 1，**請在新模組開發、完成後才切換 bat／排程**，避免週六 02:00 跑到半成品。
- 群組推播要 Boss 先建群（TASKS.md 有步驟）；設好前一切照舊推私訊。
- 補跑排程回 0（失敗已被接手），補跑那輪自己有結果碼；補跑任務名 `SlimeCat Retry <kind>` 心跳自動涵蓋。

## Next actions

1. 9/6（日）18:00 檢討會新版首跑看 factory.log（LEARN 是否只談設計、PROCESS 是否分流）；9/12（六）02:00 生產首航看：stream-json 是否收齊整份、兩則介紹是否正常、打磨採用與否、用量行。
2. Boss 建 SlimeCat Studio 群組 → `studio_setup.py`。
3. 新 session 開工 Phase 1／2（checkpoint `agent-workspace/checkpoints/slimecat-v3-kickoff.md` 有完整脈絡）。

## Risks / blockers

- stream-json 事件格式若隨 CLI 版本變動，`run_claude` 有 result 欄／原文兩層退路，但 GAMEMETA 仍可能漏；救援機制（rescue_meta／failed_outputs）保留。
- 打磨「品管過就採用」只擋壞掉、不擋手感變差；靠玩家留言與 7 天複查兜底。
- 大廳 stats 來自 gitignored 的 analytics_summary.json：本機沒跑過 analytics_pull 時 rebuild 不帶 stats（大廳退回新作優先），排程機上每天會有。
