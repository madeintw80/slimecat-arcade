# CHECKPOINT

Updated: 2026-10-19 08:0x Asia/Taipei
Task Lead: Batnini
Status: complete（10/19 早：3D 煙霧測試失敗自動重跑一次，見下節；10/18 晚：10/24 週更骨架鎖定「經營＋班次」＋《喵窟擋十波》修 Echo 評審剩下四項，只做本機 commit 未 push，見下節；10/14 早：補驗排程直譯器＋骨架鎖定乾跑；10/13 晚：生產線開放 3D＋試產模式上線，3D 試產《喵穿層連落》完成待 Boss 試玩，見下節；10/13 早：10/17 週更骨架鎖定「塔防＋波次」）；Phase 3 旗艦化待 Boss 開工

## 2026-10-19 早這輪（gateway job-20261019-075743-15b2，initiator=grokbot；Boss「修 SlimeCatArcade 的 3D 煙霧測試：失敗自動重試」）

- 起因：10/18～10/19 補證 4 跑 2 敗，都是「3D：引擎煙霧測試位置（runs/<run>/）載得到站內 three.js」這條報 `THREE.WebGLProgram: Shader Error`（headless 軟體繪圖偶發），怕週更品管誤判。
- 改了：只動 `factory/tests/test_v3.py` 那一條（10c 節 `validate_game.validate(_deep / "engine_probe.html")`）：第一次失敗印「⚠️ 3D 煙霧測試第一次失敗，自動重跑一次：<錯誤>」再跑一次，第二次仍失敗照常判 ❌。其他測試（含上面的 `qa.stress` 3D 樣本）沒加重試。
- 驗證：`python factory/tests/test_v3.py` 連跑 3 次全部 exit 0、「🎉 全部通過」、每次 142 條 check ✅（另有 1 行品管 log 帶 ✅，合計 143 個 ✅，跟 10/18 記的 143 是同一種算法）、0 條 ❌；第 3 次實際觸發重試（第一次 Shader Error → 重跑通過）。
- 沒動：`factory/knowledge/learnings.md` 的未提交 4 行（10/18 檢討會排程寫的）照舊未碰；沒 push、沒碰排程。

## 2026-10-18 晚這輪（gateway job-20261018-193641-5ae6，initiator=grokbot；Boss「允許寫入 SlimeCatArcade：10/24 鎖定經營＋班次，並修喵窟擋十波剩下四項」）

- **骨架鎖定 10/24**：`factory/skeleton_lock.json` 新增一筆 `2026-10-24`（grace 2 天＝到 10/26）、`skeleton`＝經營＋班次、`genre`＝經營；三條核心規則寫明「常駐可見進度／短決策／會失敗」，規格併入 10/18 檢討會教訓（標題一句、冪等選取、登場表、固定班做完才進無限、星等門檻同表推算）。10/17 那筆保留（日期過了自動失效）。`make_game_v3.skeleton_decon()` 原本寫死「核心迴圈＝放塔擋波次」，改讀可選欄 `core_loop`／`avoid`／`spec_source`（沒寫就用塔防版預設字，舊鎖定行為不變）。
- **《喵窟擋十波》四項**（只改 `games/2026-10-17-001/index.html`）：
  - (a) 第 10 波沒清完不會進無限波：`holdFinal()`＝第 10 波以後且未通關時，主迴圈不開下一波、提早開波鈕也不給；`onVictory()` 改成通關後 `VICTORY_GAP`＝6 秒接第 11 波（提早清完也不再等原倒數）。HUD／底列在等通關時顯示「清光就通關」。
  - (b) 內容包 `waves`：第 2 波加 shuttle_moth、第 5 波加 split_thread、第 7 波加 loose_thread 群、第 8～10 波混入，第 9 波六種怪到齊；無限樣板 e11～e14 補上三種怪；loose_thread `introWave` 7→5（跟分線怪同波）。
  - (c) 新增免費「🐾 拍擊」（底列右下，原提早開波鈕切成上下兩半；鍵盤 C）：冷卻 8 秒，拍最接近貓窟那隻＋半徑 56 內的怪（傷害 6＋2×波數，地面怪減速 50% 2 秒，圈＝實際判定範圍）。另外開戰前若魚乾花到蓋不起任何塔，提早開波鈕變「立即開戰」（還蓋得起時照舊只教放塔）。
  - (d) 標題頁只留「擋住 10 波，別讓貓窟被攻破」＋選卡示意；四行操作鍵移到暫停畫面，回訪紀錄本來就在選圖頁與結算頁。
  - 順手：選卡改完全冪等（`R.sel=i`，取消用 Esc 或點別張卡），照 10/18 檢討教訓。
- **驗證**：新增 `factory/tests/verify_meowhole.py`（記憶體注入掛鉤、60Hz 同步模擬，不動 repo 檔）。修後 12 項全 ✅：王慢走時第 11 波在通關後 6 秒才開（victoryAt 376.4／t11 382.4）、第 10 波未清按提早開波不跳波、提早清完 6 秒接無限；三種怪在 waves.groups 且第 1～10 波真的生成；Echo 情境（兩座打不到的塔）最長無操作空窗 25.8s→0.5s、一有錢就蓋廢塔 25.8s→0.5s、錢全升級廢塔 13.4s→0s、機器人正常玩四圖 8s；標題頁規則一句；照開局提示點卡＋點閃爍格第一座塔蓋成功；0 JS 例外。舊版同腳本對照：(a)(b)(c)(d) 全 ❌。難度：機器人四圖新舊都通關（新版第四圖掉 2 命，舊版 0），沒有變簡單。產線品管 `python -m v3.qa games/2026-10-17-001/index.html`：✅ 通過。
- `python factory/tests/test_v3.py`：143 條全綠（10b 節新增 6 條 10/24 檢查，乾跑 `main()` 改成 10/17、10/24 各跑一次）。第一次跑有一條 3D 煙霧測試報 WebGL shader 錯誤，原封重跑即過＝headless 軟體繪圖偶發，與本輪無關。
- 乾跑證據（排程同一個 `pythoncore-3.14-64` 直譯器、讀正式 `skeleton_lock.json`、日期凍在 10/24、抓榜／解構換成會炸的假函式）：log「🔒 骨架鎖定：經營＋班次（2026-10-24 起 2 天內有效）→ 不抓榜、不解構，直接進企劃書」，rc=0、decon `origin=locked`、`locked_genre=經營`、publish=True、trial=False；10/23、10/27 不鎖，10/26 仍鎖；目前沒有續跑指標。
- 沒動：`factory/knowledge/learnings.md` 的未提交 4 行是 10/18 18:00 檢討會排程寫的，本輪沒碰也沒 commit；`factory/runs/v3-20261017-020001/` 的內容包快照（gitignore）沒同步，之後若對這款跑 `--regen`／`--polish` 要留意它還是舊波次。
- ⚠️ 本輪只做本機 commit、沒 push。但 `publish_site.publish()` 會 `git push origin main`，所以下一次自動部署（每日留言排程或 10/24 週更）會把這輪 commit 一起推上公開站——Boss 不想讓它上線的話要先講。

## 2026-10-14 早這輪（補驗；gateway job-20261014-091555-1254，initiator=grokbot，任務單 #slimecat-7d27c0f-retest）

- 只驗不改程式。排程 `run_factory.bat` 用的 `pythoncore-3.14-64`（Python 3.14.3）**本來就裝有 requests 2.33.1**，import 成功，沒有 pip 安裝。
- `python factory/tests/test_v3.py`（用同一個排程直譯器跑）：全部 ✅、「🎉 全部通過」、exit 0。
- 骨架鎖定乾跑探針（排程直譯器、不帶參數的 `main()`、讀正式 `skeleton_lock.json`、日期凍在 10/17；抓榜／解構換成會炸的假函式，生產線只記錄收到什麼不真跑，`clear_retry` 換成 no-op）：rc=0，log 出「🔒 骨架鎖定：塔防＋波次 → 不抓榜、不解構」，交給生產線的 decon `origin=locked`、`locked_genre=塔防`、publish=True、trial=False。另外實查：今天（10/14）鎖定不生效（正確）、目前沒有續跑指標（10/17 不會先去續跑舊 run）。
- 未追蹤的 `factory/knowledge/deconstructions/2026-10-13-Helix_Jump.*` 是 10/13 3D 試產點名解構的正常產物（見下節），這輪沒動。

## 2026-10-13 晚這輪（3D／three.js＋試產模式；詳見 DECISIONS.md 同日條目）

- Boss 拍板四題：three.js 放站內 `vendor/three/0.186.1/`、2D／3D 由企劃書依玩法判斷、**10/17 就生效**、先試產一款 3D 不上架。
- 改了：`v3/stages.py`（合約 `render`、企劃 prompt 判斷說明、`HARD_SPECS_3D`、`hard_specs_for()`、打磨 prompt 依 render）、`validate_game.py`（`open_game()` 虛擬網址 `http://localhost:47977`、擋對外請求）、`v3/qa.py`（改用 open_game）、`v3/pipeline.py`（`trial` 模式、`games.json` 記 render）、`make_game_v3.py`（`--render`、`--trial`）、`publish_site.py`（白名單加 `vendor/`）、`fix_game.py`（保留 importmap）、`.gitignore`（`trial/`）；新增 `vendor/three/0.186.1/`（three.module.js、three.core.js、LICENSE）與 `factory/tests/fixture_engine3d.html`（3D 樣本引擎）。
- 測試：`python factory/tests/test_v3.py` 離線 132 條全綠（新增 10c 節 19 條：render 正規化與強制、PLAN_SCHEMA、vendor 檔案、引擎／打磨／企劃 prompt 分流、白名單、品管真跑 3D 樣本、偷用 CDN 被抓、試產 main 與 pipeline 不碰 games.json）。手動品管：《喵沙橫流》（2D v3）照常通過、3D 樣本通過（r186、0 錯誤）。
- 3D 試產結果（run `v3-20261013-191820`）：《喵穿層連落》（Helix Jump 變形、render=3d、引擎 915 行、內容包 段型 10／爪印 15／貓抓柱 20／圖鑑貓 12），品管通過、Echo 評審 38/50（稽核合約 5、bug 3），打磨 patch 3 項採用；成品 `trial/v3-20261013-191820/index.html`（另有 play.png 遊戲中截圖），本機預覽 `http://localhost:3462/trial/v3-20261013-191820/`。實際 fps 60、同屏 23 mesh，three.js 兩檔 200 載入、0 console 錯誤。games.json／history／plans 都沒動，只多 Helix Jump 解構筆記（點名解構的正常產物）。
- 試產踩雷（已修，commit `c337d9f`）：第一次跑兩次引擎都被煙霧測試擋下（three.js 404）——引擎煙霧測試的 `factory/runs/<run>/engine_probe.html` 在站內但深一層，虛擬網址照真實位置掛讓 `../../vendor` 變 `/factory/vendor`。改成只有站內第二層（games／trial）才照真實位置掛，其他一律 `/games/_qa/`（`validate_game.qa_url_path`）；回歸測試 135 條全綠（新增 3 條含 runs/ 深一層實跑）。引擎本身沒問題，第 2 次交稿重測通過後登記為完成（run.json `salvaged` 註記）、從內容包續跑，沒有重付引擎。
- 小問題（交評審、未處理）：圖鑑貓 `unlock` 欄位寫的是解鎖條件關鍵字（start／score…），跨包引用檢查誤當成 towers id，警告放行；之後若 3D 款常見再調引用判斷。
- 下一步：Boss 試玩後決定上架與否——要上架目前沒有「試產轉正」指令，要另做（把 trial 成品搬進 games/、寫 games.json 條目、重建、部署＝對外，需 Boss 明講）。10/17 週更照常跑（骨架鎖定塔防，企劃書可自選 3D），看 `factory.log` 的合約 render 與品管結果。

## 2026-10-13 早這輪（骨架鎖定；詳見 DECISIONS.md 同日條目）

- Boss「選 A：10/17 鎖定塔防＋波次，允許寫入 SlimeCatArcade 改產線」（gateway job，initiator=grokbot）。新增 `factory/skeleton_lock.json`；`make_game_v3.py` 加 `active_skeleton_lock()`／`skeleton_decon()`，鎖定期間不抓榜不解構；`v3/stages.py` 合約 genre 強制＋企劃 prompt 標「骨架鎖定」。
- 測試：`python factory/tests/test_v3.py` 離線 113 條全綠（新增 10b 節 8 條，含乾跑 `main()`：fetch_trends／stage_deconstruct 被換成會炸的假函式仍 rc=0、交給生產線的 decon＝塔防）。沒有真跑生產線、沒有改排程、沒有 push。
- 下一步：10/17（六）02:00 週更跑完看 `factory.log` 有「🔒 骨架鎖定：塔防＋波次」而不是「📈 榜單 OK」，`games.json` 新款 genre＝塔防；10/18 檢討會看這款有沒有真的做成塔防。

## 2026-09-30 這輪（Echo 評審型號；詳見 DECISIONS.md 同日條目）

- Boss 拍板 Codex 工具預設改 `gpt-6.1-sol`、effort 不變，經 Echo handoff `2026-09-30-1824-echo-to-batnini-codex-default-model.md` 交辦。`v3/echo_review.py` 的 `PREFERRED_MODEL`／`FALLBACK_MODELS` 都改 `gpt-6.1-sol`，`ECHO_EFFORT` 維持 high、沙盒維持 read-only；不再留舊代型號當候選，跑不動就照舊 fail-open 回 sonnet。
- runner 用 Codex app 內建 codex，冒煙實測 0.159.2 跑 `gpt-6.1-sol` 回 OK（PATH 上的 0.157.0 回 400，runner 不會挑它）。
- 測試：`python factory/tests/test_v3.py` 離線 105 條全綠（新增 5b 節 4 條）；沒有真委派 Echo、沒有生遊戲。
- 沒有常駐程序：下一場週更（10/3（六）02:00）就會用新型號評審；跑完看 `factory.log` 的評審行是 `model=gpt-6.1-sol`、產出的 reviewer 是 `echo:gpt-6.1-sol`，若寫 `claude:sonnet` 就是 Echo 不可用、翻委派記錄查原因。

## 2026-09-25 這輪（prompt 稽核；詳見 DECISIONS.md 同日條目）

- 批 3（Session A，`f81568a`）：H7、M10～M13、M19、M20 產線 prompt 對齊新模型。
- H8（Session B）：企劃書合約／內容包／v3 評審 Claude 退路／v2.2 自評／rescue_meta／每日留言分流改走 `make_game.run_claude_json`（`--json-schema`）。Echo 評審路徑不變。
- 測試：`python factory/tests/test_v3.py` 101 條全綠（⚠️ 要用 python 直接跑，pytest 會因檔尾 `sys.exit` 報 INTERNALERROR）；六處真 CLI 探針全過；企劃書 A/B 文筆沒變差（兩份原文在 Batnini 該 session 的 scratchpad，數字見 DECISIONS）。
- 下一步：9/26（六）02:00 週更是整條產線第一次用新版；跑完看 `factory.log` 企劃書／內容包有沒有「沒交結構化結果」或 400 錯誤。不要手動生遊戲。

## 2026-09-23 這輪（詳見 DECISIONS.md 同日條目）

- **子 Claude 沙盒**：`make_game.run_claude`（全工廠唯一 `claude -p` 入口）的 `--disallowedTools` 黑名單換成 `SANDBOX_ARGS=["--restricted","--tools",""]`，防玩家留言／榜單簡介做提示注入；另補 `--append-system-prompt LANG_GUARD`（`--restricted` 會關掉原本注入繁中的全域 hook）。其餘旗標與 env 不變。
- 測試：`tests/test_v3.py` 離線全綠（新增 9 條沙盒／解析回歸）；haiku 真跑事件流、預算保險絲、注入探針都過。`--live` 探針第一次失敗＝haiku 合約寫了 `array[string]` 型別被 `validate_contract` 擋（跟沙盒無關，傳輸與解析正常）；**第二次重跑全過**（企劃書《喵港捍衛》4 包合約＋內容包 4 筆，兩次共 $0.33）。
- 沒有常駐程序：三個排程都是每次新開 python，自動吃新碼——最先跑到的是 9/24 11:30 每日留言，其次 9/26（六）02:00 週更、9/27（日）18:00 檢討會；看 `factory.log` 有沒有 claude -p 失敗即可。

## 2026-09-17 這輪（詳見 DECISIONS.md 同日條目）

- **9/12 停產根因**：`ref_fields` 把合約 headlines.text 說明裡的 `{stage}` 佔位符當成「引用 stages 包」→ 驗證器拿整句中文頭條比對 id，兩次必敗、整場中止（燒 $7.43）。修法＝比對前剝掉 `{…}` 佔位符＋第二道保險（欄位 examples 不是英文 id 格式就不當引用）。
- **模型分工**（Boss 拍板）：引擎 fable→**opus** high、打磨 fable→**opus** high（Batnini 自決，跟引擎一致）、解構 opus→**fable**、內容包**維持 sonnet**、Echo 評審固定 **gpt-5.6-sol** high（config 現役降為第二順位）。`BUDGET_USD` 引擎 9→5、打磨 4→2.5。同 token 下每場約省 $1.2。**10:42 追加**：v2 舊線 `MODEL_BUILD` fable→**opus**（＝`run_claude` 預設，連帶 v2.2 單線／`fix_game`／`daily_feedback`／`weekly_review`／`original_mode` 一起降）。
- **內容包跨包引用改 fail-open**：重試一次後仍不合格＝警告放行，寫進 `content_warnings.json` 並併入 `qa_info["warnings"]` 交評審；解析不出 JSON／schema 不合仍致命。
- 測試：`tests/test_v3.py` 全綠（新增 5 條回歸）。下次週更（9/19 02:00）跑完要看 `factory.log` 確認引擎那段是 opus、評審 reviewer 是 sol。
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

- Echo 評審讀 60k 字元原始碼約 2～3 分鐘，9/30 起型號是 gpt-6.1-sol（9/17～9/29 的場次是 gpt-5.6-sol，對帳時別混在一起比）；Echo 若整個不可用→sonnet（分數口徑會不同，對帳時分開看 `reviewer`）。
- 引擎 640 行卻 60k 字元（長行）：patch 的 SEARCH 段要對到整行，模型改長行容易對不上；再打磨若失敗會維持現版。
- 品管壓力測試只保證「不炸＋內容載入」，不保證可通關；可通關性靠 Echo 稽核＋玩家留言。
- `factory/runs/` gitignored：本機才有完整落檔；企劃書副本在 `knowledge/plans/`（公開 repo）。
