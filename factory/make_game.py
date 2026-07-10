# -*- coding: utf-8 -*-
"""SlimeCat 遊戲工作室 v2 — 會學習的遊戲生產線。

跟 v1（單純模仿）的差別：完整的學習迴圈——
  解構為什麼好玩 → 帶著設計理論做 → 出廠自評 → 玩家回饋餵回 → 下一款更好。

流程：
  1. fetch_trends 抓 App Store 台灣免費遊戲榜（失敗自動退回快取）
  2. 【解構】claude 從榜單挑一款，解構它的上癮機制 → 存 knowledge/deconstructions/
     （解構筆記會永久累積，工作室的遊戲設計功力隨時間變厚）
  3. 【設計+實作】claude 帶著三份資料生成遊戲：
     - knowledge/fun_principles.md（設計聖經：核心迴圈/near-miss/juice/難度曲線…）
     - 這次的解構筆記
     - knowledge/learnings.md 最新教訓（玩家評分 + 歷次 AI 自評）
  4. 【品管】Playwright 煙霧測試（噴錯不上架，重生一次）
  5. 【自評】claude 評審按五維量表打分（上手/juice/目標/難度/再一局，滿分 50），
     分數與改進點記進 learnings，餵給下一款
  6. 上架 games.json + games.js，Telegram 推新品（含自評分）

玩家回饋入口：python rate_game.py <遊戲名> <1-10> [評語] —— 玩家評分 > AI 自評 > 理論。
"""
import datetime
import json
import re
import shutil
import subprocess
import sys
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
# 模型策略（2026-07-06 改混合模型：保品質、砍 opus 額度約 2/3）：
# 三個階段吃的模型分開挑——「寫遊戲」才需要旗艦，前後的讀寫小任務用小模型就夠。
#   解構＝sonnet：讀榜單寫解構筆記，中模型夠用
#   實作＝opus（別名=最新版 Opus，目前 4.8）：品質關鍵，唯一保 opus 的環節
#   自評＝haiku：按固定五維量表打分出一行 JSON，小模型夠用
# run_claude 的 model 參數預設 MODEL_BUILD(opus) → fix_game / daily_feedback /
# weekly_review / original_mode 這些沒指定 model 的呼叫端行為不變（零回歸）。
MODEL_DECON = "sonnet"    # 解構熱門遊戲
MODEL_BUILD = "opus"      # 設計＋實作遊戲（品質關鍵）
MODEL_CRITIC = "haiku"    # 出廠五維自評
GEN_TIMEOUT = 2700        # 實作一整款遊戲的時間上限（sonnet 曾 30 分鐘超時，放寬到 45 分鐘）
SMALL_TIMEOUT = 900       # 解構 / 評審這類小任務的上限
MAX_ATTEMPTS = 2          # 實作 + 驗證最多試幾次


def log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_claude(prompt: str, timeout: int, model: str = MODEL_BUILD) -> str:
    """呼叫 claude -p。空 MCP config 跳過冷啟動；model 不指定＝MODEL_BUILD(opus)。"""
    # 子 Claude 是「純文字交稿」：禁用全部工具，防止它自作主張直接寫檔案
    # （2026-07-04 事故：開發者把遊戲直接寫進專案、stdout 沒交稿 → 驗收誤判失敗）
    deny = "Bash,Edit,Write,NotebookEdit,Read,Glob,Grep,WebFetch,WebSearch,Task,TodoWrite"
    cmd = [CLAUDE, "-p", "--model", model, "--disallowedTools", deny,
           "--strict-mcp-config", "--mcp-config", str(EMPTY_MCP)]
    proc = subprocess.run(cmd, input=prompt, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=str(LLM_CWD))
    if proc.returncode != 0:
        err = (proc.stderr or "")[-500:]
        if "401" in err or "unauthorized" in err.lower():
            raise RuntimeError("claude CLI 401：token 過期，請跑 scripts/claude_relogin.bat 重登")
        raise RuntimeError(f"claude -p 失敗 (code {proc.returncode})：{err}")
    return proc.stdout


def tail(path: Path, lines: int = 60) -> str:
    """讀檔案最後 N 行（learnings 只餵最新的）。"""
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-lines:])


# ---------------------------------------------------------------- 解構
def stage_deconstruct(trends: dict, history: dict, past_games: list) -> dict:
    """挑一款熱門遊戲並解構其上癮機制。回傳 {source,title,genre,doc}。"""
    chart = []
    for g in trends["games"][:40]:
        s = f"{g['rank']}. {g['name']}（{g['artist']}）"
        if g.get("summary"):
            s += f"：{g['summary'][:100]}"
        chart.append(s)
    used = [u["inspiration"] for u in history["used"]]
    past = [f"《{g['title']}》({g.get('genre','')})：{g.get('desc','')}" for g in past_games]

    prompt = f"""你是「SlimeCat 遊戲工作室」的首席遊戲策劃。今天是 {datetime.date.today().isoformat()}。

App Store 台灣免費遊戲排行榜（來源 {trends['source']}）：
{chr(10).join(chart)}

已用過的靈感（避開）：{json.dumps(used, ensure_ascii=False)}
本站已有的遊戲（新遊戲的核心機制不可跟它們重複，多樣性也是留存）：
{chr(10).join(past) if past else "（還沒有）"}

任務：從榜單挑一款「核心玩法能濃縮成 30 秒上手網頁小遊戲」的遊戲
（避開：博弈/賭場、需連線帳號、重度 RPG/卡牌收集、純 IP 授權作），
然後寫一份**解構筆記**：不是描述它有什麼功能，而是拆解「為什麼會好玩、為什麼讓人上癮」。

輸出格式（嚴格遵守，前三行是標頭，之後是筆記本體；直接印出文字、不要使用任何工具）：
SOURCE: <原作名稱>
TITLE: <我們的變形版建議中文名（全新命名；不可含原作名，也不可與原作名音近/形近/直譯——商標紅線）>
GENRE: <類型一詞（街機/益智/反應/跑酷/消除…）>

# 解構：<原作名>
## 核心迴圈（一圈幾秒？操作→回饋→獎勵怎麼轉？）
## 上癮機制（用心理學拆：near-miss？歸因於己？指數獎勵？損失趨避？收集慾？）
## 難度與節奏（怎麼讓新手活過前 15 秒、又讓老手 2 分鐘後不無聊？）
## 可偷的設計（3-5 條，我們的單檔小遊戲做得到的）
## 不可行的部分（原作有但我們該捨棄的，為什麼）
## 我們的變形版一句話企劃（史萊姆貓宇宙，核心樂趣要保留哪一條）
"""
    out = run_claude(prompt, SMALL_TIMEOUT, model=MODEL_DECON)
    src = re.search(r"^SOURCE:\s*(.+)$", out, re.M)
    ttl = re.search(r"^TITLE:\s*(.+)$", out, re.M)
    gnr = re.search(r"^GENRE:\s*(.+)$", out, re.M)
    if not src:
        raise ValueError("解構輸出缺 SOURCE 標頭")
    doc_start = out.find("# 解構")
    doc = out[doc_start:] if doc_start >= 0 else out
    return {
        "source": src.group(1).strip(),
        "title": (ttl.group(1).strip() if ttl else ""),
        "genre": (gnr.group(1).strip() if gnr else "小遊戲"),
        "doc": doc.strip(),
    }


# ---------------------------------------------------------------- 設計 + 實作
def stage_generate(decon: dict, past_games: list, feedback: str = ""):
    """帶著設計聖經 + 解構筆記 + 教訓生成完整遊戲。回傳 (meta, html)。"""
    kb = KB_FILE.read_text(encoding="utf-8") if KB_FILE.exists() else ""
    learn = tail(LEARN_FILE, 60)
    past = [f"《{g['title']}》({g.get('genre','')})" for g in past_games]
    fb = (f"\n⚠️ 上一次生成沒通過品管，錯誤如下，請避免同類問題：\n{feedback}\n"
          if feedback else "")

    prompt = f"""你是「SlimeCat 遊戲工作室」的資深遊戲開發者。要做一款比本站過去所有作品都更好玩的小遊戲。

═══ 設計聖經（做之前先內化）═══
{kb}

═══ 這次的解構筆記（策劃已完成）═══
{decon['doc']}

═══ 最近的教訓與玩家回饋（最高優先級，玩家評分 > 理論）═══
{learn if learn else "（還沒有）"}

═══ 本站已有遊戲（核心機制不可重複）═══
{chr(10).join(past) if past else "（無）"}
{fb}
任務：把解構筆記裡「我們的變形版企劃」實作成完整單檔 HTML5 小遊戲。
建議名稱《{decon['title'] or '（自訂）'}》，主角美術一律「史萊姆貓」宇宙
（綠色史萊姆＋貓耳，canvas 畫或 emoji），絕不可用原作名稱/角色/美術/音樂。
版權紅線：只學「機制與心理學」、不抄「表達」——遊戲名不可與原作音近/形近/直譯；
不可複製原作的特徵性視覺（配色組合/圖示造型）、具體數值表與關卡佈局。
實作時逐條對照設計聖經第三節「出貨檢查清單」——特別是：
前 15 秒不會死、每個互動都有 juice、Game Over 顯示差 X 分破紀錄、重開一鍵零等待。

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
（你也沒有寫檔權限），把完整 HTML 當純文字印出來就是交稿。

輸出格式（嚴格遵守）：
- 不要 markdown code fence、不要任何解說文字，直接輸出檔案內容
- 檔案第一行必須是這個中繼資料註解（JSON 單行）：
<!--GAMEMETA {{"title":"遊戲中文名","emoji":"一個代表emoji","genre":"{decon['genre']}","inspiration":"{decon['source']}","desc":"一句話介紹(30字內)"}}-->
- 第二行開始就是 <!DOCTYPE html> 起頭的完整網頁
"""
    out = run_claude(prompt, GEN_TIMEOUT, model=MODEL_BUILD)
    return extract(out)


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
    meta.setdefault("genre", "小遊戲")
    meta.setdefault("desc", "")
    if "<canvas" not in html.lower():
        raise ValueError("HTML 裡沒有 canvas")
    return meta, html


# ---------------------------------------------------------------- 出廠自評
def stage_critic(html: str, meta: dict):
    """AI 評審按五維量表打分。失敗不擋出貨（fail-open），回傳 dict 或 None。"""
    kb_scale = ("五維量表：上手(不看說明能玩?規則一句話?)、Juice(每個操作有視聽回饋?得分有爽感演出?)、"
                "目標(隨時知道為何而玩?)、難度(前15秒安全?2分鐘後仍有挑戰?)、再一局(near-miss設計?重開零摩擦?)")
    prompt = f"""你是嚴格的遊戲評審。以下是一款 canvas 小遊戲《{meta['title']}》的完整原始碼，
用讀 code 的方式評估它「實際玩起來」的體驗（想像執行結果，別只看有沒有寫註解）。

{kb_scale}

每維 1-10 分（8 分以上必須真的出色才給）。只輸出一行 JSON，格式：
{{"scores":{{"onboarding":n,"juice":n,"goal":n,"difficulty":n,"one_more":n}},"total":n,"fixes":["最重要的改進點1","改進點2","改進點3"],"verdict":"一句話總評"}}

原始碼：
{html[:45000]}
"""
    try:
        out = run_claude(prompt, SMALL_TIMEOUT, model=MODEL_CRITIC)
        i, j = out.find("{"), out.rfind("}")
        crit = json.loads(out[i:j + 1])
        # 🔴 不信模型自報的 total：haiku 常把單維 1-10 分當成總分回（例 total=7），
        # 被當成 50 分制上架 → 公開卡片顯示 6/7/8 這種假分數。
        # 改成先驗五維齊全且各為 1-10 整數，再一律自己加總（忽略模型自報 total）。
        scores = crit.get("scores") or {}
        dims = ("onboarding", "juice", "goal", "difficulty", "one_more")
        clean = {}
        for d in dims:
            v = scores.get(d)
            # 每維必須是 1-10 的整數（容忍 8.0 這種整數值 float，擋掉 8.5／缺項／超範圍）；
            # 不合格就 raise → 被下面 except 接住當「自評失敗」→ 不設 ai_score（卡片隱藏分數）。
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or not 1 <= v <= 10:
                raise ValueError(f"自評維度 {d}={v!r} 非 1-10 整數（五維不齊或超範圍）")
            clean[d] = int(v)
        crit["scores"] = clean
        crit["total"] = sum(clean.values())   # 一律五維加總（滿分 50），不看模型自報 total
        return crit
    except Exception as e:
        log(f"  ⚠️ 自評失敗（不擋出貨）：{e}")
        return None


# ---------------------------------------------------------------- 工具
def next_id(date_str: str, games: list) -> str:
    n = sum(1 for g in games if g["id"].startswith(date_str)) + 1
    return f"{date_str}-{n:03d}"


def inject_stats(html: str) -> str:
    """把數據回報的 script 標籤插進 </body> 前（生成器不用知道 stats 的存在）。"""
    tags = ('<script src="../../sc_config.js"></script>\n'
            '<script src="../../stats.js"></script>\n')
    i = html.lower().rfind("</body>")
    return html[:i] + tags + html[i:] if i >= 0 else html + "\n" + tags


def append_learning(line: str) -> None:
    with LEARN_FILE.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def notify(entry: dict, crit) -> None:
    if not (tg and tg.available()):
        return
    score_line = (f"AI 自評：{crit['total']}/50 —— {crit.get('verdict','')}"
                  if crit else "AI 自評：略過")
    text = (f"🏭🎮 SlimeCat 遊戲區 新品出爐！\n"
            f"《{entry['title']}》{entry['emoji']}\n"
            f"類型：{entry['genre']}｜靈感：{entry['inspiration']}\n"
            f"{entry['desc']}\n{score_line}\n\n"
            f"玩完給回饋（會讓下一款更好玩）：\n"
            f"「遊戲評分 {entry['title']} 8 手感不錯」\n\n"
            f"打開遊戲區：C:/Users/User/projects/SlimeCatArcade/index.html")
    shot = HERE / "shots" / f"{entry['id']}.png"
    try:
        if shot.exists():
            tg.push_photo(shot, caption=text)
        else:
            tg.send(text)
    except Exception as e:
        log(f"⚠️ Telegram 推播失敗：{e}")


def notify_fail(reason: str) -> None:
    if not (tg and tg.available()):
        return
    try:
        tg.send(f"🏭⚠️ SlimeCat 遊戲工廠今天生產失敗（已重試）。\n"
                f"原因：{reason[:300]}\n詳見 factory/factory.log")
    except Exception:
        pass


# ---------------------------------------------------------------- 生產管線（共用）
def produce_from_decon(decon: dict) -> int:
    """帶著企劃資料跑完 設計→實作→品管→自評→上架→部署。

    decon = {source, title, genre, doc}——doc 是解構筆記（臨摹模式，make_game）
    或原創企劃書（原創模式，original_mode.py），管線本身完全相同。
    """
    history = (json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
               if HISTORY_FILE.exists() else {"used": []})
    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    today = datetime.date.today().isoformat()
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"🛠️ 第 {attempt}/{MAX_ATTEMPTS} 次實作（model={MODEL_BUILD}，最多等 {GEN_TIMEOUT//60} 分鐘）…")
        try:
            meta, html = stage_generate(decon, data["games"], feedback)
        except Exception as e:
            log(f"  ❌ 實作失敗：{e}")
            feedback = str(e)
            continue

        meta["inspiration"] = decon["source"]  # 靈感欄以策劃解構為準
        gid = next_id(today, data["games"])
        gdir = GAMES_DIR / gid
        gdir.mkdir(parents=True, exist_ok=True)
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

        # 品管截圖複製進遊戲資料夾當大廳縮圖
        shot_src = HERE / "shots" / f"{gid}.png"
        if shot_src.exists():
            shutil.copy(shot_src, gdir / "shot.png")

        # ── 出廠自評 ──
        log("🧐 評審自評中…")
        crit = stage_critic(html, meta)
        entry = {"id": gid, "title": meta["title"], "emoji": meta["emoji"],
                 "genre": meta["genre"], "date": today,
                 "inspiration": meta["inspiration"], "desc": meta["desc"]}
        if crit:
            entry["ai_score"] = crit["total"]
            log(f"  📋 自評 {crit['total']}/50：{crit.get('verdict','')}")
            append_learning(
                f"- {today} AI 自評《{meta['title']}》{crit['total']}/50："
                f"{crit.get('verdict','')}；待改進：{'；'.join(crit.get('fixes', [])[:3])}")

        # ── 上架 ──
        data["games"].append(entry)
        GAMES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        rebuild.rebuild()
        history["used"].append({"date": today, "inspiration": decon["source"],
                                "title": meta["title"], "id": gid})
        HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        log(f"✅ 上架完成：《{meta['title']}》（全站第 {len(data['games'])} 款）")
        # 先部署、部署成功才推「新品出爐」——否則會出現「站根本沒更新卻已報喜」。
        # publish 失敗會 raise（見 publish_site.py），被這裡接住 → 改發失敗告警、不報喜。
        try:
            import publish_site
            publish_site.publish(f"🏭 新遊戲《{meta['title']}》上架")
            notify(entry, crit)
        except Exception as e:
            log(f"⚠️ 自動部署失敗（本機照常可玩）：{e}")
            notify_fail(f"《{meta['title']}》已生成但部署失敗、公開站尚未更新：{e}")
        return 0

    log("❌ 重試後仍失敗，今天停產（明天排程會再試）")
    notify_fail(feedback)
    return 1


# ---------------------------------------------------------------- 主流程（臨摹模式）
def main() -> int:
    log("🏭 SlimeCat 遊戲工作室 v2 開工（解構 → 設計 → 品管 → 自評）")
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
        DECON_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^\w一-鿿-]+", "_", decon["source"])[:40]
        decon_file = DECON_DIR / f"{today}-{slug}.md"
        decon_file.write_text(decon["doc"], encoding="utf-8")
        log(f"📖 解構完成：{decon['source']} → {decon_file.name}")
    except Exception as e:
        log(f"❌ 解構階段失敗：{e}")
        notify_fail(f"解構階段失敗：{e}")
        return 1

    return produce_from_decon(decon)


if __name__ == "__main__":
    sys.exit(main())
