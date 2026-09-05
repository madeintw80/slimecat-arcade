# -*- coding: utf-8 -*-
"""v3 各階段的 prompt／交稿解析／驗證（企劃書→引擎→內容包→組裝→評審→打磨 patch）。

模型／effort 首輪配置（2026-09-05 Boss 照建議自決，跑三～四款用 usage.jsonl 對帳後再定案）：
  企劃書 fable max   —— 輸出短、槓桿最大（合約寫錯後面全歪）
  引擎   fable xhigh —— 品質關鍵、單一作者
  內容包 sonnet      —— 照 schema 填資料，便宜又聽話
  評審   Echo（Phase 2，見 echo_review.py）→ 失敗回 sonnet
  打磨   fable high  —— 只印 patch，輸出小
呼叫都走 make_game.run_claude（stream-json 收全段、記 usage.jsonl、撞額度丟 QuotaError）。
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # factory/
sys.path.insert(0, str(HERE))
import make_game as mg   # noqa: E402  共用 run_claude／GENRES／normalize_genre／split_html／recent_lessons

# ---- 模型與 effort（對帳後改這裡）----
# 企劃書 effort：2026-09-05 首航實測 max＝1050 秒／66k 輸出 tokens／$5.16，且合約 JSON 壞掉——
# 「輸出短、槓桿大」的假設不成立（max 會把企劃書寫成小論文）；改 high，篇幅由 prompt 限制。
MODEL_PLAN, EFFORT_PLAN = "fable", "high"
# 引擎 effort：首航 xhigh＋2,200 行在 64k 輸出上限被截斷（思考 tokens 也算輸出）；改 high、上限拉到 128k、
# 行數壓 2,000；再爆一次就用 TIGHT（1,400 行、medium）重試。
MODEL_ENGINE, EFFORT_ENGINE = "fable", "high"
TIGHT_ENGINE_LINES, TIGHT_ENGINE_EFFORT = 1400, "medium"
MODEL_CONTENT, EFFORT_CONTENT = "sonnet", ""
MODEL_CRITIC, EFFORT_CRITIC = "sonnet", ""
MODEL_POLISH, EFFORT_POLISH = "fable", "high"

PLAN_TIMEOUT = 1800      # 企劃書
ENGINE_TIMEOUT = 3600    # 引擎一整檔（可能 2,000 行）
CONTENT_TIMEOUT = 900    # 每個內容包
CRITIC_TIMEOUT = 900
POLISH_TIMEOUT = 1800

# 每次呼叫的花費保險絲（美元；CLI --max-budget-usd）。截斷後 CLI 會自己重試，沒保險絲一次可燒 $15。
BUDGET_USD = {"v3-plan": 4.0, "v3-engine": 9.0, "v3-content": 1.5, "v3-critic": 1.5, "v3-polish": 4.0}

# ---- 規模上限（Boss 拍板 3C：由企劃書依機制自訂，上限＝大型）----
CAPS = {"packs": 4, "items": 30, "engine_lines": 2000, "session_max_min": 10}
DEFAULT_ENGINE_LINES = 1600
CRITIC_HTML_CAP = 200000   # 評審讀多少字原始碼（v3 遊戲比較大）
PACK_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,24}$")
CONTENT_BLOCK_RE = re.compile(r"<script[^>]*\bid=[\"']sc-content[\"'][^>]*>.*?</script>", re.S | re.I)
NOTES_RE = re.compile(r"<!--\s*CONTENT-NOTES(.*?)-->", re.S)


def call(prompt: str, timeout: int, model: str, effort: str, stage: str) -> str:
    """run_claude 的薄包裝：帶該階段的花費保險絲；effort 不被接受時自動退回預設 effort 再試一次。"""
    budget = BUDGET_USD.get(stage.split(":")[0], 0)
    try:
        return mg.run_claude(prompt, timeout, model=model, effort=effort, stage=stage, max_budget_usd=budget)
    except (mg.QuotaError, mg.OutputLimitError):
        raise
    except RuntimeError as e:
        if effort and "effort" in str(e).lower():
            mg.log(f"  ⚠️ {stage}：effort={effort} 被拒（{str(e)[:80]}），改用預設 effort 重試")
            return mg.run_claude(prompt, timeout, model=model, effort="", stage=stage, max_budget_usd=budget)
        raise


def _strip_fences(text: str) -> str:
    return re.sub(r"^```[a-zA-Z]*\s*$", "", text or "", flags=re.M).strip()


def _balanced_object(text: str, start: int) -> str:
    """從 text[start]（必須是 '{'）取到配對的 '}'；跳過字串內的括號。取不到回 ''。"""
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def _json_cleanup(s: str) -> str:
    """模型常犯的兩種 JSON 錯：尾逗號、行尾 // 註解。清掉再試一次。"""
    s = re.sub(r"^\s*//[^\n]*$", "", s, flags=re.M)          # 整行註解
    s = re.sub(r",\s*([}\]])", r"\1", s)                      # 尾逗號
    return s


def _first_json_object(text: str):
    """從文字裡撈第一個能 parse 的 {…}（容忍前後廢話）。撈不到回 None。"""
    text = _strip_fences(text)
    start = text.find("{")
    while start >= 0:
        blob = _balanced_object(text, start)
        if blob:
            for cand in (blob, _json_cleanup(blob)):
                try:
                    return json.loads(cand)
                except ValueError:
                    continue
        start = text.find("{", start + 1)
    return None


def parse_json_block(raw: str) -> dict:
    """合約專用：只認「最外層」那個物件（第一個 { 到配對的 }），壞掉就 raise，不退到內層物件。

    為什麼不用 _first_json_object：外層 JSON 有尾逗號時它會掉到內層第一個合法物件
    （例如 modules[0]），看起來像「合約沒有內容包」，其實是整份合約沒 parse 到（9/5 首航）。
    """
    text = _strip_fences(raw)
    start = text.find("{")
    if start < 0:
        raise ValueError("合約區塊裡沒有 JSON 物件")
    blob = _balanced_object(text, start)
    if not blob:
        raise ValueError("合約 JSON 大括號沒配對（輸出被截斷？）")
    last_err = None
    for cand in (blob, _json_cleanup(blob)):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
            raise ValueError("合約 JSON 不是物件")
        except ValueError as e:
            last_err = e
    raise ValueError(f"合約 JSON 解析失敗：{str(last_err)[:120]}")


_KEY_ALIASES = {
    "contentpacks": "content_packs", "packs": "content_packs", "contentpack": "content_packs",
    "itemschema": "item_schema", "schema": "item_schema", "fields": "item_schema",
    "enginelinesbudget": "engine_lines_budget", "linesbudget": "engine_lines_budget",
    "sessionminutes": "session_minutes", "storagekey": "storage_key", "unlockrule": "unlock_rule",
}


def _normalize_keys(obj):
    """鍵名容錯：contentPacks／content-packs／packs 都對回合約用的 snake_case（遞迴）。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            nk = str(k)
            flat = re.sub(r"[^a-z0-9]", "", nk.lower())
            nk = _KEY_ALIASES.get(flat, nk)
            out[nk] = _normalize_keys(v)
        return out
    if isinstance(obj, list):
        return [_normalize_keys(x) for x in obj]
    return obj


# ================================================================ 企劃書（模組合約）
CONTRACT_TEMPLATE = """{
  "title": "遊戲中文名（全新命名；不可含原作名，不可與原作名音近/形近/直譯）",
  "emoji": "一個代表 emoji",
  "genre": "只能從這個清單挑一個：%s",
  "desc": "一句話介紹（30 字內，大廳卡片用）",
  "session_minutes": [3, 8],
  "modules": [
    {"id": "spawner", "role": "職責一句話", "state": "它管哪些狀態", "api": "對外函式或事件"}
  ],
  "content_packs": [
    {"key": "levels", "label": "關卡", "count": 12,
     "item_schema": {"id": "string｜唯一英文 id", "name": "string｜繁中名稱（有個性，不要「第一關」）",
                     "waves": "int｜1-30，該關波數", "boss": "bool｜是否有頭目"},
     "rules": ["前 3 關不會死", "每 3 關引入一個新元素", "數值要有節奏（緊→鬆→緊）"],
     "examples": [{"id": "l01", "name": "晨霧碼頭", "waves": 3, "boss": false},
                  {"id": "l02", "name": "潮汐倉庫", "waves": 4, "boss": false}]}
  ],
  "progress": {"storage_key": "sc_<英文slug>_v1", "saves": "存什麼（解鎖關卡／升級等級／圖鑑）",
               "unlock_rule": "解鎖規則一句話"},
  "acceptance": ["開場 15 秒內不會死", "第 3 分鐘出現新壓力源（具體是什麼）", "…共 8～12 條可觀察行為"],
  "engine_lines_budget": 1800
}""" % "/".join(mg.GENRES)


def build_plan_prompt(decon: dict, past_games: list) -> str:
    kb = mg.KB_FILE.read_text(encoding="utf-8") if mg.KB_FILE.exists() else ""
    learn = mg.recent_lessons()
    past = [f"《{g['title']}》({g.get('genre', '')})：{g.get('desc', '')}" for g in past_games]
    origin_note = {
        "steam": "（來源＝Steam PC 遊戲：原作是一套大系統，你只能留一個核心迴圈；別把整款搬過來）",
        "named": "（Boss 點名的靈感）",
    }.get(decon.get("origin", ""), "")
    return f"""你是「SlimeCat 遊戲工作室」的首席遊戲策劃。任務：把下面這份解構筆記（或原創企劃）展開成
一份「可直接分工實作」的企劃書＋模組合約。這款要比本站過去所有作品都更好玩，而且要「做大」：
單局 3～{CAPS['session_max_min']} 分鐘、有跨局進度（解鎖／升級／圖鑑至少一種），玩家關掉再開會想繼續。
（直接輸出文字、不要使用任何工具）

═══ 設計聖經（做之前先內化）═══
{kb}

═══ 解構筆記／企劃（策劃前置作業）{origin_note}═══
建議名稱：《{decon.get('title') or '（自訂）'}》；類型：{mg.normalize_genre(decon.get('genre'))}
{decon.get('doc', '')}

═══ 近期的教訓與玩家回饋（最高優先級，玩家評分 > 理論）═══
{learn if learn else "（還沒有）"}

═══ 本站已有遊戲（核心機制不可重複）═══
{chr(10).join(past) if past else "（無）"}

分工方式（要理解才寫得出合約）：
1. 引擎由一位開發者「一次寫完單檔」，它只實作系統，不寫死任何關卡／波次／升級／圖鑑資料
2. 內容包由另一位內容設計師照你定的 schema 分次生成 JSON；引擎從 window.SC_CONTENT[key] 讀
3. 所以合約要寫清楚：每種內容包的欄位（型別｜意義｜範圍）、數量、設計原則、2 筆完整範例；
   引擎要有哪些模組、各管什麼狀態、對外介面是什麼

規模由你依機制決定（Boss 拍板：不綁固定規模），但硬上限：
- 內容包最多 {CAPS['packs']} 種、每種最多 {CAPS['items']} 筆（合約 count）
- 引擎不超過 {CAPS['engine_lines']} 行（單檔 HTML 含 CSS/JS）；一般 1,500～2,000 行就夠
- 單局 3～{CAPS['session_max_min']} 分鐘；跨局進度存 localStorage
- 手機直式 canvas 400×600，觸控＋鍵盤都能玩；零外部資源；美術完全自由（不必是史萊姆貓）
版權紅線：只學機制與心理學、不抄表達——命名、特徵性視覺、具體數值表與關卡佈局都不可與原作相同。

篇幅：企劃書本體 3,000～5,000 字（不含合約 JSON）——寫給工程師看的規格，不是論文；每節講清楚就換下一節。

輸出格式（嚴格遵守）：先是企劃書本體（Markdown，照下面章節），最後一行 ===CONTRACT=== 之後
接一個 JSON 物件（合法 JSON：不要 code fence、不要註解、不要尾逗號），再以 ===END=== 收尾。

# 企劃書：《遊戲名》
## 一句話企劃與核心樂趣
## 核心迴圈（一圈幾秒？操作→回饋→獎勵；微迴圈／中迴圈／威脅迴圈）
## 上癮機制（near-miss／歸因於己／變動獎勵／損失趨避……在這款怎麼掛，具體可實作）
## 系統與模組（引擎要做的模組：職責／狀態／對外介面）
## 內容包規格（每種內容包：用途／欄位／數量／設計原則／難度曲線怎麼靠內容排）
## 進度與存檔（存什麼、解鎖規則、第一次玩與第十次玩的差別）
## 玩法規格（盤面／判定／計分／UI 版面／操作：手機觸控＋鍵盤，具體到工程師能直接照做）
## 難度曲線與壓力源（第 1 分鐘／第 3 分鐘／第 6 分鐘各有什麼新壓力）
## 風險與捨棄（最容易不好玩的點怎麼避；誘人但要忍住不做的）
## 驗收清單（8～12 條「可觀察」的行為，評審與品管會逐條對）

===CONTRACT===
{CONTRACT_TEMPLATE}
===END===

合約 JSON 規則：content_packs 的 key 用小寫英文＋底線；item_schema 每個欄位值寫成「型別｜說明（範圍或可用值）」，
型別只能是 string／int／number／bool／array／object；examples 每筆都要包含 item_schema 全部欄位；
acceptance 每條都要是「看得見、測得到」的行為。
"""


def parse_plan(out: str) -> tuple:
    """把策劃輸出拆成 (企劃書 Markdown, 合約 dict)。合約撈不到就 raise ValueError。"""
    text = out.replace("\r\n", "\n")
    m = re.search(r"^===\s*CONTRACT\s*===\s*$", text, re.M)
    if not m:
        raise ValueError("企劃書輸出缺 ===CONTRACT=== 分隔線")
    doc = text[:m.start()].strip()
    rest = text[m.end():]
    end = re.search(r"^===\s*END\s*===\s*$", rest, re.M)
    raw = rest[:end.start()] if end else rest
    contract = _normalize_keys(parse_json_block(raw))
    i = doc.find("# 企劃書")
    if i > 0:
        doc = doc[i:]
    return doc, contract


def _schema_type(spec) -> str:
    """item_schema 的值「型別｜說明」→ 取型別（小寫）；格式不對回 ''。"""
    s = str(spec or "").strip().lower()
    t = re.split(r"[｜|:：\s]", s, 1)[0] if s else ""
    return {"integer": "int", "float": "number", "boolean": "bool", "list": "array", "str": "string",
            "dict": "object"}.get(t, t)


def validate_contract(c: dict, decon: dict) -> dict:
    """整理＋驗證合約：補預設、夾規模上限、格式壞掉就 raise ValueError（讓企劃書重做）。"""
    c = dict(c or {})
    c["title"] = str(c.get("title") or decon.get("title") or "").strip()
    if not c["title"]:
        raise ValueError("合約缺 title")
    c["emoji"] = str(c.get("emoji") or "🎮").strip()[:4] or "🎮"
    c["genre"] = mg.normalize_genre(c.get("genre") or decon.get("genre"))
    c["desc"] = str(c.get("desc") or "").strip()[:60]
    sm = c.get("session_minutes")
    if not (isinstance(sm, list) and len(sm) == 2):
        sm = [3, 8]
    c["session_minutes"] = [max(1, int(sm[0])), min(CAPS["session_max_min"], max(int(sm[0]), int(sm[1])))]
    c["modules"] = [m for m in (c.get("modules") or []) if isinstance(m, dict) and m.get("id")][:16]

    packs = [p for p in (c.get("content_packs") or []) if isinstance(p, dict)]
    if not packs:
        raise ValueError("合約沒有任何內容包（content_packs 空的）")
    clean, keys = [], set()
    for p in packs[:CAPS["packs"]]:
        key = re.sub(r"[^a-z0-9_]", "_", str(p.get("key") or "").strip().lower())[:24]
        if not PACK_KEY_RE.match(key or "") or key in keys:
            raise ValueError(f"內容包 key 不合法或重複：{p.get('key')!r}")
        keys.add(key)
        schema = p.get("item_schema")
        if not isinstance(schema, dict) or len(schema) < 2:
            raise ValueError(f"內容包 {key} 的 item_schema 要是至少 2 個欄位的物件")
        bad = [k for k, v in schema.items() if _schema_type(v) not in
               ("string", "int", "number", "bool", "array", "object")]
        if bad:
            raise ValueError(f"內容包 {key} 的 item_schema 型別不合法：{bad}（要寫成「型別｜說明」）")
        try:
            count = int(p.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        count = max(1, min(CAPS["items"], count or 8))
        examples = [e for e in (p.get("examples") or []) if isinstance(e, dict)]
        if not examples:
            raise ValueError(f"內容包 {key} 沒有 examples（引擎要靠它們才能單獨跑）")
        for e in examples:
            for k in schema:
                if k not in e:
                    raise ValueError(f"內容包 {key} 的範例缺欄位 {k}")
        clean.append({"key": key, "label": str(p.get("label") or key)[:20], "count": count,
                      "item_schema": {str(k): str(v) for k, v in schema.items()},
                      "rules": [str(r)[:120] for r in (p.get("rules") or [])][:10],
                      "examples": examples[:3]})
    c["content_packs"] = clean

    prog = c.get("progress") if isinstance(c.get("progress"), dict) else {}
    slug = re.sub(r"[^a-z0-9]+", "_", str(prog.get("storage_key") or "").lower()).strip("_")
    if not slug or slug == "sc":
        slug = "sc_" + re.sub(r"[^a-z0-9]+", "", str(c["title"]).lower()) or "sc_game"
    c["progress"] = {"storage_key": slug[:40], "saves": str(prog.get("saves") or "")[:160],
                     "unlock_rule": str(prog.get("unlock_rule") or "")[:160]}
    c["acceptance"] = [str(a)[:120] for a in (c.get("acceptance") or []) if str(a).strip()][:12]
    try:
        budget = int(c.get("engine_lines_budget") or DEFAULT_ENGINE_LINES)
    except (TypeError, ValueError):
        budget = DEFAULT_ENGINE_LINES
    c["engine_lines_budget"] = max(800, min(CAPS["engine_lines"], budget))
    return c


def stage_plan(decon: dict, past_games: list, feedback: str = "") -> tuple:
    """企劃書＋合約。回 (plan_doc, contract, raw)；解析／驗證失敗時原始輸出先存 failed_outputs 再 raise。"""
    prompt = build_plan_prompt(decon, past_games)
    if feedback:
        prompt += f"\n⚠️ 上一次的合約有問題，請修正：{feedback}\n"
    out = call(prompt, PLAN_TIMEOUT, MODEL_PLAN, EFFORT_PLAN, "v3-plan")
    try:
        doc, contract = parse_plan(out)
        contract = validate_contract(contract, decon)
    except ValueError as e:
        p = mg.save_failed_output(out, "v3-plan")
        raise ValueError(f"{e}（原始輸出 failed_outputs/{p.name}）") from e
    return doc, contract, out


# ================================================================ 引擎
HARD_SPECS = """硬性規格（違反任何一條就算失敗）：
- 單一 HTML 檔內含全部 CSS/JS；零外部資源（不可用 CDN、外部圖片、字型、音檔；音效用 WebAudio 合成）
- 遊戲畫面用 <canvas>，寬 400 高 600 直式，JS 把 canvas 等比縮放到適合視窗
- 手機觸控與電腦鍵盤都要能玩；canvas 設 touch-action:none 防頁面捲動
- 主迴圈不可假設 60fps：用固定時間步長（fixed timestep accumulator）或 deltaTime，
  120Hz 螢幕的手機不可變兩倍速；監聽 pointercancel/blur 清掉輸入狀態（防卡鍵/自走）
- 高解析度輸出：canvas 實體緩衝 = 顯示尺寸 × devicePixelRatio（cap 3），再用
  ctx.setTransform(s*dpr,0,0,s*dpr,0,0) 讓邏輯座標維持 400×600；輸入座標一律用 getBoundingClientRect 換算
- 標題畫面（遊戲名＋一句話規則＋繁中操作說明＋點擊開始）；即時分數；Game Over／通關可一鍵重來
- localStorage 存最高分與跨局進度（鍵名照合約 progress.storage_key），所有讀寫包 try/catch
- 介面文字一律繁體中文；程式碼加簡短繁中註解
- 不可用 alert/confirm/prompt；不可出現 console.error 或未捕捉例外
- 頁面左上角放回大廳連結：<a href="../../index.html">← 回遊戲區</a>
- 一局結束（Game Over 或通關）時加一行 `if (window.SC) SC.over(最終分數);`（匿名數據回報，SC 由站台注入）"""

CONTENT_MECHANISM = """內容注入機制（合約的核心，違反＝失敗）：
- 引擎不可寫死關卡／波次／升級／圖鑑等內容；一律從 window.SC_CONTENT[內容包 key] 讀
  （值＝物件陣列，欄位照合約 item_schema）
- 檔案裡放一個 <script id="sc-content">window.SC_CONTENT = {…};</script>，內容＝合約各內容包的 examples
  （工廠組裝時會把這整塊換成完整內容；這個 script 要放在引擎主程式之前，id 與寫法不可變）
- 引擎要吃得下「任何符合 schema 的內容」：數值超出合理範圍要 clamp、缺欄位給預設值，
  內容包長度不同（5 筆或 30 筆）都不能壞；關卡／波次數量要依陣列長度動態決定
- <head> 裡放一段 <!--CONTENT-NOTES … --> 註解：逐包列出引擎實際支援的欄位、數值安全範圍、
  enum 可用值（內容設計師只會照這段填資料，寫得越具體內容越好）
- 暴露 window.SC_HOOKS = { start(): 跳過標題直接開始一局, snapshot(): 回傳 {scene, score, level, elapsed, …} 純資料 }
  （品管自動化用，不影響玩家）"""


def engine_line_budget(contract: dict, tight: bool = False) -> int:
    try:
        budget = int(contract.get("engine_lines_budget") or DEFAULT_ENGINE_LINES)
    except (TypeError, ValueError):
        budget = DEFAULT_ENGINE_LINES
    budget = min(budget, CAPS["engine_lines"])
    return min(budget, TIGHT_ENGINE_LINES) if tight else budget


def build_engine_prompt(plan_doc: str, contract: dict, decon: dict, feedback: str = "",
                        line_budget: int = None) -> str:
    kb = mg.KB_FILE.read_text(encoding="utf-8") if mg.KB_FILE.exists() else ""
    fb = (f"\n⚠️ 上一次交稿沒通過，原因如下，請避免同類問題：\n{feedback}\n" if feedback else "")
    line_budget = line_budget or engine_line_budget(contract)
    return f"""你是「SlimeCat 遊戲工作室」的資深遊戲開發者。策劃已完成企劃書與模組合約，你是引擎的**唯一作者**：
一次寫完整個單檔 HTML5 遊戲引擎（系統＋畫面＋音效），內容資料由別人照合約另外生成。
（直接輸出文字、不要使用任何工具）

═══ 設計聖經（實作時逐條對照第三節「出貨檢查清單」）═══
{kb}

═══ 企劃書 ═══
{plan_doc}

═══ 模組合約（JSON）═══
{json.dumps(contract, ensure_ascii=False, indent=1)}
{fb}
任務：實作《{contract['title']}》引擎。美術風格完全自由（不必是史萊姆貓）：挑最能放大這個機制的主題與視覺，
canvas 畫或 emoji 皆可；絕不可用原作（{decon.get('source', '')}）的名稱/角色/美術/音樂。
特別注意：前 15 秒不會死、每個互動都有 juice、Game Over 顯示差 X 分破紀錄、重開一鍵零等待、
第 3 分鐘要有新的壓力源；跨局進度要讓「第十次玩」跟「第一次玩」明顯不同。

{HARD_SPECS}

{CONTENT_MECHANISM}

🔴 篇幅硬上限：整個檔案 **{line_budget} 行以內**（含 CSS/JS）。超過會被輸出上限截斷、整包作廢。
合約的模組清單是「職責劃分」不是檔案結構：小模組合併成函式、共用工具抽出來、不要重複程式碼、
註解精簡（每個函式一行說明就好）；寧可少做一個次要系統，也要一次交完整。把力氣花在手感與回饋，不要堆系統。

🔴 交付方式：你唯一的交付物是「印出的文字」。不要使用任何工具、不要建立或修改任何檔案（你也沒有寫檔權限）。
**整份交稿放在同一則回覆裡**，不要分成兩則、不要中途停下來問問題。想清楚再開始寫，寫的時候一路寫到底。
輸出格式（嚴格遵守）：不要 markdown code fence、不要任何解說文字；第一行就是 <!DOCTYPE html>，
最後一行是 </html>。
"""


def parse_engine(out: str) -> tuple:
    """交稿 → (html, content_notes)。本體殘缺就 raise ValueError（呼叫端存 failed_outputs）。"""
    body = mg.split_html(out)
    if body is None:
        raise ValueError("引擎交稿不完整（缺 DOCTYPE/</html>/canvas）")
    notes_m = NOTES_RE.search(body)
    notes = notes_m.group(1).strip() if notes_m else ""
    return body, notes


def stage_engine(plan_doc: str, contract: dict, decon: dict, feedback: str = "", tight: bool = False) -> tuple:
    """tight＝上一次爆輸出上限後的緊縮模式：行數壓到 TIGHT_ENGINE_LINES、effort 降到 TIGHT_ENGINE_EFFORT。"""
    prompt = build_engine_prompt(plan_doc, contract, decon, feedback, engine_line_budget(contract, tight))
    out = call(prompt, ENGINE_TIMEOUT, MODEL_ENGINE, TIGHT_ENGINE_EFFORT if tight else EFFORT_ENGINE, "v3-engine")
    try:
        return parse_engine(out)
    except ValueError:
        p = mg.save_failed_output(out, "v3-engine")
        mg.log(f"  🗄️ 引擎原始輸出已存 failed_outputs/{p.name}（驗屍用）")
        raise


# ================================================================ 內容包＋組裝
def content_script(content: dict) -> str:
    """把 {key: [items…]} 變成 <script id="sc-content"> 區塊；JSON 裡的 </ 與 <!-- 要跳脫，否則 HTML 解析會提早收尾。"""
    js = json.dumps(content, ensure_ascii=False)
    js = js.replace("</", "<\\/").replace("<!--", "<\\!--")
    return f'<script id="sc-content">window.SC_CONTENT = {js};</script>'


def assemble(engine_html: str, content: dict) -> str:
    """把引擎裡的 examples 版 sc-content 區塊換成完整內容包。沒有那個區塊就插在第一個 <script> 前。"""
    block = content_script(content)
    if CONTENT_BLOCK_RE.search(engine_html):
        return CONTENT_BLOCK_RE.sub(lambda _m: block, engine_html, count=1)
    mg.log("  ⚠️ 引擎沒有 <script id=\"sc-content\"> 區塊，改插在第一個 <script> 之前")
    i = engine_html.lower().find("<script")
    if i < 0:
        i = engine_html.lower().find("</head>")
    if i < 0:
        return block + "\n" + engine_html
    return engine_html[:i] + block + "\n" + engine_html[i:]


def examples_content(contract: dict) -> dict:
    return {p["key"]: p["examples"] for p in contract["content_packs"]}


def plan_excerpt(plan_doc: str, keys=("核心迴圈", "內容包", "難度曲線", "進度"), limit: int = 7000) -> str:
    """給內容設計師看的企劃書節錄（只抓相關章節，省 tokens）；抓不到就給全文前段。"""
    parts = []
    for k in keys:
        m = re.search(rf"^(##[^\n]*{re.escape(k)}[^\n]*\n.*?)(?=^## |\Z)", plan_doc or "", re.S | re.M)
        if m:
            parts.append(m.group(1).strip())
    text = "\n\n".join(parts) if parts else (plan_doc or "")
    return text[:limit]


# ---- 跨包引用（2026-09-05 首航教訓：房間包引用了圖鑑包沒有的 24 個 id，引擎靜默略過→首房軟鎖）----
REF_KEYS = ("obj", "object", "id", "ref", "target", "item", "boss", "key", "type", "unlock", "reward")


def _singulars(key: str) -> list:
    forms = [key]
    if key.endswith("ies"):
        forms.append(key[:-3] + "y")
    if key.endswith("es"):
        forms.append(key[:-2])
    if key.endswith("s"):
        forms.append(key[:-1])
    return [f for f in forms if len(f) >= 3]


def _strings_in(v) -> set:
    """一個欄位值裡「可能是 id」的字串：字串本身／字串陣列／物件陣列裡 REF_KEYS 欄位的值。"""
    out = set()
    if isinstance(v, str):
        out.add(v)
    elif isinstance(v, list):
        for x in v:
            out |= _strings_in(x)
    elif isinstance(v, dict):
        for k, x in v.items():
            if k in REF_KEYS and isinstance(x, str):
                out.add(x)
    return out


def ref_fields(pack: dict, contract: dict) -> dict:
    """這個內容包哪些欄位引用別的內容包：{欄位: 目標 pack key}。

    判斷：欄位說明提到別包的 key／單數形／label（例 spawn「obj 必存在於 objects」），
    或該欄位在 examples 裡的值對得上別包 examples 的 id（例 boss:"landlord_fatcat"）。
    """
    others = [p for p in contract["content_packs"] if p["key"] != pack["key"]]
    ex_ids = {p["key"]: {str(e.get("id")) for e in p.get("examples", []) if e.get("id")} for p in others}
    out = {}
    for field, spec in pack["item_schema"].items():
        s = str(spec)
        # 只看「說明」部分，不看型別：型別 object 會撞到內容包 objects 的單數形（palette:"object｜{…}" 誤判）
        desc = re.split(r"[｜|]", s, 1)[1] if re.search(r"[｜|]", s) else s
        target = ""
        for p in others:
            words = set(_singulars(p["key"])) | {p.get("label", "")}
            if any(w and re.search(rf"(?<![a-z_]){re.escape(w)}(?![a-z_])", desc) for w in words):
                target = p["key"]
                break
        if not target:
            for e in pack.get("examples", []):
                vals = _strings_in(e.get(field))
                for pk, ids in ex_ids.items():
                    if vals and vals & ids:
                        target = pk
                        break
                if target:
                    break
        if target:
            out[field] = target
    return out


def order_packs(contract: dict) -> list:
    """依引用關係排生成順序（被引用的先生）；有環或看不出來就照合約順序。"""
    packs = contract["content_packs"]
    deps = {p["key"]: set(ref_fields(p, contract).values()) for p in packs}
    done, ordered = set(), []
    remaining = list(packs)
    while remaining:
        ready = [p for p in remaining if deps[p["key"]] <= done]
        if not ready:
            ready = [remaining[0]]   # 互相引用→放棄排序，照合約順序
        for p in ready:
            ordered.append(p)
            done.add(p["key"])
            remaining.remove(p)
    return ordered


def pack_ids(items: list) -> set:
    return {str(it.get("id")) for it in items if isinstance(it, dict) and it.get("id") is not None}


def find_bad_refs(items: list, refs: dict, ids_by_key: dict) -> list:
    """回引用不存在 id 的問題清單（空＝乾淨）。目標包還沒生成就跳過（生成順序保證這不會發生）。"""
    problems = []
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        for field, target in refs.items():
            pool = ids_by_key.get(target)
            if pool is None:
                continue
            bad = sorted(v for v in _strings_in(it.get(field)) if v not in pool)
            if bad:
                problems.append(f"第 {i} 筆 {field} 引用 {target} 裡不存在的 id：{', '.join(bad[:6])}")
        if len(problems) >= 10:
            break
    return problems


def build_content_prompt(pack: dict, plan_doc: str, contract: dict, notes: str, feedback: str = "",
                         available: dict = None) -> str:
    fb = f"\n⚠️ 上一次的內容沒通過驗證：{feedback}\n請修正後重交。\n" if feedback else ""
    spec = {k: pack.get(k, [] if k in ("rules", "examples") else "") for k in ("key", "label", "count", "item_schema", "rules", "examples")}
    refs = ref_fields(pack, contract)
    avail_block = ""
    if refs and available:
        labels = {p["key"]: p.get("label", p["key"]) for p in contract["content_packs"]}
        lines = []
        for target in sorted(set(refs.values())):
            ids = sorted(available.get(target) or [])
            if ids:
                fields = "、".join(f for f, t in refs.items() if t == target)
                lines.append(f"- {target}（{labels.get(target, target)}）共 {len(ids)} 個，欄位 {fields} 只能用這些：{', '.join(ids)}")
        if lines:
            avail_block = ("\n═══ 🔴 可引用的 id 清單（其他內容包已生成；引用欄位一個都不可自創，自創的引擎會略過、關卡會壞）═══\n"
                           + "\n".join(lines) + "\n")
    return f"""你是「SlimeCat 遊戲工作室」的內容設計師（關卡／數值設計）。引擎已經做好，
請照合約 schema 填《{contract['title']}》的「{pack['label']}」內容包。（直接輸出文字、不要使用任何工具）

═══ 企劃書節錄（核心迴圈／內容包規格／難度曲線／進度）═══
{plan_excerpt(plan_doc)}

═══ 這個內容包的合約 ═══
{json.dumps(spec, ensure_ascii=False, indent=1)}

═══ 引擎的 CONTENT-NOTES（它實際支援的欄位與安全範圍；超出會被 clamp、不存在的欄位不會被讀）═══
{notes or "（引擎沒附；照合約 item_schema 的範圍填）"}
{avail_block}{fb}
要求：
- 剛好 {pack['count']} 筆；每筆包含 item_schema 全部欄位、型別照 schema；有 id 欄位就必須唯一
- 難度曲線照企劃書排：前段安全、每隔幾筆引入新元素、後段有壓力；數值不可單調線性，要有節奏（緊→鬆→緊）
- 引用別的內容包時只能用上面清單裡的 id；要用到的種類清單裡沒有就換一個有的，不可自創
- 繁中命名要有個性、貼主題，避免「第一關／第二關」這種占位名
- 只填 schema／CONTENT-NOTES 列出的欄位（多寫引擎也不會讀）

輸出：只印一個 JSON 陣列（[ {{…}}, {{…}} ]），不要 code fence、不要任何解說。
"""


def validate_pack(items, pack: dict) -> list:
    """驗內容包：型別、欄位齊全、id 唯一、筆數。有問題 raise ValueError（訊息會餵回重生）。"""
    if not isinstance(items, list):
        raise ValueError("輸出不是 JSON 陣列")
    schema, count = pack["item_schema"], pack["count"]
    items = [it for it in items if isinstance(it, dict)]
    if len(items) < max(1, int(count * 0.8)):
        raise ValueError(f"只有 {len(items)} 筆，合約要 {count} 筆")
    problems, ids = [], set()
    checks = {
        "string": lambda v: isinstance(v, str),
        "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "bool": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    for i, it in enumerate(items, 1):
        for k, spec in schema.items():
            if k not in it:
                problems.append(f"第 {i} 筆缺欄位 {k}")
                continue
            t = _schema_type(spec)
            if t in checks and not checks[t](it[k]):
                # int 欄位收到 3.0 這種整數值的 float 就放行（順手轉回 int）
                if t == "int" and isinstance(it[k], float) and it[k].is_integer():
                    it[k] = int(it[k])
                    continue
                problems.append(f"第 {i} 筆的 {k} 型別要 {t}，收到 {type(it[k]).__name__}")
        if "id" in schema:
            if it.get("id") in ids:
                problems.append(f"第 {i} 筆的 id 重複：{it.get('id')}")
            ids.add(it.get("id"))
        if len(problems) >= 8:
            break
    if problems:
        raise ValueError("；".join(problems[:8]))
    return items[:count]


def stage_content(pack: dict, plan_doc: str, contract: dict, notes: str, available: dict = None) -> list:
    """生成一個內容包（schema 驗證＋跨包引用驗證，失敗帶錯誤重生一次）。

    available：已生成的內容包 id（{pack key: set(ids)}），引用欄位只能用這些。
    """
    available = available or {}
    refs = ref_fields(pack, contract)
    feedback = ""
    for attempt in (1, 2):
        prompt = build_content_prompt(pack, plan_doc, contract, notes, feedback, available)
        out = call(prompt, CONTENT_TIMEOUT, MODEL_CONTENT, EFFORT_CONTENT, f"v3-content:{pack['key']}")
        text = _strip_fences(out)
        i, j = text.find("["), text.rfind("]")
        try:
            items = json.loads(text[i:j + 1]) if i >= 0 and j > i else None
            if items is None:
                raise ValueError("輸出裡找不到 JSON 陣列")
            items = validate_pack(items, pack)
            bad = find_bad_refs(items, refs, available)
            if bad:
                raise ValueError("；".join(bad[:6]))
            return items
        except ValueError as e:
            feedback = str(e)[:500]
            mg.log(f"  ⚠️ 內容包 {pack['key']} 第 {attempt} 次驗證失敗：{feedback[:160]}")
    raise ValueError(f"內容包 {pack['key']} 兩次都不合格：{feedback[:200]}")


# ================================================================ 評審（sonnet／Echo 共用 prompt）
REVIEW_SCALE = ("五維量表：上手(不看說明能玩?規則一句話?)、Juice(每個操作有視聽回饋?得分有爽感演出?)、"
                "目標(隨時知道為何而玩?)、難度(前15秒安全?2分鐘後仍有挑戰?)、再一局(near-miss設計?重開零摩擦?)")
REVIEW_JSON = ('{"scores":{"onboarding":n,"juice":n,"goal":n,"difficulty":n,"one_more":n},"total":n,'
               '"fixes":["最重要的改進點1（具體到工程師能直接改）","改進點2","改進點3"],'
               '"verdict":"一句話總評","howto":"給玩家看的一句話怎麼玩（30字內）",'
               '"design_choices":["從程式碼看得出來的關鍵設計決策1","決策2"],'
               '"pressure_3min":"第 3 分鐘的壓力源是什麼？沒有就寫『無：後期會平掉』（30字內）",'
               '"scale_up":{"worth":true或false,"why":"值不值得再做大的一句理由"},'
               '"audit":{"contract_issues":["合約寫了但成品沒做／做歪的（合約哪一項＋程式碼證據）"],'
               '"bugs":["確定會發生的錯誤（怎麼觸發＋在哪段程式碼）"]}}')


def build_review_prompt(plan_doc: str, contract: dict, html: str, qa_info: dict = None,
                        for_echo: bool = False) -> str:
    acceptance = "\n".join(f"- {a}" for a in contract.get("acceptance") or []) or "（企劃書沒列）"
    packs = "、".join(f"{p['label']}({p['key']}) {p['count']} 筆" for p in contract["content_packs"])
    qa = json.dumps({k: v for k, v in (qa_info or {}).items() if k in ("content", "snapshot", "warnings")},
                    ensure_ascii=False)[:800]
    who = ("你是 Echo（Codex 端 agent），受 Batnini 委派擔任 SlimeCat 遊戲工作室的獨立評審兼整合稽核員。"
           "只讀不寫：不要執行任何會修改檔案的指令，直接用文字回覆。" if for_echo
           else "你是嚴格的遊戲評審兼整合稽核員。")
    tail = ("回覆：先用 3～6 行繁體中文說明檢查結果，最後「單獨一行」輸出（務必照這個格式）：\n"
            f"REVIEW: {REVIEW_JSON}" if for_echo
            else f"只輸出一行，格式：\nREVIEW: {REVIEW_JSON}")
    return f"""{who}
以下是《{contract['title']}》的模組合約、企劃書驗收清單與完整原始碼（引擎＋內容包已組裝）。
用讀 code 的方式評估它「實際玩起來」的體驗（想像執行結果，別只看有沒有寫註解），並稽核成品有沒有照合約做。

{REVIEW_SCALE}
每維 1-10 分（8 分以上必須真的出色才給；可以給 .5 半分）。

整合稽核（audit）：
- contract_issues：合約寫了但成品沒做／做歪的——模組缺、內容包沒被引擎讀（例如 SC_CONTENT 的某個 key 沒用到）、
  驗收清單哪一條不成立、進度存檔沒實作。每條寫「合約哪一項＋程式碼證據」，沒有就給空陣列
- bugs：確定會發生的錯誤——邏輯錯、狀態沒清、越界、第 N 波／第 N 關後會炸、內容欄位型別用錯。
  每條寫「怎麼觸發＋在哪段程式碼」，沒有就給空陣列；不確定的別列（列了會被拿去修）

═══ 模組合約（JSON）═══
{json.dumps(contract, ensure_ascii=False, indent=1)}

═══ 驗收清單 ═══
{acceptance}

═══ 內容包 ═══
{packs}

═══ 品管快照（Playwright 亂玩 12 秒後）═══
{qa}

{tail}

═══ 原始碼 ═══
{html[:CRITIC_HTML_CAP]}
"""


def parse_review(text: str):
    """撈 REVIEW: 後的 JSON（找不到標記就撈最後一個含 scores 的物件）。撈不到回 None。"""
    text = text or ""
    for m in reversed(list(re.finditer(r"REVIEW:\s*(\{.*)", text, re.S))):
        obj = _first_json_object(m.group(1))
        if isinstance(obj, dict) and "scores" in obj:
            return obj
    obj = _first_json_object(text)
    return obj if isinstance(obj, dict) and "scores" in obj else None


def normalize_review(crit: dict) -> dict:
    """整理評審 JSON（同 make_game.stage_critic 的規則：五維 1-10、半分四捨五入、自己加總）＋稽核欄位。"""
    import math
    scores = crit.get("scores") or {}
    dims = ("onboarding", "juice", "goal", "difficulty", "one_more")
    clean = {}
    for d in dims:
        v = scores.get(d)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= v <= 10:
            raise ValueError(f"評審維度 {d}={v!r} 不在 1-10（五維不齊或超範圍）")
        clean[d] = int(math.floor(v + 0.5))
    out = {
        "scores": clean,
        "total": sum(clean.values()),
        "fixes": [str(x) for x in (crit.get("fixes") or []) if str(x).strip()][:3],
        "verdict": str(crit.get("verdict") or "")[:120],
        "howto": str(crit.get("howto") or "")[:60],
        "design_choices": [str(x)[:80] for x in (crit.get("design_choices") or [])][:3],
        "pressure_3min": str(crit.get("pressure_3min") or "")[:60],
    }
    su = crit.get("scale_up") if isinstance(crit.get("scale_up"), dict) else {}
    out["scale_up"] = {"worth": bool(su.get("worth")), "why": str(su.get("why") or "")[:80]}
    au = crit.get("audit") if isinstance(crit.get("audit"), dict) else {}
    out["audit"] = {
        "contract_issues": [str(x)[:200] for x in (au.get("contract_issues") or []) if str(x).strip()][:5],
        "bugs": [str(x)[:200] for x in (au.get("bugs") or []) if str(x).strip()][:5],
    }
    return out


def stage_critic(plan_doc: str, contract: dict, html: str, qa_info: dict = None):
    """sonnet 評審（Echo 不可用時的退路；Phase 1 也直接用它）。失敗回 None（不擋出貨）。"""
    prompt = build_review_prompt(plan_doc, contract, html, qa_info, for_echo=False)
    try:
        out = call(prompt, CRITIC_TIMEOUT, MODEL_CRITIC, EFFORT_CRITIC, "v3-critic")
        crit = parse_review(out)
        if crit is None:
            raise ValueError("輸出裡撈不到 REVIEW JSON")
        rev = normalize_review(crit)
        rev["reviewer"] = f"claude:{MODEL_CRITIC}"
        return rev
    except mg.QuotaError:
        raise
    except Exception as e:
        mg.log(f"  ⚠️ 評審失敗（不擋出貨）：{e}")
        return None


# ================================================================ 打磨（patch）
def build_polish_prompt(html: str, issues: list, contract: dict) -> str:
    items = "\n".join(f"{i}. {t}" for i, t in enumerate(issues, 1))
    return f"""你是「SlimeCat 遊戲工作室」的資深遊戲開發者。你剛完成的《{contract['title']}》經過評審與整合稽核，
請針對下面這幾條修訂——**用 patch 交稿，不要重印整檔**。（直接輸出文字、不要使用任何工具）

═══ 要修的項目（只處理這幾條，其他別動）═══
{items}

═══ 目前完整原始碼 ═══
{html}

修訂規則：
- 只做「修這幾條」需要的改動，改動越小越好；不可重寫成另一款遊戲、不可順手大改其他系統
- 原本能玩的功能不可弄壞；維持硬性規格（單檔零外部資源／canvas 400×600／fixed timestep／DPR 高解析／
  繁中介面／SC.over 回報／localStorage try-catch）
- <script id="sc-content"> 區塊、window.SC_CONTENT 讀取、window.SC_HOOKS 都不可拆掉
- 🔴 不要 patch <script id="sc-content"> 那一行（內容包是工廠另外生成的單行 JSON，patch 對不上）：
  內容資料有問題就改「引擎怎麼處理這種資料」（例如引用不存在的 id 時改用同 tier 的替代物件、
  至少保證每房有可吞的成長階梯），不要動資料本身

交稿格式（嚴格遵守）：一個或多個下面這種區塊。SEARCH 段必須是原始碼裡「一字不差」的連續行（含縮排），
並包含足夠上下文讓它在檔案裡唯一；REPLACE 段是換上去的內容。除了區塊之外不要任何解說。
真的不需要修改就只印一行：NOPATCH: 理由

<<<<<<< SEARCH
（原始碼裡的連續幾行）
=======
（換成這些行）
>>>>>>> REPLACE
"""


def stage_polish_patch(html: str, issues: list, contract: dict) -> tuple:
    """回 (patch 原文, 套用後 html 或 None)。套不上 raise patch.PatchError（呼叫端沿用原版）。"""
    from v3 import patch as patchmod
    prompt = build_polish_prompt(html, issues, contract)
    out = call(prompt, POLISH_TIMEOUT, MODEL_POLISH, EFFORT_POLISH, "v3-polish")
    new_html, n = patchmod.apply_text(html, out)
    if new_html is not None:
        mg.log(f"  🩹 patch 套用 {n} 塊")
    return out, new_html
