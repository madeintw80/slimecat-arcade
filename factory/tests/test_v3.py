# -*- coding: utf-8 -*-
"""v3 生產線回歸測試（離線為主；加 --live 會用 haiku 真跑一次企劃書＋內容包探針，約 $0.05）。

    python factory/tests/test_v3.py           # 離線：合約解析／內容包驗證／組裝／patch／品管壓力測試／續跑指標
    python factory/tests/test_v3.py --live    # 加真呼叫探針（驗 parser 對真實模型輸出有效）
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY))
import make_game as mg                         # noqa: E402
import decon_now                               # noqa: E402
import make_game_v3                            # noqa: E402
from v3 import stages, patch, qa, pipeline     # noqa: E402
from v3.run import Run                         # noqa: E402
import v3.run as runmod                        # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("✅" if cond else "❌"), name, info)
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="slimecat_v3_test_"))

# ---------------------------------------------------------------- 1. 企劃書＋合約解析
SAMPLE_PLAN = """先講幾句廢話。
# 企劃書：《潮汐倉庫》
## 一句話企劃與核心樂趣
守住碼頭。
## 核心迴圈（一圈幾秒？）
撈→蓋→守。
## 內容包規格
關卡 12 個。
## 難度曲線與壓力源
第 3 分鐘鯊魚。
## 驗收清單
- 前 15 秒不會死
===CONTRACT===
```json
{"title": "潮汐倉庫", "emoji": "🌊", "genre": "塔防 混合", "desc": "守住碼頭的撈魚塔防",
 "session_minutes": [4, 12],
 "modules": [{"id": "spawner", "role": "生怪", "state": "wave", "api": "next()"}],
 "content_packs": [
   {"key": "Levels", "label": "關卡", "count": 40,
    "item_schema": {"id": "string｜唯一 id", "name": "string｜名", "waves": "int｜1-30", "boss": "bool｜頭目"},
    "rules": ["前 3 關不會死"],
    "examples": [{"id": "l01", "name": "晨霧碼頭", "waves": 3, "boss": false}]},
   {"key": "upgrades", "label": "升級", "count": 8,
    "item_schema": {"id": "string｜id", "cost": "int｜10-500"},
    "examples": [{"id": "u1", "cost": 10}]}
 ],
 "progress": {"storage_key": "sc_tide_v1", "saves": "解鎖關卡"},
 "acceptance": ["前 15 秒不會死", "第 3 分鐘出現鯊魚"],
 "engine_lines_budget": 5000}
```
===END===
"""
doc, raw = stages.parse_plan(SAMPLE_PLAN)
check("parse_plan 企劃書從 # 企劃書 開始", doc.startswith("# 企劃書：《潮汐倉庫》"))
check("parse_plan 合約解析", raw.get("title") == "潮汐倉庫")
c = stages.validate_contract(raw, {"title": "x", "genre": "益智"})
check("validate_contract key 轉小寫", c["content_packs"][0]["key"] == "levels")
check("validate_contract count 夾上限", c["content_packs"][0]["count"] == stages.CAPS["items"], str(c["content_packs"][0]["count"]))
check("validate_contract session 夾上限", c["session_minutes"] == [4, 10], str(c["session_minutes"]))
check("validate_contract 引擎行數夾上限", c["engine_lines_budget"] == stages.CAPS["engine_lines"])
check("validate_contract genre 正規化", c["genre"] == "塔防")
check("validate_contract storage_key", c["progress"]["storage_key"] == "sc_tide_v1")
try:
    stages.validate_contract({"title": "x", "content_packs": [{"key": "a", "item_schema": {"id": "string"}, "examples": []}]}, {})
    check("validate_contract 缺 examples 應 raise", False)
except ValueError as e:
    check("validate_contract 缺 examples 應 raise", True, str(e)[:50])
try:
    stages.validate_contract({"title": "x", "content_packs": [{"key": "a", "item_schema": {"id": "string｜x", "n": "float64｜x"}, "examples": [{"id": "1", "n": 1}]}]}, {})
    check("validate_contract 型別不合法應 raise", False)
except ValueError as e:
    check("validate_contract 型別不合法應 raise", True, str(e)[:50])
try:
    stages.parse_plan("沒有分隔線的輸出")
    check("parse_plan 缺分隔線應 raise", False)
except ValueError:
    check("parse_plan 缺分隔線應 raise", True)
# 外層 JSON 有尾逗號＋行尾註解＋鍵名別名：以前會掉到內層 modules[0]、變成「沒有內容包」
DIRTY = SAMPLE_PLAN.replace('```json\n', '').replace('\n```', '').replace(
    '"modules": [{"id": "spawner", "role": "生怪", "state": "wave", "api": "next()"}],',
    '"modules": [{"id": "spawner", "role": "生怪", "state": "wave", "api": "next()"},],\n // 註解行\n').replace(
    '"content_packs": [', '"contentPacks": [').replace('"item_schema"', '"itemSchema"')
doc_d, raw_d = stages.parse_plan(DIRTY)
check("parse_plan 尾逗號＋註解＋別名鍵仍解析", raw_d.get("content_packs") and "item_schema" in raw_d["content_packs"][0], str(list(raw_d.keys()))[:80])
try:
    stages.parse_json_block('{"a": [1, 2}')
    check("parse_json_block 壞 JSON 應 raise 不退內層", False)
except ValueError as e:
    check("parse_json_block 壞 JSON 應 raise 不退內層", True, str(e)[:50])
excerpt = stages.plan_excerpt(doc)
check("plan_excerpt 抓到核心迴圈＋內容包＋難度", "撈→蓋→守" in excerpt and "關卡 12 個" in excerpt and "鯊魚" in excerpt)

# ---------------------------------------------------------------- 2. 內容包驗證
pack = c["content_packs"][0]
pack["count"] = 3
good = [{"id": "l01", "name": "a", "waves": 3, "boss": False},
        {"id": "l02", "name": "b", "waves": 4.0, "boss": True},
        {"id": "l03", "name": "c", "waves": 5, "boss": False},
        {"id": "l04", "name": "d", "waves": 6, "boss": False}]
items = stages.validate_pack(good, pack)
check("validate_pack 多的截掉", len(items) == 3)
check("validate_pack 4.0 轉 int", items[1]["waves"] == 4 and isinstance(items[1]["waves"], int))
for bad, label in (([{"id": "l01", "name": "a", "waves": "3", "boss": False}] * 3, "型別錯"),
                   ([{"id": "l01", "name": "a", "waves": 3}] * 3, "缺欄位"),
                   ([{"id": "same", "name": "a", "waves": 3, "boss": False}] * 3, "id 重複"),
                   ([{"id": "l01", "name": "a", "waves": 3, "boss": False}], "筆數不足")):
    try:
        stages.validate_pack(bad, pack)
        check(f"validate_pack {label} 應 raise", False)
    except ValueError as e:
        check(f"validate_pack {label} 應 raise", True, str(e)[:60])

# ---------------------------------------------------------------- 2b. 跨包引用
cref = {"content_packs": [
    {"key": "objects", "label": "圖鑑", "count": 3, "item_schema": {"id": "string｜唯一 id", "size": "int｜1-99"},
     "examples": [{"id": "crumb", "size": 1}]},
    {"key": "scenes", "label": "房間", "count": 2,
     "item_schema": {"id": "string｜唯一", "spawn": "array｜[{obj:string 物件 id, n:int}]，obj 必存在於 objects",
                     "boss": "string｜tier 5 物件 id", "palette": "object｜{bg:hex}"},
     "examples": [{"id": "r1", "spawn": [{"obj": "crumb", "n": 3}], "boss": "crumb", "palette": {"bg": "#000"}}]},
    {"key": "perks", "label": "卡", "count": 1, "item_schema": {"id": "string｜id", "desc": "string｜說明"}, "examples": [{"id": "p1", "desc": "x"}]},
]}
refs = stages.ref_fields(cref["content_packs"][1], cref)
check("ref_fields 說明提到 objects＋example 對得上 id", refs == {"spawn": "objects", "boss": "objects"}, str(refs))
check("ref_fields 型別 object 不誤判成 objects", "palette" not in refs)
check("ref_fields 無引用回空", stages.ref_fields(cref["content_packs"][0], cref) == {})
check("order_packs 被引用的先生", [p["key"] for p in stages.order_packs(cref)] == ["objects", "perks", "scenes"])
bad = stages.find_bad_refs([{"id": "r1", "spawn": [{"obj": "crumb", "n": 1}, {"obj": "mug", "n": 2}], "boss": "landlord"}],
                           refs, {"objects": {"crumb", "sock"}})
check("find_bad_refs 抓到 mug／landlord", len(bad) == 2 and "mug" in bad[0] and "landlord" in bad[1], str(bad))
check("find_bad_refs 乾淨回空", stages.find_bad_refs([{"id": "r1", "spawn": [{"obj": "sock", "n": 1}], "boss": "crumb"}], refs, {"objects": {"crumb", "sock"}}) == [])
prompt_c = stages.build_content_prompt(cref["content_packs"][1], "# 企劃書", {"title": "t", "content_packs": cref["content_packs"]}, "", available={"objects": {"crumb", "sock"}})
check("build_content_prompt 帶可引用 id 清單", "只能用這些：crumb, sock" in prompt_c)

# ---------------------------------------------------------------- 3. 組裝
ENGINE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>t</title>
<!--CONTENT-NOTES
levels: waves 1-30, boss bool
-->
<style>canvas{touch-action:none}</style></head><body>
<a href="../../index.html">← 回遊戲區</a>
<canvas id="c" width="400" height="600"></canvas>
<script id="sc-content">window.SC_CONTENT = {"levels":[{"id":"l01","name":"a","waves":3}]};</script>
<script>
const cv=document.getElementById('c'),ctx=cv.getContext('2d');let scene='title',score=0,t0=0;
function start(){scene='play';t0=performance.now();}
window.SC_HOOKS={start,snapshot:()=>({scene,score,level:0,elapsed:Math.round(performance.now()-t0)})};
cv.addEventListener('pointerdown',()=>{if(scene==='title')start();else score++;});
addEventListener('keydown',()=>{score++});
function loop(){ctx.fillStyle='#123';ctx.fillRect(0,0,400,600);ctx.fillStyle='#fff';
ctx.fillText(scene+' '+score+' '+window.SC_CONTENT.levels.length,20,40);
__HOOK__
requestAnimationFrame(loop);}loop();
</script></body></html>
"""
engine_ok = ENGINE.replace("__HOOK__", "")
content = {"levels": [{"id": "l01", "name": "含 </script> 與 <!-- 的名字", "waves": 3}] * 2,
           "upgrades": [{"id": "u1", "cost": 10}]}
assembled = stages.assemble(engine_ok, content)
check("assemble 換掉 examples 區塊", assembled.count('id="sc-content"') == 1 and '"upgrades"' in assembled)
check("assemble 跳脫 </script", "<\\/script>" in assembled and "<!--" not in assembled.split('id="sc-content"')[1].split("</script>")[0])
no_block = engine_ok.replace('<script id="sc-content">window.SC_CONTENT = {"levels":[{"id":"l01","name":"a","waves":3}]};</script>\n', "")
assembled2 = stages.assemble(no_block, content)
check("assemble 沒區塊就插在第一個 script 前", assembled2.find('id="sc-content"') < assembled2.find("const cv"))
body, notes = stages.parse_engine("```html\n" + engine_ok + "\n```")
check("parse_engine 去 fence＋抓 CONTENT-NOTES", body.startswith("<!DOCTYPE") and "waves 1-30" in notes)
ex = stages.examples_content(c)
check("examples_content", set(ex) == {"levels", "upgrades"})

# ---------------------------------------------------------------- 4. patch
src = "line1\n  line2 with space  \nline3\nline4\n"
p_exact = "<<<<<<< SEARCH\nline3\nline4\n=======\nline3\nline4b\n>>>>>>> REPLACE\n"
new, n = patch.apply_text(src, p_exact)
check("patch 精確套用", n == 1 and "line4b" in new and "line1" in new)
p_norm = "<<<<<<< SEARCH\nline1\n  line2 with space\n=======\nL1\n>>>>>>> REPLACE"
new, n = patch.apply_text(src, p_norm)
check("patch 去尾端空白比對", n == 1 and new.startswith("L1\nline3"), repr(new[:20]))
try:
    patch.apply_text(src, "<<<<<<< SEARCH\nnope\n=======\nx\n>>>>>>> REPLACE")
    check("patch 找不到應 raise", False)
except patch.PatchError as e:
    check("patch 找不到應 raise", True, str(e)[:40])
new, n = patch.apply_text(src, "NOPATCH: 沒問題")
check("patch NOPATCH 回 None", new is None and n == 0)
try:
    patch.apply_text(src, "廢話而已")
    check("patch 無區塊應 raise", False)
except patch.PatchError:
    check("patch 無區塊應 raise", True)
multi = ("```\n<<<<<<< SEARCH\nline1\n=======\nA\n>>>>>>> REPLACE\n\n<<<<<<< SEARCH\nline4\n=======\nD\n>>>>>>> REPLACE\n```")
new, n = patch.apply_text(src, multi)
check("patch 多區塊＋fence", n == 2 and new.startswith("A\n") and "D\n" in new)

# ---------------------------------------------------------------- 5. 評審解析
rev_text = ("檢查了。\nREVIEW: {\"scores\":{\"onboarding\":7.5,\"juice\":8,\"goal\":6,\"difficulty\":7,\"one_more\":6},"
            "\"total\":99,\"fixes\":[\"修 A\",\"修 B\"],\"verdict\":\"不錯\",\"howto\":\"點\",\"design_choices\":[\"x\"],"
            "\"pressure_3min\":\"鯊魚\",\"scale_up\":{\"worth\":true,\"why\":\"y\"},"
            "\"audit\":{\"contract_issues\":[\"升級沒讀\"],\"bugs\":[]}}\n")
r = stages.normalize_review(stages.parse_review(rev_text))
check("parse_review + normalize 半分四捨五入＋自己加總", r["scores"]["onboarding"] == 8 and r["total"] == 35, str(r["total"]))
check("normalize_review audit", r["audit"]["contract_issues"] == ["升級沒讀"] and r["audit"]["bugs"] == [])
check("parse_review 沒標記也撈得到", stages.parse_review('{"scores":{"onboarding":5,"juice":5,"goal":5,"difficulty":5,"one_more":5}}') is not None)
check("parse_review 撈不到回 None", stages.parse_review("nothing") is None)
r["total"] = 30
check("_polish_issues bug 優先", pipeline._polish_issues({"audit": {"bugs": ["b1", "b2", "b3"], "contract_issues": ["c1"]}, "total": 45, "fixes": ["f"]}) == ["[bug] b1", "[bug] b2", "[合約缺陷] c1"])
check("_polish_issues 低分修第一條", pipeline._polish_issues({"audit": {}, "total": 30, "fixes": ["f1", "f2"]}) == ["[評審改進點] f1"])
check("_polish_issues 達標不修", pipeline._polish_issues({"audit": {}, "total": 45, "fixes": ["f1"]}) == [])

# ---------------------------------------------------------------- 6. 榜單合併＋解構筆記存讀
trends = {"source": "appstore-tw-legacy", "games": [{"rank": 1, "name": "A", "artist": "x", "summary": "s"}],
          "steam": {"games": [{"rank": 1, "name": "B", "list": "熱銷", "genres": ["動作"], "summary": "ss"}]}}
chart = mg.trend_chart(trends)
check("trend_chart 含兩份榜", "【App Store" in chart and "【Steam" in chart and "S1. [熱銷] B｜動作" in chart)
orig_dir = mg.DECON_DIR
mg.DECON_DIR = TMP / "decon"
try:
    note = mg.save_decon({"source": "測試/原作", "title": "變形", "genre": "塔防", "origin": "steam", "doc": "# 解構：測試/原作\n## 核心迴圈\n一圈 5 秒\n## 變形版\n企劃"})
    check("save_decon 存 md＋json 側檔", note.exists() and note.with_suffix(".json").exists(), note.name)
    d = make_game_v3.load_decon_file(note)
    check("load_decon_file 用側檔", d["source"] == "測試/原作" and d["origin"] == "steam" and d["genre"] == "塔防")
    note.with_suffix(".json").unlink()
    d2 = make_game_v3.load_decon_file(note)
    check("load_decon_file 沒側檔從標題推", d2["source"] == "測試/原作" and d2["origin"] == "note")
    s = decon_now.summarize(d, note)
    check("decon_now.summarize", "🔁 核心迴圈：一圈 5 秒" in s and "--decon" in s)
finally:
    mg.DECON_DIR = orig_dir

# ---------------------------------------------------------------- 7. Run 狀態＋續跑指標
orig_runs, orig_ptr = runmod.RUNS_DIR, runmod.RESUME_PTR
runmod.RUNS_DIR, runmod.RESUME_PTR = TMP / "runs", TMP / "v3_resume.json"
try:
    run = Run()
    run.write_json("decon.json", {"a": 1})
    run.mark("plan", model="x")
    run2 = Run(run.id)
    check("Run 狀態落檔＋重讀", run2.done("plan") and run2.read_json("decon.json") == {"a": 1})
    run2.unmark("plan")
    check("Run unmark", not Run(run.id).done("plan"))
    check("pending_resume 一開始沒有", Run.pending_resume() == "")
    run.set_resume_pointer()
    check("pending_resume 指到這輪", Run.pending_resume() == run.id)
    Run.clear_resume_pointer()
    check("clear_resume_pointer", Run.pending_resume() == "")
finally:
    runmod.RUNS_DIR, runmod.RESUME_PTR = orig_runs, orig_ptr

# ---------------------------------------------------------------- 8. 品管壓力測試（Playwright）
good_html = TMP / "good.html"
good_html.write_text(stages.assemble(engine_ok, content), encoding="utf-8")
errs, info = qa.stress(good_html, secs=3)
check("stress 好引擎通過", not errs, str(errs)[:120])
check("stress 讀到 SC_CONTENT 數量", info.get("content") == {"levels": 2, "upgrades": 1}, str(info.get("content")))
check("stress 用到 hooks＋snapshot", info.get("hooks") and isinstance(info.get("snapshot"), dict) and info["snapshot"].get("scene") == "play", str(info.get("snapshot"))[:80])
bad_html = TMP / "bad.html"
bad_html.write_text(ENGINE.replace("__HOOK__", "if(scene==='play'&&performance.now()-t0>800)throw new Error('boom-after-start');"), encoding="utf-8")
errs, info = qa.stress(bad_html, secs=3)
check("stress 開始後才炸的引擎被抓到", any("boom-after-start" in e for e in errs), str(errs)[:120])
nocontent = TMP / "nocontent.html"
nocontent.write_text(engine_ok.replace("window.SC_CONTENT", "window.XX"), encoding="utf-8")
errs, info = qa.stress(nocontent, secs=2)
check("stress 沒 SC_CONTENT 報錯", any("SC_CONTENT" in e for e in errs))

# ---------------------------------------------------------------- 9. 成品檔標頭
final = pipeline._final_html("<!DOCTYPE html><html><body><canvas></canvas></body></html>", c, {"source": "原作"})
meta, html = mg.extract(final)
check("_final_html GAMEMETA 可被 extract 讀回", meta["title"] == "潮汐倉庫" and meta["inspiration"] == "原作" and "stats.js" in html)

# ---------------------------------------------------------------- 10. live 探針（可選）
if "--live" in sys.argv:
    print("── live：haiku 企劃書探針 ──")
    stages.MODEL_PLAN, stages.EFFORT_PLAN = "haiku", ""
    stages.MODEL_CONTENT = "haiku"
    decon = {"source": "測試原作", "title": "測試變形", "genre": "塔防", "origin": "appstore",
             "doc": "# 解構：測試原作\n## 核心迴圈\n撈漂流物、蓋木筏、擋鯊魚，一圈 5 秒。\n## 上癮機制\n損失趨避。\n## 我們的變形版一句話企劃\n碼頭塔防。"}
    try:
        plan_doc, contract, _raw = stages.stage_plan(decon, [])
        check("live 企劃書解析＋合約驗證", bool(plan_doc) and contract["content_packs"], f"{contract['title']} packs={[p['key'] for p in contract['content_packs']]}")
        pack = contract["content_packs"][0]
        pack["count"] = min(pack["count"], 4)
        items = stages.stage_content(pack, plan_doc, contract, "")
        check("live 內容包生成＋驗證", len(items) >= 1, f"{len(items)} 筆 keys={list(items[0].keys())}")
    except Exception as e:
        check("live 探針", False, str(e)[:200])

shutil.rmtree(TMP, ignore_errors=True)
print("\n" + ("❌ 失敗：" + "、".join(fails) if fails else "🎉 全部通過"))
sys.exit(1 if fails else 0)
