# -*- coding: utf-8 -*-
"""SlimeCat 遊戲工作室 v2.2 — 會學習的遊戲生產線（2026-09-05 起每週六 02:00 一款）。

跟 v1（單純模仿）的差別：完整的學習迴圈——
  解構為什麼好玩 → 帶著設計理論做 → 出廠自評 → 玩家回饋餵回 → 下一款更好。

流程：
  1. fetch_trends 抓 App Store 台灣免費遊戲榜（失敗自動退回快取）
  2. 【解構】claude 從榜單挑一款，解構它的上癮機制 → 存 knowledge/deconstructions/
     （解構筆記會永久累積，工作室的遊戲設計功力隨時間變厚）
  3. 【設計+實作】claude 帶著三份資料生成遊戲：
     - knowledge/fun_principles.md（設計聖經：核心迴圈/near-miss/juice/難度曲線…）
     - 這次的解構筆記
     - knowledge/learnings.md 近六週的「設計類」教訓（玩家留言/修復根因/自評改進點；
       檢討會的流程建議不餵開發者——2026-09-05 餵料分流，見 recent_lessons）
  4. 【品管】Playwright 煙霧測試（噴錯不上架，重生一次）
  5. 【自評】claude 評審按五維量表打分（上手/juice/目標/難度/再一局，滿分 50），
     順便交出「怎麼玩／設計決策／第 3 分鐘壓力源／值不值得做大」給工廠備註用
  6. 【打磨】自評低於 POLISH_BAR 的作品：只修評審點名的「第一條缺陷」，
     修訂版品管通過就採用（2026-09-05 改制：不再拿自評分數當裁判——分數是雜訊）
  7. 上架 games.json + games.js，Telegram 推兩則介紹到 SlimeCat Studio 群組
     （①靈感/機制/變形/怎麼玩 ②工廠備註；沒設群組就推 Boss 私訊）

額度：claude -p 撞到訂閱額度時不是停產，而是照額度重置時間建一次性排程自動補跑
（同一天最多 MAX_QUOTA_RETRY 次），細節見 schedule_retry。

玩家回饋入口：python rate_game.py <遊戲名> <1-10> [評語] —— 玩家評分 > AI 自評 > 理論。
"""
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent      # factory/
ROOT = HERE.parent                          # SlimeCatArcade/
GAMES_DIR = ROOT / "games"
GAMES_JSON = ROOT / "games.json"
HISTORY_FILE = HERE / "history.json"
EMPTY_MCP = HERE / "empty_mcp.json"
KNOW = HERE / "knowledge"
KB_FILE = KNOW / "fun_principles.md"
LEARN_FILE = KNOW / "learnings.md"
DECON_DIR = KNOW / "deconstructions"
FAILED_DIR = HERE / "failed_outputs"   # 交稿解析失敗的原始輸出（驗屍用，最多留 10 份）
STUDIO_CFG = HERE / "studio_chat.json"  # SlimeCat Studio 群組 chat_id（gitignored；用 studio_setup.py 設）
USAGE_LOG = HERE / "usage.jsonl"        # 每次 claude -p 的用量流水（gitignored；Phase 2 對帳用）
RETRY_STATE = HERE / "retry_state.json"  # 撞額度自動補跑的當日計數（gitignored）
SITE_URL = "https://madeintw80.github.io/slimecat-arcade/"

sys.path.insert(0, str(HERE))
import fetch_trends                  # noqa: E402
import rebuild                       # noqa: E402
from validate_game import validate   # noqa: E402

# Telegram 推播走 Batnini 共用模組（沒設定也能跑，只是不推）
sys.path.insert(0, "C:/Users/User/projects/_common")
try:
    import batnini_telegram as tg
except Exception:
    tg = None

# claude CLI：先用 PATH 找，找不到用安裝時記下的絕對路徑（排程環境 PATH 可能不同）
CLAUDE = shutil.which("claude") or r"C:\Users\User\.local\bin\claude.exe"
# claude -p 子程序的工作目錄：故意設在 C:/Users/User「之外」（Public 下）。
# claude -p 會從 cwd 往上層找 CLAUDE.md；工廠在 ~/projects/SlimeCatArcade 跑，
# 往上會整份載入 root 的 Batnini CLAUDE.md（33.5k chars ≈ 每次白付 ~17.4k input tokens）。
# 子 Claude 工具全禁、純文字交稿（見 run_claude），cwd 只影響 CLAUDE.md 載入 → 搬出去零副作用。
# 註：只搬 claude -p 子程序的 cwd，工廠腳本本身照常在專案目錄跑（配方同 XianxiaSaga/llm.py）。
LLM_CWD = Path("C:/Users/Public/slimecat_llm_cwd")
LLM_CWD.mkdir(parents=True, exist_ok=True)
# 模型策略（2026-08-09 全鏈升一級：改三天一產後，省下的額度換每款品質；前配置 sonnet/opus/haiku）：
# 三個階段吃的模型分開挑——各自升到「該任務值得的最高一階」。
#   解構＝opus：企劃拆得更深，實作才有好料
#   實作＝fable（Mythos 級最前沿旗艦，CLI 別名 fable 已實測可用）：品質關鍵
#   自評＝sonnet：評得更準、改進點更有料——它同時是打磨迴圈的觸發依據
# run_claude 的 model 參數預設 MODEL_BUILD(fable) → fix_game / daily_feedback /
# weekly_review / original_mode 這些沒指定 model 的呼叫端同步升級（全鏈一致）。
# 2026-09-05 註：「全 fable 分級 effort」是 v3 Phase 2 的題目，跑三款對帳後再定；這裡先不動。
MODEL_DECON = "opus"      # 解構熱門遊戲
MODEL_BUILD = "fable"     # 設計＋實作遊戲（品質關鍵）
MODEL_CRITIC = "sonnet"   # 出廠五維自評
GEN_TIMEOUT = 3600        # 實作一整款遊戲的時間上限（fable 思考較久，放寬到 60 分鐘）
SMALL_TIMEOUT = 900       # 解構 / 評審這類小任務的上限
MAX_ATTEMPTS = 2          # 實作 + 驗證最多試幾次
POLISH_BAR = 40           # 自評低於這分數就觸發「打磨一輪」（0=關閉打磨、50=每款必磨）
MAX_QUOTA_RETRY = 2       # 撞額度時同一天最多自動補跑幾次（防無限迴圈燒額度）
CRITIC_HTML_CAP = 160000  # 評審讀多少字的原始碼（舊值 45000 只看得到大型遊戲的前 1/3）
# claude -p 單次回覆的輸出上限（預設 64,000，**思考 tokens 也算在內**）。2026-09-05 v3 首航：fable xhigh 寫 2,200 行
# 引擎在 64k 被截斷，CLI 還自己重試到 256k tokens／$15 才放棄；企劃書 max 也是 66k 被截斷才合約壞掉。
# 128,000 實測 fable 接受（超過模型上限 API 會直接拒絕，改這裡前先用小 prompt 試）。
MAX_OUTPUT_TOKENS = 128000

# 類型固定清單（2026-09-05）：以前讓模型自由填，59 款長出 33 種寫法
# （「益智（邏輯推理）」「街機／駕駛跑酷」…），大廳分類靠正則猜、猜錯就掉錯格。
# 現在只准這 14 個；模型亂填由 normalize_genre 對回來，大廳 index.html 的分類表跟這裡一致。
GENRES = ["益智", "消除", "合成", "觀察", "策略", "經營", "塔防", "放置",
          "動作", "街機", "反應", "跑酷", "生存", "放鬆"]
# 自由文字 → 固定類型的關鍵字對照。順序就是優先序（前面的比較專門，先比對）。
_GENRE_HINTS = [
    ("塔防", r"塔防|防守|防禦|守城"),
    ("策略", r"策略|抉擇|選擇|roguelite|路徑|回合|骰"),
    ("經營", r"經營|模擬|餐廳|開店|養成"),
    ("放置", r"放置|掛機"),
    ("益智", r"解謎|數獨|接龍|拼詞|文字|邏輯|推理|配對|記憶"),
    ("觀察", r"觀察|找碴|找不同|尋物|搜查"),
    ("合成", r"合成|配方|融合|合併"),
    ("消除", r"消除|三消|方塊|疊層"),
    ("跑酷", r"跑酷|駕駛|衝刺"),
    ("生存", r"生存|射擊|割草|防衛"),
    ("反應", r"反應|節奏|拍點|時機"),
    ("街機", r"街機|彈射|彈跳|投籃"),
    ("動作", r"動作|格鬥|閃避|物理"),
    ("放鬆", r"放鬆|解壓|療癒|休閒"),
    ("益智", r"益智|拼"),
]

# 開發者要看的教訓：近六週、最多 40 行、跳過「檢討會」開頭的行
# （2026-09-05 餵料分流：檢討會 85 行裡 2/3 是產能/流程抱怨，餵給開發者只會把它帶偏）
LESSON_DAYS = 42
LESSON_MAX = 40
LESSON_SKIP = ("檢討會",)


def log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------- claude -p 包裝
class QuotaError(RuntimeError):
    """claude -p 撞到訂閱額度（session／週額度）。resets_at＝額度重置的 epoch 秒（不明就 None）。"""

    def __init__(self, msg: str, resets_at=None):
        super().__init__(msg)
        self.resets_at = resets_at


class OutputLimitError(RuntimeError):
    """單次回覆超過輸出 tokens 上限（含思考）——交稿被截斷。呼叫端可用更緊的篇幅／effort 再試一次。"""


# 額度錯誤的文字特徵（9/2 實例：「You've hit your session limit · resets 3:40pm (Asia/Taipei)」）
_QUOTA_RE = re.compile(r"hit your .{0,24}limit|usage limit|rate.?limit|limit reached", re.I)
_RESET_TXT_RE = re.compile(r"resets?\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
_OUTLIMIT_RE = re.compile(r"exceeded the (\d+) output token maximum", re.I)

USAGE: list = []   # 本次程序內每次 claude -p 的用量（工廠備註要附本次 run 總用量）


def _parse_reset_text(text: str):
    """從「resets 3:40pm」這種文字推回 epoch（今天該時刻；已經過了就算明天）。"""
    m = _RESET_TXT_RE.search(text or "")
    if not m:
        return None
    hour, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if ap == "pm" and hour != 12:
        hour += 12
    if ap == "am" and hour == 12:
        hour = 0
    now = datetime.datetime.now()
    t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t <= now:
        t += datetime.timedelta(days=1)
    return t.timestamp()


def _record_usage(stage: str, model: str, effort, result, secs: float) -> None:
    """把這次呼叫的 token／費用（CLI result 事件自帶）記進 USAGE 與 usage.jsonl。"""
    u = (result or {}).get("usage") or {}
    rec = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "stage": stage, "model": model, "effort": effort or "",
        "in": int(u.get("input_tokens") or 0),
        "cache_w": int(u.get("cache_creation_input_tokens") or 0),
        "cache_r": int(u.get("cache_read_input_tokens") or 0),
        "out": int(u.get("output_tokens") or 0),
        "cost_usd": round(float((result or {}).get("total_cost_usd") or 0), 4),
        "turns": (result or {}).get("num_turns"),
        "secs": round(secs),
    }
    USAGE.append(rec)
    try:
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def usage_summary(recs=None) -> str:
    """本次 run 的用量一行（in＝輸入＋快取寫入、cache＝快取讀取、out＝輸出；$＝CLI 依牌價估）。"""
    recs = USAGE if recs is None else recs
    if not recs:
        return "（無紀錄）"

    def k(n):
        return f"{n/1000:.0f}k" if n >= 1000 else str(n)

    tin = sum(r["in"] + r["cache_w"] for r in recs)
    tcr = sum(r["cache_r"] for r in recs)
    tout = sum(r["out"] for r in recs)
    cost = sum(r["cost_usd"] for r in recs)
    return f"in {k(tin)}／cache {k(tcr)}／out {k(tout)} ≈ ${cost:.2f}（{len(recs)} 次呼叫）"


def run_claude(prompt: str, timeout: int, model: str = MODEL_BUILD,
               effort: str = "", stage: str = "", max_budget_usd: float = 0) -> str:
    """呼叫 claude -p，回傳模型印出的全部文字。

    2026-09-05 改走 --output-format stream-json：以前用預設 text 格式，模型分兩則訊息交稿時
    stdout 只印「最後一則」→ GAMEMETA 跟前半段遊戲一起消失（8/30 驗屍檔＝完整遊戲的最後
    2,154 bytes，有 </html> 沒 DOCTYPE）。stream-json 會把每一則 assistant 文字塊都吐出來，
    這裡照順序接起來；result 事件順便帶 usage／cost（記進 usage.jsonl），
    rate_limit_event 帶額度重置時間（撞額度時交給 schedule_retry 算補跑時刻）。
    effort：可選 low/medium/high/xhigh/max（空字串＝CLI 預設）。
    max_budget_usd：這一次呼叫最多花幾美元（CLI `--max-budget-usd`，0＝不設）——花費保險絲：
    截斷後 CLI 會自己重試，沒保險絲一次引擎可以燒到 $15（9/5 首航）。
    輸出上限走環境變數 CLAUDE_CODE_MAX_OUTPUT_TOKENS＝MAX_OUTPUT_TOKENS（預設 64k 不夠 v3 引擎用）。
    """
    # 子 Claude 是「純文字交稿」：禁用全部工具，防止它自作主張直接寫檔案
    # （2026-07-04 事故：開發者把遊戲直接寫進專案、stdout 沒交稿 → 驗收誤判失敗）
    deny = "Bash,Edit,Write,NotebookEdit,Read,Glob,Grep,WebFetch,WebSearch,Task,TodoWrite"
    cmd = [CLAUDE, "-p", "--model", model, "--disallowedTools", deny,
           "--strict-mcp-config", "--mcp-config", str(EMPTY_MCP),
           "--output-format", "stream-json", "--verbose"]
    if effort:
        cmd += ["--effort", effort]
    if max_budget_usd and max_budget_usd > 0:
        cmd += ["--max-budget-usd", f"{max_budget_usd:g}"]
    env = dict(os.environ)
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(MAX_OUTPUT_TOKENS)
    t0 = time.time()
    proc = subprocess.run(cmd, input=prompt, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=str(LLM_CWD), env=env)

    texts, result, reset_at = [], None, None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("type")
        if kind == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
        elif kind == "result":
            result = ev
        elif kind == "rate_limit_event":
            info = ev.get("rate_limit_info") or {}
            status = str(info.get("status") or "").lower()
            if status not in ("", "allowed", "allowed_warning") and info.get("resetsAt"):
                reset_at = float(info["resetsAt"])
    text = "\n".join(texts)
    if not text and result and isinstance(result.get("result"), str):
        text = result["result"]           # 沒抓到 assistant 事件（CLI 格式變了？）就退回 result 欄
    if not text and proc.returncode == 0 and (proc.stdout or "").strip() \
            and not proc.stdout.lstrip().startswith("{"):
        text = proc.stdout                # 完全不是 JSON（未知格式）→ 原文照收，別把成品丟掉
    _record_usage(stage or model, model, effort, result, time.time() - t0)

    failed = proc.returncode != 0 or bool(result and result.get("is_error"))
    if failed:
        err = ""
        if result and isinstance(result.get("result"), str):
            err = result["result"][-500:]
        if not err.strip():
            err = (proc.stderr or "")[-500:]
        if not err.strip():
            # claude -p 的錯誤（額度上限/API error）常印在 stdout、stderr 反而全空，
            # 只看 stderr 會把真正原因丟掉（2026-08-21 停產事故：log 只剩「code 1：」）
            err = (proc.stdout or "")[-500:]
        if "401" in err or "unauthorized" in err.lower():
            raise RuntimeError("claude CLI 401：token 過期，請跑 scripts/claude_relogin.bat 重登")
        if reset_at or _QUOTA_RE.search(err):
            raise QuotaError(f"claude -p 撞額度：{err.strip()[:200]}",
                             reset_at or _parse_reset_text(err))
        m = _OUTLIMIT_RE.search(err)
        if m:
            raise OutputLimitError(f"單次回覆超過 {m.group(1)} tokens 輸出上限（思考也算）：{err.strip()[:160]}")
        raise RuntimeError(f"claude -p 失敗 (code {proc.returncode})：{err}")
    if not text.strip():
        raise RuntimeError("claude -p 回傳空白（stream-json 裡沒有任何文字塊）")
    return text


def tail(path: Path, lines: int = 60) -> str:
    """讀檔案最後 N 行（保留給舊呼叫端；開發者餵料改用 recent_lessons）。"""
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-lines:])


def recent_lessons(days: int = LESSON_DAYS, max_lines: int = LESSON_MAX,
                   skip=LESSON_SKIP) -> str:
    """learnings.md 裡近 days 天、跳過 skip 類型（預設跳「檢討會」）的教訓，最多 max_lines 行。

    每行格式「- YYYY-MM-DD 類型《…》…」，類型＝日期後第一個詞（AI 自評／玩家留言／修復／打磨／檢討會）。
    """
    if not LEARN_FILE.exists():
        return ""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    keep = []
    for line in LEARN_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- (\d{4}-\d{2}-\d{2}) (\S+)", line)
        if not m or m.group(1) < cutoff:
            continue
        if any(m.group(2).startswith(s) for s in skip):
            continue
        keep.append(line)
    return "\n".join(keep[-max_lines:])


def section(doc: str, key: str, limit: int = 160) -> str:
    """從解構筆記／企劃書抓「## 標題含 key」那一節的正文，壓成一段、截 limit 字（介紹推播用）。"""
    m = re.search(rf"^##[^\n]*{re.escape(key)}[^\n]*\n(.*?)(?=^## |\Z)", doc or "", re.S | re.M)
    if not m:
        return ""
    body = re.sub(r"\s+", " ", m.group(1)).strip(" -*")
    return body[:limit].rstrip() + "…" if len(body) > limit else body


def normalize_genre(text: str) -> str:
    """把模型自由填的類型對回 GENRES 固定清單（對不到一律「益智」）。"""
    t = str(text or "").strip()
    if t in GENRES:
        return t
    for name, pat in _GENRE_HINTS:
        if re.search(pat, t, re.I):
            return name
    return "益智"


# ---------------------------------------------------------------- 解構
def trend_chart(trends: dict) -> str:
    """把 App Store 榜＋Steam 榜排成策劃看的清單文字（2026-09-05 v3 Phase 1：一榜合併、策劃自己挑）。"""
    lines = [f"【App Store 台灣免費遊戲榜】（來源 {trends.get('source', '?')}）"]
    for g in (trends.get("games") or [])[:40]:
        s = f"{g['rank']}. {g['name']}（{g.get('artist', '')}）"
        if g.get("summary"):
            s += f"：{g['summary'][:100]}"
        lines.append(s)
    steam = (trends.get("steam") or {}).get("games") or []
    if steam:
        lines.append("")
        lines.append("【Steam 榜：熱銷＋新品熱門】（PC 大型遊戲——挑它時要把「一套系統」濃縮成一個核心迴圈；"
                     "避開 3A 敘事、連線對戰、純模擬器）")
        for g in steam:
            s = f"S{g['rank']}. [{g.get('list', '')}] {g['name']}"
            if g.get("genres"):
                s += f"｜{'/'.join(g['genres'][:4])}"
            if g.get("summary"):
                s += f"：{g['summary'][:100]}"
            lines.append(s)
    return "\n".join(lines)


def stage_deconstruct(trends: dict, history: dict, past_games: list, pick: str = "") -> dict:
    """挑一款熱門遊戲並解構其上癮機制。回傳 {source,title,genre,origin,doc}。

    pick：Boss 點名（「解構 <遊戲名>」指令）時直接解構那一款，不看榜單（trends 可為 None）。
    origin：appstore／steam／named（Boss 點名）——工廠備註與筆記會標來源，方便之後對帳哪種靈感做得好。
    """
    used = [u["inspiration"] for u in history["used"]]
    past = [f"《{g['title']}》({g.get('genre','')})：{g.get('desc','')}" for g in past_games]
    if pick:
        chart_block = (f"Boss 點名要解構的遊戲：《{pick}》（不論它在不在榜上；手遊／PC／主機皆可，"
                       f"用你對這款遊戲的了解來拆；若是大型遊戲，挑「一套最上癮的系統」濃縮成核心迴圈）")
        task_line = f"任務：解構《{pick}》"
    else:
        chart_block = trend_chart(trends)
        task_line = ("任務：從兩份榜單挑一款「核心玩法能濃縮成 30 秒上手網頁小遊戲」的遊戲\n"
                     "（避開：博弈/賭場、需連線帳號、重度 RPG/卡牌收集、純 IP 授權作、成人內容）")

    prompt = f"""你是「SlimeCat 遊戲工作室」的首席遊戲策劃。今天是 {datetime.date.today().isoformat()}。

{chart_block}

已用過的靈感（避開）：{json.dumps(used, ensure_ascii=False)}
本站已有的遊戲（新遊戲的核心機制不可跟它們重複，多樣性也是留存）：
{chr(10).join(past) if past else "（還沒有）"}

{task_line}，
然後寫一份**解構筆記**：不是描述它有什麼功能，而是拆解「為什麼會好玩、為什麼讓人上癮」。

輸出格式（嚴格遵守，前四行是標頭，之後是筆記本體；直接印出文字、不要使用任何工具）：
SOURCE: <原作名稱>
ORIGIN: <appstore 或 steam（它在哪份榜單上；Boss 點名的寫 named）>
TITLE: <我們的變形版建議中文名（全新命名；不可含原作名，也不可與原作名音近/形近/直譯——商標紅線）>
GENRE: <只能從這個清單挑一個：{'/'.join(GENRES)}>

# 解構：<原作名>
## 核心迴圈（一圈幾秒？操作→回饋→獎勵怎麼轉？）
## 上癮機制（用心理學拆：near-miss？歸因於己？指數獎勵？損失趨避？收集慾？）
## 難度與節奏（怎麼讓新手活過前 15 秒、又讓老手 2 分鐘後不無聊？）
## 可偷的設計（3-5 條，我們的單檔小遊戲做得到的）
## 不可行的部分（原作有但我們該捨棄的，為什麼）
## 我們的變形版一句話企劃（主題與美術自由挑最適合這個機制的，核心樂趣要保留哪一條）
"""
    out = run_claude(prompt, SMALL_TIMEOUT, model=MODEL_DECON, stage="decon")
    src = re.search(r"^SOURCE:\s*(.+)$", out, re.M)
    org = re.search(r"^ORIGIN:\s*(.+)$", out, re.M)
    ttl = re.search(r"^TITLE:\s*(.+)$", out, re.M)
    gnr = re.search(r"^GENRE:\s*(.+)$", out, re.M)
    if not src:
        raise ValueError("解構輸出缺 SOURCE 標頭")
    doc_start = out.find("# 解構")
    doc = out[doc_start:] if doc_start >= 0 else out
    origin = (org.group(1).strip().lower() if org else "")
    if pick:
        origin = "named"
    elif origin not in ("appstore", "steam"):
        origin = "appstore"
    return {
        "source": src.group(1).strip(),
        "title": (ttl.group(1).strip() if ttl else ""),
        "genre": normalize_genre(gnr.group(1) if gnr else ""),
        "origin": origin,
        "doc": doc.strip(),
    }


def save_decon(decon: dict) -> Path:
    """把解構筆記存進 knowledge/deconstructions/：<日期>-<原作 slug>.md（正文）＋同名 .json 側檔（標頭）。

    側檔讓 make_game_v3.py --decon <筆記> 能拿回 source／title／genre／origin；
    正文格式跟以前完全一樣（檢討會、section() 都照舊讀）。
    """
    DECON_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    slug = re.sub(r"[^\w一-鿿-]+", "_", decon["source"])[:40]
    path = DECON_DIR / f"{today}-{slug}.md"
    path.write_text(decon["doc"], encoding="utf-8")
    side = {k: decon.get(k, "") for k in ("source", "title", "genre", "origin")}
    side["date"] = today
    path.with_suffix(".json").write_text(json.dumps(side, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 設計 + 實作
def stage_generate(decon: dict, past_games: list, feedback: str = ""):
    """帶著設計聖經 + 解構筆記 + 教訓生成完整遊戲。回傳 (meta, html)。"""
    kb = KB_FILE.read_text(encoding="utf-8") if KB_FILE.exists() else ""
    learn = recent_lessons()
    past = [f"《{g['title']}》({g.get('genre','')})" for g in past_games]
    fb = (f"\n⚠️ 上一次生成沒通過品管，錯誤如下，請避免同類問題：\n{feedback}\n"
          if feedback else "")
    genre = normalize_genre(decon.get("genre"))

    prompt = f"""你是「SlimeCat 遊戲工作室」的資深遊戲開發者。要做一款比本站過去所有作品都更好玩的小遊戲。

═══ 設計聖經（做之前先內化）═══
{kb}

═══ 這次的解構筆記（策劃已完成）═══
{decon['doc']}

═══ 近期的教訓與玩家回饋（最高優先級，玩家評分 > 理論）═══
{learn if learn else "（還沒有）"}

═══ 本站已有遊戲（核心機制不可重複）═══
{chr(10).join(past) if past else "（無）"}
{fb}
任務：把解構筆記裡「我們的變形版企劃」實作成完整單檔 HTML5 小遊戲。
建議名稱《{decon['title'] or '（自訂）'}》。美術風格完全自由（不必是史萊姆貓）：
挑最能放大這個機制的主題與視覺，canvas 畫或 emoji 皆可；絕不可用原作名稱/角色/美術/音樂。
版權紅線：只學「機制與心理學」、不抄「表達」——遊戲名不可與原作音近/形近/直譯；
不可複製原作的特徵性視覺（配色組合/圖示造型）、具體數值表與關卡佈局。
實作時逐條對照設計聖經第三節「出貨檢查清單」——特別是：
前 15 秒不會死、每個互動都有 juice、Game Over 顯示差 X 分破紀錄、重開一鍵零等待、
第 3 分鐘要有新的壓力源（新機制／加速／縮圈／限時擇一，別讓後期平掉）。

硬性規格（違反任何一條就算失敗）：
- 單一 HTML 檔內含全部 CSS/JS；零外部資源（不可用 CDN、外部圖片、字型、音檔；音效用 WebAudio 合成）
- 遊戲畫面用 <canvas>，寬 400 高 600 直式，JS 把 canvas 等比縮放到適合視窗
- 手機觸控與電腦鍵盤都要能玩；canvas 設 touch-action:none 防頁面捲動
- 主迴圈不可假設 60fps：用固定時間步長（fixed timestep accumulator）或 deltaTime，
  120Hz 螢幕的手機不可變兩倍速；監聽 pointercancel/blur 清掉輸入狀態（防卡鍵/自走）
- 高解析度輸出（不可省，省了高 DPI 手機上字和圖全糊）：canvas 實體緩衝 = 顯示尺寸 ×
  devicePixelRatio（cap 3），再用 ctx.setTransform(s*dpr,0,0,s*dpr,0,0) 讓邏輯座標維持 400×600；
  輸入座標一律用 getBoundingClientRect 比例換算回邏輯座標（不可拿 canvas.width 算）
- 標題畫面（遊戲名＋一句話規則＋繁中操作說明＋點擊開始）；即時分數；localStorage 最高分；Game Over 可一鍵重來
- 介面文字一律繁體中文；程式碼加簡短繁中註解
- 30 秒上手，一局約 1~3 分鐘
- 不可用 alert/confirm/prompt；不可出現 console.error 或未捕捉例外
- 頁面左上角放回大廳連結：<a href="../../index.html">← 回遊戲區</a>
- 一局結束（Game Over）時加一行 `if (window.SC) SC.over(最終分數);`（匿名數據回報，SC 由站台注入）

🔴 交付方式：你唯一的交付物是「印出的文字」。不要使用任何工具、不要建立或修改任何檔案
（你也沒有寫檔權限），把完整 HTML 當純文字印出來就是交稿。**整份交稿放在同一則回覆裡**，
不要分成兩則、不要中途停下來問問題。

輸出格式（嚴格遵守）：
- 不要 markdown code fence、不要任何解說文字，直接輸出檔案內容
- 檔案第一行必須是這個中繼資料註解（JSON 單行）：
<!--GAMEMETA {{"title":"遊戲中文名","emoji":"一個代表emoji","genre":"{genre}","inspiration":"{decon['source']}","desc":"一句話介紹(30字內)"}}-->
- 第二行開始就是 <!DOCTYPE html> 起頭的完整網頁
- 🔴 交稿前最後自檢：輸出的「第 1 行」必須就是那行 <!--GAMEMETA …--> 中繼資料註解
  （先印它、再印網頁）；漏了這行，整包交稿直接作廢
"""
    out = run_claude(prompt, GEN_TIMEOUT, model=MODEL_BUILD, stage="build")
    try:
        return extract(out)
    except ValueError as e:
        body = split_html(out)
        if body is None:
            p = save_failed_output(out, "build")
            log(f"  🗄️ 原始輸出已存 failed_outputs/{p.name}（驗屍用）")
            raise
        # GAMEMETA 壞了但遊戲本體完整：15 分鐘的 fable 成品別整包丟，
        # 用便宜模型從成品反推補一份 meta，照常走後面的品管把關
        log(f"  🚑 {e} → HTML 本體完整，用 {MODEL_CRITIC} 補產 GAMEMETA 救回成品")
        save_failed_output(out, "build-rescued")
        return rescue_meta(body, decon)


def extract(output: str):
    """從 claude 輸出撈出 GAMEMETA 與 HTML 本體（容忍 code fence / 前置廢話）。"""
    i = output.find("<!--GAMEMETA")
    if i < 0:
        raise ValueError("輸出裡找不到 GAMEMETA 標頭")
    html = output[i:].strip()
    html = re.sub(r"\n```\s*$", "", html)  # 去掉尾端可能多出的 code fence
    m = re.match(r"<!--GAMEMETA\s*(\{.*?\})\s*-->", html, re.S)
    if not m:
        raise ValueError("GAMEMETA 不是合法 JSON 註解")
    meta = json.loads(m.group(1))
    for k in ("title", "inspiration"):
        if not meta.get(k):
            raise ValueError(f"GAMEMETA 缺 {k}")
    meta.setdefault("emoji", "🎮")
    meta["genre"] = normalize_genre(meta.get("genre"))
    meta.setdefault("desc", "")
    if "<canvas" not in html.lower():
        raise ValueError("HTML 裡沒有 canvas")
    return meta, html


def split_html(output: str):
    """撈出完整的 HTML 本體（GAMEMETA 壞掉時的救援前置檢查）。

    要求 <!DOCTYPE/<html 起頭、</html> 收尾、含 canvas 才算「本體完整」；
    缺一就回 None——殘缺的輸出救回來也過不了品管，不值得花救援呼叫。
    """
    low = output.lower()
    i = low.find("<!doctype html")
    if i < 0:
        i = low.find("<html")
    if i < 0:
        return None
    body = re.sub(r"\n```\s*$", "", output[i:].strip())
    if "</html>" not in body.lower() or "<canvas" not in body.lower():
        return None
    return body


def save_failed_output(out: str, stage: str) -> Path:
    """交稿解析失敗時把原始輸出存檔（事後驗屍用），只留最新 10 份。

    以前解析失敗原始輸出直接丟掉，fable 到底交了什麼永遠查不到
    （2026-08-18/21 連環漏 GAMEMETA 就是這樣變成懸案的）。
    """
    FAILED_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    p = FAILED_DIR / f"{ts}-{stage}.txt"
    p.write_text(out, encoding="utf-8")
    for old in sorted(FAILED_DIR.glob("*.txt"))[:-10]:
        old.unlink()
    return p


def rescue_meta(body: str, decon: dict):
    """開發者漏交 GAMEMETA 時，用便宜模型從成品 HTML 反推補一份 meta。

    genre/inspiration 不用問模型——解構筆記本來就知道；只要它從成品
    讀出 title/emoji/desc。回傳格式同 extract()：(meta, 含標頭的完整 HTML)。
    """
    prompt = f"""以下是一款 canvas 小遊戲的完整原始碼。讀完後只輸出一行 JSON（不要解說、不要 code fence）：
{{"title":"遊戲中文名(從標題畫面或<title>取)","emoji":"一個代表emoji","desc":"一句話介紹(30字內)"}}

原始碼：
{body[:45000]}
"""
    out = run_claude(prompt, SMALL_TIMEOUT, model=MODEL_CRITIC, stage="rescue-meta")
    i, j = out.find("{"), out.rfind("}")
    got = json.loads(out[i:j + 1])
    meta = {
        "title": str(got.get("title", "")).strip(),
        "emoji": str(got.get("emoji", "")).strip() or "🎮",
        "genre": normalize_genre(decon.get("genre")),
        "inspiration": decon.get("source", ""),
        "desc": str(got.get("desc", "")).strip()[:60],
    }
    if not meta["title"] or not meta["inspiration"]:
        raise ValueError("救援補產的 GAMEMETA 仍缺 title/inspiration")
    header = "<!--GAMEMETA " + json.dumps(meta, ensure_ascii=False) + "-->"
    return meta, header + "\n" + body


# ---------------------------------------------------------------- 出廠自評
def stage_critic(html: str, meta: dict):
    """AI 評審按五維量表打分＋交工廠備註素材。失敗不擋出貨（fail-open），回傳 dict 或 None。

    回傳欄位：scores/total/fixes/verdict（原本就有）＋ howto（怎麼玩）／design_choices（設計決策）／
    pressure_3min（第 3 分鐘壓力源）／scale_up（值不值得做大）——給 Telegram 第二則「工廠備註」用。
    """
    kb_scale = ("五維量表：上手(不看說明能玩?規則一句話?)、Juice(每個操作有視聽回饋?得分有爽感演出?)、"
                "目標(隨時知道為何而玩?)、難度(前15秒安全?2分鐘後仍有挑戰?)、再一局(near-miss設計?重開零摩擦?)")
    prompt = f"""你是嚴格的遊戲評審。以下是一款 canvas 小遊戲《{meta['title']}》的完整原始碼，
用讀 code 的方式評估它「實際玩起來」的體驗（想像執行結果，別只看有沒有寫註解）。

{kb_scale}

每維 1-10 分（8 分以上必須真的出色才給；可以給 .5 半分）。只輸出一行 JSON，格式：
{{"scores":{{"onboarding":n,"juice":n,"goal":n,"difficulty":n,"one_more":n}},"total":n,"fixes":["最重要的改進點1（要具體到工程師能直接改）","改進點2","改進點3"],"verdict":"一句話總評","howto":"給玩家看的一句話怎麼玩（30字內）","design_choices":["這款最關鍵的設計決策或取捨1（從程式碼看得出來的）","決策2"],"pressure_3min":"第 3 分鐘的壓力源是什麼？沒有就寫『無：後期會平掉』（30字內）","scale_up":{{"worth":true或false,"why":"值不值得做成大型版（關卡/波次/升級/圖鑑）的一句理由"}}}}

原始碼：
{html[:CRITIC_HTML_CAP]}
"""
    try:
        out = run_claude(prompt, SMALL_TIMEOUT, model=MODEL_CRITIC, stage="critic")
        i, j = out.find("{"), out.rfind("}")
        crit = json.loads(out[i:j + 1])
        # 🔴 不信模型自報的 total：haiku 常把單維 1-10 分當成總分回（例 total=7），
        # 被當成 50 分制上架 → 公開卡片顯示 6/7/8 這種假分數。
        # 改成先驗五維齊全且各在 1-10，再一律自己加總（忽略模型自報 total）。
        # 2026-09-05：半分（7.5）改四捨五入收下——以前整包退件，兩款網頁 8 分的好遊戲自評因此變 None。
        scores = crit.get("scores") or {}
        dims = ("onboarding", "juice", "goal", "difficulty", "one_more")
        clean = {}
        for d in dims:
            v = scores.get(d)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= v <= 10:
                raise ValueError(f"自評維度 {d}={v!r} 不在 1-10（五維不齊或超範圍）")
            clean[d] = int(math.floor(v + 0.5))   # 四捨五入（7.5→8），不是 banker's rounding
        crit["scores"] = clean
        crit["total"] = sum(clean.values())   # 一律五維加總（滿分 50），不看模型自報 total
        crit["fixes"] = [str(x) for x in (crit.get("fixes") or []) if str(x).strip()][:3]
        crit["verdict"] = str(crit.get("verdict") or "")[:120]
        crit["howto"] = str(crit.get("howto") or "")[:60]
        crit["design_choices"] = [str(x)[:80] for x in (crit.get("design_choices") or [])][:3]
        crit["pressure_3min"] = str(crit.get("pressure_3min") or "")[:60]
        su = crit.get("scale_up") if isinstance(crit.get("scale_up"), dict) else {}
        crit["scale_up"] = {"worth": bool(su.get("worth")), "why": str(su.get("why") or "")[:80]}
        return crit
    except Exception as e:
        log(f"  ⚠️ 自評失敗（不擋出貨）：{e}")
        return None


# ---------------------------------------------------------------- 打磨（低分才觸發）
def stage_polish(html: str, meta: dict, crit: dict) -> str:
    """把評審點名的「第一條缺陷」餵回開發者，針對「這一款」修一版。回傳修訂後的完整 HTML。

    2026-08-09 三天一產改制：以前評審的 fixes 只餵給下一款，這一款照樣原樣上架；
    現在自評低於 POLISH_BAR 的作品出廠前多吃一輪修訂。
    2026-09-05 改制：只修第一條缺陷（改動小＝不容易弄壞），修訂版品管通過就採用——
    以前要「重評分數變高才換版」，但 7 次觸發只換版 2 次、都在評審雜訊範圍內，分數當裁判無效。
    """
    fixes = crit.get("fixes") or []
    fix0 = fixes[0] if fixes else "針對分數最低的維度自行強化一項"
    prompt = f"""你是「SlimeCat 遊戲工作室」的資深遊戲開發者。你剛完成的小遊戲《{meta['title']}》
出廠評審給了 {crit['total']}/50，評審點名了一條最重要的缺陷。請針對這一條修訂一版。

═══ 這次修訂的唯一目標（只處理這一條，其他的別動）═══
{fix0}

評審總評：{crit.get('verdict', '')}
各維分數（1-10）：{json.dumps(crit.get('scores', {}), ensure_ascii=False)}

═══ 目前的完整原始碼 ═══
{html}

修訂規則：
- 只做「修這一條缺陷」需要的改動，改動越小越好；不可重寫成另一款遊戲、不可順手大改其他系統
- 原本能玩的功能不可弄壞；維持原有硬性規格（單檔零外部資源／canvas 400×600／
  fixed timestep 不可假設 60fps／DPR 高解析／繁中介面／SC.over 回報／localStorage 最高分）
- 遊戲名與第一行 GAMEMETA 註解保持原樣

🔴 交付方式：你唯一的交付物是「印出的文字」。不要使用任何工具（你也沒有寫檔權限）。
整份交稿放在同一則回覆裡，不要分成兩則。
輸出格式：不要 code fence、不要任何解說文字；第一行是原本的 GAMEMETA 註解，第二行起是完整 HTML。
交稿前最後自檢：輸出第 1 行必須就是原本那行 <!--GAMEMETA …-->，漏了整包作廢。
"""
    out = run_claude(prompt, GEN_TIMEOUT, model=MODEL_BUILD, stage="polish")
    try:
        _, html2 = extract(out)   # meta 一律沿用原版（防模型偷改名），只取修訂後的 HTML
    except ValueError as e:
        body = split_html(out)
        m = re.match(r"<!--GAMEMETA.*?-->", html, re.S)
        if body is None or m is None:
            save_failed_output(out, "polish")
            raise
        # 打磨版只是漏抄標頭：meta 本來就沿用原版，接回原標頭繼續品管
        log(f"  🚑 {e} → 打磨版 HTML 完整，接回原版 GAMEMETA 續跑")
        html2 = m.group(0) + "\n" + body
    return html2


# ---------------------------------------------------------------- 工具
def next_id(date_str: str, games: list) -> str:
    n = sum(1 for g in games if g["id"].startswith(date_str)) + 1
    return f"{date_str}-{n:03d}"


def reserve_game_dir(date_str: str):
    """撥一個今天的新編號並「建資料夾佔位」，回傳 (gid, gdir)。

    防並行撞號的兩道保險（2026-07-10 健檢追蹤項）：
    1. 撥號當下才重讀最新 games.json——不能用開場讀的舊快照，因為生成一款
       要 20~45 分鐘，期間可能有別輪生產已上架新遊戲；games + retired 一起算，
       下架遊戲的編號不重用（資料夾可能還在）
    2. mkdir(exist_ok=False) 由作業系統保證原子性：兩個程序搶同一個資料夾
       只有一個會成功，搶輸的拿到 FileExistsError → 序號 +1 重試，
       所以編號跟資料夾永遠一對一，不會互相覆寫對方的遊戲檔案
    """
    fresh = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    gid = next_id(date_str, fresh.get("games", []) + fresh.get("retired", []))
    while True:
        gdir = GAMES_DIR / gid
        try:
            gdir.mkdir(parents=True, exist_ok=False)
            return gid, gdir
        except FileExistsError:
            # 撞名＝這個號碼被並行生產（或殘留資料夾）佔走了 → +1 再試
            gid = f"{date_str}-{int(gid.rsplit('-', 1)[1]) + 1:03d}"


def inject_stats(html: str) -> str:
    """把數據回報的 script 標籤插進 </body> 前（生成器不用知道 stats 的存在）。"""
    tags = ('<script src="../../sc_config.js"></script>\n'
            '<script src="../../stats.js"></script>\n')
    i = html.lower().rfind("</body>")
    return html[:i] + tags + html[i:] if i >= 0 else html + "\n" + tags


def append_learning(line: str) -> None:
    with LEARN_FILE.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


# ---------------------------------------------------------------- Telegram
def studio_chat():
    """SlimeCat Studio 群組的 chat_id（factory/studio_chat.json，用 studio_setup.py 設）；沒設回 None。"""
    try:
        cid = json.loads(STUDIO_CFG.read_text(encoding="utf-8")).get("chat_id")
        return str(cid) if cid else None
    except (OSError, ValueError, AttributeError):
        return None


def send_public(text: str, photo: Path = None) -> bool:
    """對外（玩家群）推播：有設 Studio 群組就送群組，沒設就送預設對象（Boss 私訊）。

    帶圖時 Telegram caption 上限 1024 字：文字太長就「圖＋短說明」再補一則全文。
    """
    if not (tg and tg.available()):
        return False
    cid = studio_chat()
    try:
        if photo is not None and photo.exists():
            if len(text) <= 1000:
                return tg.push_photo(photo, caption=text, chat_id=cid)
            tg.push_photo(photo, caption=text.splitlines()[0][:200], chat_id=cid)
        return tg.send(text, chat_id=cid)
    except Exception as e:
        log(f"⚠️ Telegram 推播失敗：{e}")
        return False


def notify_release(entry: dict, crit, decon: dict, polish_note: str = "", extra: str = "") -> None:
    """新品出爐推兩則（2026-09-05 4B）：①給玩家看的介紹 ②工廠備註（設計決策／壓力源／評審／值不值得做大／用量）。

    extra：v3 生產線多交代的幾行（內容包規模／評審是誰／稽核結果），接在工廠備註「用量」之後。
    """
    if not (tg and tg.available()):
        return
    doc = decon.get("doc", "")
    mech = section(doc, "核心迴圈") or section(doc, "上癮機制")
    twist = section(doc, "變形版")
    howto = (crit or {}).get("howto") or entry.get("desc", "")
    url = f"{SITE_URL}games/{entry['id']}/index.html"
    intro = (f"🎮 本週新作《{entry['title']}》{entry['emoji']}\n"
             f"{entry['desc']}\n\n"
             f"💡 靈感：{entry['inspiration']}\n"
             f"🔁 機制：{mech or '（見解構筆記）'}\n"
             f"🌀 變形：{twist or '（見企劃）'}\n"
             f"🕹️ 怎麼玩：{howto}\n\n"
             f"👉 {url}\n"
             f"玩完到大廳按「評分」留一句，工廠會照留言改。")
    if crit:
        choices = "\n".join(f"• {c}" for c in crit.get("design_choices") or []) or "• （評審沒列）"
        su = crit.get("scale_up") or {}
        worth = "✅ 值得" if su.get("worth") else "❌ 先不用"
        polish = f"修了「{polish_note}」，品管通過採用" if polish_note else "未觸發／未採用"
        notes = (f"🏭 工廠備註《{entry['title']}》\n"
                 f"設計決策：\n{choices}\n"
                 f"第 3 分鐘壓力源：{crit.get('pressure_3min') or '（未評）'}\n"
                 f"評審看法：{crit['total']}/50 — {crit.get('verdict', '')}\n"
                 f"最想修：{(crit.get('fixes') or ['—'])[0]}\n"
                 f"打磨：{polish}\n"
                 f"值不值得做大：{worth} — {su.get('why', '')}\n"
                 f"用量：{usage_summary()}\n"
                 + (extra.rstrip() + "\n" if extra else "")
                 + f"要做大就說「做大 {entry['title']}」")
    else:
        notes = (f"🏭 工廠備註《{entry['title']}》\n評審這次沒交卷（自評失敗，不擋出貨）。\n"
                 f"用量：{usage_summary()}"
                 + (("\n" + extra.rstrip()) if extra else ""))
    shot = HERE / "shots" / f"{entry['id']}.png"
    send_public(intro, photo=shot)
    send_public(notes)


def notify_fail(reason: str) -> None:
    """生產失敗告警：一律送 Boss 私訊（預設對象），不進玩家群。"""
    if not (tg and tg.available()):
        return
    try:
        tg.send(f"🏭⚠️ SlimeCat 遊戲工廠這輪生產失敗（已重試）。\n"
                f"原因：{reason[:300]}\n詳見 factory/factory.log")
    except Exception:
        pass


# ---------------------------------------------------------------- 撞額度自動補跑
_RETRY_BATS = {"factory": ROOT / "run_factory.bat",
               "weekly": ROOT / "run_weekly.bat",
               "feedback": ROOT / "run_feedback.bat"}


def _retry_task(kind: str) -> str:
    return f"SlimeCat Retry {kind}"   # 前綴 SlimeCat＝心跳監控 WATCH_PREFIXES 自動涵蓋


def _schtasks(*args) -> tuple:
    proc = subprocess.run(["schtasks", *args], capture_output=True)
    return proc.returncode, (proc.stdout + proc.stderr).decode("cp950", errors="replace").strip()


def schedule_retry(kind: str, resets_at, reason: str) -> bool:
    """撞額度：照重置時間＋10 分鐘建一次性 schtasks 自動補跑，回傳是否已排。

    以前撞額度＝當輪停產、等 Boss 回來喊「生一個新遊戲」（8/18、8/21、9/2 三次）。
    現在：kind ∈ factory/weekly/feedback → 對應 run_*.bat；同一天最多 MAX_QUOTA_RETRY 次
    （計數在 retry_state.json），超過就放棄並推警報。重置時間不明就 3 小時後再試。
    排到補跑時呼叫端回 0（失敗已被接手，別讓心跳監控紅一整週）；補跑那輪自己有結果碼。
    """
    bat = _RETRY_BATS[kind]
    today = datetime.date.today().isoformat()
    state = {}
    try:
        state = json.loads(RETRY_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if state.get("date") != today:
        state = {"date": today, "count": {}}
    n = int(state.get("count", {}).get(kind, 0))
    if n >= MAX_QUOTA_RETRY:
        log(f"⛔ 撞額度，今天已自動補跑 {n} 次，放棄（明天排程再試）：{reason[:120]}")
        notify_fail(f"撞額度且今天已自動補跑 {n} 次，放棄：{reason[:150]}")
        return False

    now = datetime.datetime.now()
    when = (datetime.datetime.fromtimestamp(resets_at) if resets_at
            else now + datetime.timedelta(hours=3)) + datetime.timedelta(minutes=10)
    if when < now + datetime.timedelta(minutes=2):
        when = now + datetime.timedelta(minutes=5)
    task = _retry_task(kind)
    rc, out = _schtasks("/Create", "/TN", task, "/TR", str(bat), "/SC", "ONCE",
                        "/SD", when.strftime("%Y/%m/%d"), "/ST", when.strftime("%H:%M"), "/F")
    if rc != 0:
        log(f"❌ 建補跑排程失敗（{out[-200:]}）：{reason[:120]}")
        notify_fail(f"撞額度且補跑排程建不起來：{out[-150:]}")
        return False
    state["count"][kind] = n + 1
    RETRY_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"⏳ 撞額度，已排 {when:%m/%d %H:%M} 自動補跑（今天第 {n + 1} 次）：{reason[:120]}")
    if tg and tg.available():
        try:
            tg.send(f"🏭⏳ SlimeCat 撞額度：{reason[:120]}\n"
                    f"已排 {when:%m/%d %H:%M} 自動補跑（今天第 {n + 1}/{MAX_QUOTA_RETRY} 次），不用手動喊。")
        except Exception:
            pass
    return True


def clear_retry(kind: str) -> None:
    """開跑時清掉上一次的一次性補跑排程（ONCE 跑過就不會再觸發，但留著會佔心跳監控的結果碼）。"""
    _schtasks("/Delete", "/TN", _retry_task(kind), "/F")


# ---------------------------------------------------------------- 生產管線（共用）
def produce_from_decon(decon: dict) -> int:
    """帶著企劃資料跑完 設計→實作→品管→自評→(打磨)→上架→部署→推播。

    decon = {source, title, genre, doc}——doc 是解構筆記（臨摹模式，make_game）
    或原創企劃書（原創模式，original_mode.py），管線本身完全相同。
    回傳 0＝上架完成或已排補跑；1＝失敗。
    """
    # 這份 data 只當 prompt 素材（給模型看「本站已有哪些遊戲」，舊幾分鐘沒關係）；
    # 撥編號、上架寫檔都會「當下重讀最新檔」，不吃這份舊快照（防並行蓋檔，見下方註解）
    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    today = datetime.date.today().isoformat()
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"🛠️ 第 {attempt}/{MAX_ATTEMPTS} 次實作（model={MODEL_BUILD}，最多等 {GEN_TIMEOUT//60} 分鐘）…")
        try:
            meta, html = stage_generate(decon, data["games"], feedback)
        except QuotaError as e:
            # 撞額度再重試也是撞：直接排補跑，這輪收工
            log(f"  ⏳ 實作撞額度：{e}")
            return 0 if schedule_retry("factory", e.resets_at, str(e)) else 1
        except Exception as e:
            log(f"  ❌ 實作失敗：{e}")
            feedback = str(e)
            continue

        meta["inspiration"] = decon["source"]  # 靈感欄以策劃解構為準
        gid, gdir = reserve_game_dir(today)   # 撥號＋資料夾佔位（防並行撞號，見函式註解）
        (gdir / "index.html").write_text(inject_stats(html), encoding="utf-8")
        log(f"  📝 《{meta['title']}》→ games/{gid}/")

        # ── 品管 ──
        try:
            ok, errs = validate(gdir / "index.html", shot_name=gid)
        except Exception as e:
            # Playwright 本身炸掉（沒裝好／瀏覽器當掉）就視同品管失敗，走重試流程；
            # 別讓例外往上炸穿整條 pipeline（否則 notify_fail 不會發、零告警）。
            ok, errs = False, [f"playwright 掛了：{e}"]
        if not ok:
            log(f"  ❌ 煙霧測試失敗：{errs}")
            feedback = "\n".join(errs)[:800]
            shutil.rmtree(gdir, ignore_errors=True)
            continue

        # ── 出廠自評 ──
        log("🧐 評審自評中…")
        crit = stage_critic(html, meta)

        # ── 打磨迴圈（低分才觸發；只修第一條缺陷、品管過就採用，見 stage_polish 說明）──
        polish_note = ""
        if crit and crit["total"] < POLISH_BAR:
            fix0 = (crit.get("fixes") or ["針對分數最低的維度自行強化一項"])[0]
            log(f"🪄 自評 {crit['total']}/50 低於 {POLISH_BAR}，打磨一輪：只修第一條缺陷「{fix0[:50]}」…")
            adopted = False
            try:
                html2 = stage_polish(html, meta, crit)
                (gdir / "index.html").write_text(inject_stats(html2), encoding="utf-8")
                ok2, errs2 = validate(gdir / "index.html", shot_name=gid)
                if ok2:
                    log("  ✨ 修訂版品管通過，採用（不再拿自評分數當裁判）")
                    append_learning(f"- {today} 打磨《{meta['title']}》修第一條缺陷：{fix0[:60]}（品管通過採用）")
                    html, adopted, polish_note = html2, True, fix0[:80]
                else:
                    log(f"  ↩️ 修訂版品管沒過（{errs2}），改回原版上架")
            except Exception as e:
                log(f"  ⚠️ 打磨過程出錯（不擋出貨，用原版上架）：{e}")
            if not adopted:
                # 修訂版可能已蓋掉檔案與截圖 → 還原原版、重測一次換回原版縮圖
                try:
                    (gdir / "index.html").write_text(inject_stats(html), encoding="utf-8")
                    validate(gdir / "index.html", shot_name=gid)
                except Exception as e:
                    log(f"  ⚠️ 原版還原重測失敗（檔案已還原、縮圖可能沿用修訂版畫面）：{e}")

        # 品管截圖複製進遊戲資料夾當大廳縮圖（打磨後才複製＝拿到最終版畫面）
        shot_src = HERE / "shots" / f"{gid}.png"
        if shot_src.exists():
            shutil.copy(shot_src, gdir / "shot.png")

        entry = {"id": gid, "title": meta["title"], "emoji": meta["emoji"],
                 "genre": normalize_genre(meta["genre"]), "date": today,
                 "inspiration": meta["inspiration"], "desc": meta["desc"]}
        if crit:
            entry["ai_score"] = crit["total"]
            if crit.get("howto"):
                entry["howto"] = crit["howto"]
            log(f"  📋 自評 {crit['total']}/50：{crit.get('verdict','')}")
            append_learning(
                f"- {today} AI 自評《{meta['title']}》{crit['total']}/50："
                f"{crit.get('verdict','')}；待改進：{'；'.join(crit.get('fixes', [])[:3])}")
        if polish_note:
            entry["polished"] = polish_note

        # ── 上架 ──
        # 🔴 read-then-update（防 last-writer-wins 蓋檔）：生產一輪要 20~45 分鐘，
        # 開場讀的 data 是舊快照；拿它整檔覆寫，會把這段期間別的程序寫進
        # games.json 的改動全部抹掉（例：生產撞上 11:30 留言修復還沒收工
        # → 修復加的 bugs/changelog、玩家評分、甚至剛上架的新遊戲整批消失）。
        # 比照 daily_feedback / fix_game（2026-07-10 健檢）：寫前重讀最新檔，
        # 只把「自己這一筆」append 進去，別人的改動原封保留。
        fresh = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
        fresh["games"].append(entry)
        GAMES_JSON.write_text(json.dumps(fresh, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        rebuild.rebuild()
        # history.json 同理：讀→加→寫縮成連續三步，不用開場的舊快照
        history = (json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                   if HISTORY_FILE.exists() else {"used": []})
        history["used"].append({"date": today, "inspiration": decon["source"],
                                "title": meta["title"], "id": gid})
        HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        log(f"✅ 上架完成：《{meta['title']}》（全站第 {len(fresh['games'])} 款）")
        log(f"   本次用量：{usage_summary()}")
        # 先部署、部署成功才推「新品出爐」——否則會出現「站根本沒更新卻已報喜」。
        # publish 失敗會 raise（見 publish_site.py），被這裡接住 → 改發失敗告警、不報喜。
        try:
            import publish_site
            publish_site.publish(f"🏭 新遊戲《{meta['title']}》上架")
            notify_release(entry, crit, decon, polish_note)
        except Exception as e:
            log(f"⚠️ 自動部署失敗（本機照常可玩）：{e}")
            notify_fail(f"《{meta['title']}》已生成但部署失敗、公開站尚未更新：{e}")
        return 0

    log("❌ 重試後仍失敗，本輪停產（下週六排程會再試；想馬上重來就打「生一個新遊戲」）")
    notify_fail(feedback)
    return 1


# ---------------------------------------------------------------- 主流程（臨摹模式）
def main() -> int:
    log("🏭 SlimeCat 遊戲工作室 v2.2 開工（解構 → 設計 → 品管 → 自評 → 打磨）")
    clear_retry("factory")   # 這輪若是補跑本身，先把一次性排程收掉
    try:
        trends = fetch_trends.fetch()
        log(f"📈 榜單 OK（{trends['source']}，{len(trends['games'])} 款）")
    except Exception as e:
        log(f"❌ 抓榜單失敗：{e}")
        notify_fail(f"抓榜單失敗：{e}")
        return 1

    history = (json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
               if HISTORY_FILE.exists() else {"used": []})
    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    today = datetime.date.today().isoformat()

    # ── 解構 ──
    try:
        log("🔍 策劃解構中（挑一款熱門遊戲、拆解上癮機制）…")
        decon = stage_deconstruct(trends, history, data["games"])
        decon_file = save_decon(decon)
        log(f"📖 解構完成：{decon['source']} → {decon_file.name}")
    except QuotaError as e:
        log(f"⏳ 解構撞額度：{e}")
        return 0 if schedule_retry("factory", e.resets_at, str(e)) else 1
    except Exception as e:
        log(f"❌ 解構階段失敗：{e}")
        notify_fail(f"解構階段失敗：{e}")
        return 1

    return produce_from_decon(decon)


if __name__ == "__main__":
    sys.exit(main())
