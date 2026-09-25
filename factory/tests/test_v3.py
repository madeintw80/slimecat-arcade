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

# ---------------------------------------------------------------- 1. 企劃書＋合約（結構化交稿，2026-09-25 H8）
SAMPLE_OUT = {
    "plan_markdown": """先講幾句廢話。
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
""",
    "contract": {"title": "潮汐倉庫", "emoji": "🌊", "genre": "塔防 混合", "desc": "守住碼頭的撈魚塔防",
                 "session_minutes": [4, 12],
                 "modules": [{"id": "spawner", "role": "生怪", "state": "wave", "api": "next()"}],
                 "content_packs": [
                     {"key": "Levels", "label": "關卡", "count": 40,
                      "item_schema": {"id": "string｜唯一 id", "name": "string｜名", "waves": "int｜1-30", "boss": "bool｜頭目"},
                      "rules": ["前 3 關不會死"],
                      "examples": [{"id": "l01", "name": "晨霧碼頭", "waves": 3, "boss": False}]},
                     {"key": "upgrades", "label": "升級", "count": 8,
                      "item_schema": {"id": "string｜id", "cost": "int｜10-500"},
                      "examples": [{"id": "u1", "cost": 10}]}],
                 "progress": {"storage_key": "sc_tide_v1", "saves": "解鎖關卡"},
                 "acceptance": ["前 15 秒不會死", "第 3 分鐘出現鯊魚"],
                 "engine_lines_budget": 5000},
}
doc, raw = stages.split_plan(SAMPLE_OUT)
check("split_plan 企劃書從 # 企劃書 開始", doc.startswith("# 企劃書：《潮汐倉庫》"))
check("split_plan 合約取出", raw.get("title") == "潮汐倉庫")
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
for bad_out, label in (({"plan_markdown": "", "contract": {}}, "企劃書空白"),
                       ({"plan_markdown": "# 企劃書：x", "contract": "不是物件"}, "合約不是物件")):
    try:
        stages.split_plan(bad_out)
        check(f"split_plan {label} 應 raise", False)
    except ValueError:
        check(f"split_plan {label} 應 raise", True)
ps = stages.PLAN_SCHEMA["properties"]["contract"]
check("PLAN_SCHEMA genre＝類型清單 enum", ps["properties"]["genre"]["enum"] == list(mg.GENRES))
check("PLAN_SCHEMA 內容包 key 用同一條 regex", ps["properties"]["content_packs"]["items"]["properties"]["key"]["pattern"] == stages.PACK_KEY_RE.pattern)
check("PLAN_SCHEMA 合約欄位全必填", set(ps["required"]) == set(ps["properties"]))
# stage_plan 走 call_json：交稿 JSON 原文當 raw 回傳（pipeline 存 plan_raw.txt）
_saved_cj = stages.call_json
_seen_plan = {}
stages.call_json = lambda prompt, timeout, model, effort, stage, schema: (_seen_plan.update(prompt=prompt, schema=schema) or SAMPLE_OUT)
try:
    p_doc, p_c, p_raw = stages.stage_plan({"title": "x", "genre": "益智", "doc": "解構"}, [])
    check("stage_plan 用 PLAN_SCHEMA", _seen_plan["schema"] is stages.PLAN_SCHEMA)
    check("stage_plan prompt 不再要 ===CONTRACT=== 分隔線", "===CONTRACT===" not in _seen_plan["prompt"] and "plan_markdown" in _seen_plan["prompt"])
    check("stage_plan 回企劃書＋驗過的合約＋JSON 原文", p_doc.startswith("# 企劃書") and p_c["genre"] == "塔防" and json.loads(p_raw)["contract"]["title"] == "潮汐倉庫")
finally:
    stages.call_json = _saved_cj
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

# 2026-09-12 停產事故回歸：文字模板的 {佔位符} 與中文文案欄位不可被當成跨包引用
ctpl = {"content_packs": [
    {"key": "stages", "label": "季度", "count": 2, "item_schema": {"id": "string｜唯一英文 id", "name": "string｜季度名稱"},
     "examples": [{"id": "s1", "name": "實習日"}]},
    {"key": "headlines", "label": "頭條圖鑑", "count": 2,
     "item_schema": {"id": "string｜唯一英文 id",
                     "text": "string｜頭條模板，可用 {mult} {stage} {drivers} 佔位",
                     "hint": "string｜未解鎖時顯示的提示"},
     "examples": [{"id": "hl_calm", "text": "喵車今日車資 {mult} 倍，乘客表示：還行啦。", "hint": "平穩派單就能看到"}]},
]}
refs_tpl = stages.ref_fields(ctpl["content_packs"][1], ctpl)
check("ref_fields {stage} 佔位符不算引用 stages", refs_tpl == {}, str(refs_tpl))
check("find_bad_refs 不會拿中文文案去比 id",
      stages.find_bad_refs(ctpl["content_packs"][1]["examples"], refs_tpl, {"stages": {"s1"}}) == [])
# 第二道保險：就算說明真的寫了別包的名字，examples 擺明是中文文案就不當引用
ctpl2 = json.loads(json.dumps(ctpl))
ctpl2["content_packs"][1]["item_schema"]["text"] = "string｜依 stages 顯示的頭條文字"
check("ref_fields examples 不是 id 格式就不當引用", stages.ref_fields(ctpl2["content_packs"][1], ctpl2) == {},
      str(stages.ref_fields(ctpl2["content_packs"][1], ctpl2)))

# 2026-09-17 Boss 拍板：跨包引用不過＝重試一次後警告放行；解析／schema 不過仍然致命
_saved_call, _outs, _schemas = stages.call_json, [], []
stages.call_json = lambda prompt, timeout, model, effort, stage, schema: (_schemas.append(schema) or _outs.pop(0))
try:
    scenes = cref["content_packs"][1]
    bad_json = {"items": [
        {"id": "r1", "spawn": [{"obj": "mug", "n": 1}], "boss": "crumb", "palette": {"bg": "#000"}},
        {"id": "r2", "spawn": [{"obj": "sock", "n": 1}], "boss": "crumb", "palette": {"bg": "#111"}},
    ]}
    _outs[:] = [bad_json, bad_json]
    sink = []
    got = stages.stage_content(scenes, "# 企劃書", {"title": "t", "content_packs": cref["content_packs"]},
                               "", {"objects": {"crumb", "sock"}}, warn_sink=sink)
    check("引用不過重試一次後放行出廠", len(got) == 2 and len(_outs) == 0, f"items={len(got)}")
    check("放行有寫進警告清單給評審", len(sink) == 1 and "mug" in sink[0], str(sink))
    sch = _schemas[0]["properties"]["items"]
    check("content_schema 由 item_schema 產生（型別＋全必填＋筆數下限）",
          sch["items"]["properties"]["spawn"] == {"type": "array"} and sch["items"]["properties"]["palette"] == {"type": "object"}
          and set(sch["items"]["required"]) == {"id", "spawn", "boss", "palette"} and sch["minItems"] == 1, str(sch)[:120])
    check("content_schema int→integer、bool→boolean",
          stages.content_schema(pack)["properties"]["items"]["items"]["properties"]["waves"] == {"type": "integer"}
          and stages.content_schema(pack)["properties"]["items"]["items"]["properties"]["boss"] == {"type": "boolean"})

    zh_pack = {"key": "zh", "count": 2, "item_schema": {"id": "string｜id", "名稱": "string｜中文欄位名"}}
    zs = stages.content_schema(zh_pack)["properties"]["items"]["items"]
    check("content_schema 非英數欄位名不放進 schema（API 會 400）", list(zs["properties"]) == ["id"] and zs["required"] == ["id"], str(zs))

    _outs[:] = [{"items": "不是陣列"}, {}]
    try:
        stages.stage_content(scenes, "# 企劃書", {"title": "t", "content_packs": cref["content_packs"]},
                             "", {"objects": {"crumb", "sock"}})
        check("items 不是陣列仍應 raise", False)
    except ValueError as e:
        check("items 不是陣列仍應 raise", True, str(e)[:50])
finally:
    stages.call_json = _saved_call

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
# Claude 退路（Echo 不可用時）走 --json-schema：直接吃結構化物件，不再找 REVIEW: 標記
_saved_cj, _seen_rev = stages.call_json, {}
stages.call_json = lambda prompt, timeout, model, effort, stage, schema: (
    _seen_rev.update(prompt=prompt, schema=schema) or stages.parse_review(rev_text))
try:
    rv = stages.stage_critic("# 企劃書", c, "<html></html>")
    check("stage_critic 用 REVIEW_SCHEMA（含 audit）", _seen_rev["schema"] is stages.REVIEW_SCHEMA and "audit" in stages.REVIEW_SCHEMA["required"])
    check("stage_critic prompt 不再要 REVIEW: 單行", "REVIEW: {" not in _seen_rev["prompt"])
    check("stage_critic 結構化結果照常 normalize", rv and rv["total"] == 35 and rv["reviewer"] == f"claude:{stages.MODEL_CRITIC}")
    check("Echo 版 prompt 仍保留 REVIEW: 標記", "REVIEW: {" in stages.build_review_prompt("# 企劃書", c, "<html></html>", for_echo=True))
    check("CRITIC_SCHEMA 不含 audit（v2.2 自評）", "audit" not in mg.CRITIC_SCHEMA["properties"])
finally:
    stages.call_json = _saved_cj
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

# ---------------------------------------------------------------- 10. run_claude 沙盒旗標＋事件流解析（假 subprocess）
import subprocess                              # noqa: E402
from types import SimpleNamespace              # noqa: E402


def _fake_claude(lines, rc=0):
    """假的 subprocess.run：記下指令，回傳指定的 stream-json 行。"""
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return SimpleNamespace(returncode=rc, stdout="\n".join(json.dumps(x, ensure_ascii=False) for x in lines), stderr="")
    return run, seen


orig_run, orig_usage = mg.subprocess.run, mg.USAGE_LOG
mg.USAGE_LOG = TMP / "usage.jsonl"             # 別把測試用量寫進工廠的 usage.jsonl
try:
    ok_lines = [{"type": "system", "subtype": "init", "tools": []},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "前半"}]}},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "後半"}]}},
                {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1790157600}},
                {"type": "result", "is_error": False, "num_turns": 1, "total_cost_usd": 0.01,
                 "usage": {"input_tokens": 10, "output_tokens": 5}, "result": "後半"}]
    mg.subprocess.run, seen = _fake_claude(ok_lines)
    out = mg.run_claude("玩家留言", 60, model="opus", effort="high", stage="t-sandbox", max_budget_usd=2.5)
    cmd = seen["cmd"]
    check("run_claude 帶 --restricted --tools \"\"", cmd[cmd.index("--restricted"):cmd.index("--restricted") + 3] == ["--restricted", "--tools", ""])
    check("run_claude 不再用 --disallowedTools 黑名單", "--disallowedTools" not in cmd)
    check("空參數轉成字面 \"\"（Windows 命令列）", '--tools ""' in subprocess.list2cmdline(cmd))
    check("run_claude 補繁中 system prompt", cmd[cmd.index("--append-system-prompt") + 1] == mg.LANG_GUARD)
    check("run_claude 保留 stream-json／effort／budget／空 MCP",
          all(x in cmd for x in ("stream-json", "--verbose", "--strict-mcp-config")) and
          cmd[cmd.index("--effort") + 1] == "high" and cmd[cmd.index("--max-budget-usd") + 1] == "2.5")
    check("run_claude 保留輸出上限 env", seen["kw"]["env"].get("CLAUDE_CODE_MAX_OUTPUT_TOKENS") == str(mg.MAX_OUTPUT_TOKENS))
    check("多則文字塊照順序接起來", out == "前半\n後半", repr(out))
    check("usage 照記", mg.USAGE[-1]["stage"] == "t-sandbox" and mg.USAGE[-1]["out"] == 5)

    quota_lines = [{"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1790157600}},
                   {"type": "result", "is_error": True, "result": "You've hit your session limit · resets 3:40pm"}]
    mg.subprocess.run, _ = _fake_claude(quota_lines, rc=1)
    try:
        mg.run_claude("x", 60, stage="t-quota")
        check("撞額度 → QuotaError", False, "沒丟例外")
    except mg.QuotaError as e:
        check("撞額度 → QuotaError＋resetsAt", e.resets_at == 1790157600.0, str(e.resets_at))

    # ---- run_claude_json（--json-schema，2026-09-25 H8）
    so = {"title": "喵艙", "emoji": "🐱", "desc": "一句話"}
    json_lines = [{"type": "system", "subtype": "init", "tools": ["StructuredOutput"]},
                  {"type": "assistant", "message": {"content": [{"type": "text", "text": "讀完了。"}]}},
                  {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "StructuredOutput", "input": so}]}},
                  {"type": "result", "is_error": False, "num_turns": 2, "total_cost_usd": 0.02,
                   "usage": {"input_tokens": 10, "output_tokens": 7}, "result": "", "structured_output": so}]
    mg.subprocess.run, seen = _fake_claude(json_lines)
    got = mg.run_claude_json("x", 60, mg.RESCUE_META_SCHEMA, model="sonnet", stage="t-json")
    cmd = seen["cmd"]
    check("run_claude_json 回 structured_output", got == so, str(got))
    check("run_claude_json 帶 --json-schema（JSON 字串）", json.loads(cmd[cmd.index("--json-schema") + 1]) == mg.RESCUE_META_SCHEMA)
    check("run_claude_json 不設 --max-turns（寫 1 會 error_max_turns）", "--max-turns" not in cmd)
    check("run_claude_json 仍帶沙盒＋stream-json", "--restricted" in cmd and "stream-json" in cmd)
    mg.subprocess.run, seen_plain = _fake_claude(ok_lines)
    mg.run_claude("x", 60, stage="t-plain")
    check("run_claude（純文字交稿）不加 --json-schema", "--json-schema" not in seen_plain["cmd"])
    no_so = [dict(x) for x in json_lines]
    no_so[-1] = {k: v for k, v in no_so[-1].items() if k != "structured_output"}
    mg.subprocess.run, _ = _fake_claude(no_so)
    check("result 缺 structured_output → 退用 StructuredOutput 工具呼叫的 input", mg.run_claude_json("x", 60, {}, stage="t-json") == so)
    mg.subprocess.run, _ = _fake_claude([json_lines[0], json_lines[1], no_so[-1]])
    try:
        mg.run_claude_json("x", 60, {}, stage="t-json")
        check("完全沒結構化結果應 raise", False)
    except RuntimeError as e:
        check("完全沒結構化結果應 raise", "structured_output" in str(e), str(e)[:60])

    # rescue_meta／v2.2 出廠自評／每日留言分流 改走 run_claude_json
    orig_rcj = mg.run_claude_json
    calls = []
    try:
        mg.run_claude_json = lambda prompt, timeout, schema, **kw: (calls.append((schema, kw)) or so)
        meta_r, html_r = mg.rescue_meta("<!DOCTYPE html><html><canvas></canvas></html>", {"genre": "益智", "source": "原作"})
        check("rescue_meta 用 RESCUE_META_SCHEMA", calls[-1][0] is mg.RESCUE_META_SCHEMA and meta_r["title"] == "喵艙" and html_r.startswith("<!--GAMEMETA"))
        crit_so = {"scores": {"onboarding": 7.5, "juice": 8, "goal": 6, "difficulty": 7, "one_more": 6}, "fixes": ["a", "b"],
                   "verdict": "v", "howto": "h", "design_choices": ["d"], "pressure_3min": "p", "scale_up": {"worth": True, "why": "w"}}
        mg.run_claude_json = lambda prompt, timeout, schema, **kw: (calls.append((schema, kw)) or json.loads(json.dumps(crit_so)))
        crit_r = mg.stage_critic("<html></html>", {"title": "t"})
        check("v2.2 stage_critic 用 CRITIC_SCHEMA＋自己加總", calls[-1][0] is mg.CRITIC_SCHEMA and crit_r["total"] == 35, str(crit_r and crit_r.get("total")))
    finally:
        mg.run_claude_json = orig_rcj
    import daily_feedback                          # noqa: E402
    orig_df = daily_feedback.run_claude_json
    try:
        daily_feedback.run_claude_json = lambda prompt, timeout, schema, **kw: {"items": [
            {"row": 5, "action": "fix", "reply": "收到", "fix_instruction": "調慢", "learning": "L"},
            {"row": "壞列號", "action": "note", "reply": "x", "fix_instruction": "", "learning": ""}]}
        tri = daily_feedback.triage([{"row": 5, "game": "g", "score": 3, "note": "太快"}], {"g": "遊戲"})
        check("daily_feedback.triage 吃 items 陣列、壞列跳過", list(tri) == [5] and tri[5]["action"] == "fix", str(tri))
        check("TRIAGE_SCHEMA action 是 fix/note enum",
              daily_feedback.TRIAGE_SCHEMA["properties"]["items"]["items"]["properties"]["action"]["enum"] == ["fix", "note"])

        def _keys(s):
            for k, v in (s.get("properties") or {}).items():
                yield k
                if isinstance(v, dict):
                    yield from _keys(v)
                    if isinstance(v.get("items"), dict):
                        yield from _keys(v["items"])
        all_schemas = (stages.PLAN_SCHEMA, stages.REVIEW_SCHEMA, mg.CRITIC_SCHEMA, mg.RESCUE_META_SCHEMA, daily_feedback.TRIAGE_SCHEMA)
        check("所有固定 schema 欄位名都是英數（API 規定，中文鍵回 400）",
              all(stages._API_KEY_RE.match(k) for s in all_schemas for k in _keys(s)))
    finally:
        daily_feedback.run_claude_json = orig_df
finally:
    mg.subprocess.run, mg.USAGE_LOG = orig_run, orig_usage

# ---------------------------------------------------------------- 11. live 探針（可選）
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
