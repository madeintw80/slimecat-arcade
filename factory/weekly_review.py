# -*- coding: utf-8 -*-
"""每週檢討（後設學習）：數據 + 玩家評分 + 教訓 → 回頭修設計聖經。

流程（每週日 18:00 排程）：
  1. analytics_pull 拉最新數據（沒設定就跳過，不擋）
  2. 把 learnings.md 全文 + 每款評分/數據 丟給 claude 檢討
  3. 產出：3~5 條新教訓 → learnings.md；設計原則修訂 → fun_principles.md「檢討修訂」節
  4. Telegram 推週報
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GAMES_JSON = ROOT / "games.json"
KNOW = HERE / "knowledge"
KB_FILE = KNOW / "fun_principles.md"
LEARN_FILE = KNOW / "learnings.md"
SUMMARY_FILE = HERE / "analytics_summary.json"

sys.path.insert(0, str(HERE))
from make_game import run_claude, log, SMALL_TIMEOUT  # noqa: E402

sys.path.insert(0, "C:/Users/User/projects/_common")
try:
    import batnini_telegram as tg
except Exception:
    tg = None


def main() -> int:
    today = datetime.date.today().isoformat()
    log("📅 SlimeCat 每週檢討開始")

    # 0. 維護迴圈：玩家回報的 open bugs 先修（fix_game 自己會品管+部署+推播；失敗不擋檢討）
    try:
        subprocess.run([sys.executable, str(HERE / "fix_game.py"), "--all"],
                       timeout=7200)
    except Exception as e:
        log(f"⚠️ 自動修復階段出錯（不擋檢討）：{e}")

    # 1. 更新數據（失敗不擋檢討）
    subprocess.run([sys.executable, str(HERE / "analytics_pull.py"), "--quiet"],
                   capture_output=True)
    analytics = "（數據追蹤尚未啟用）"
    if SUMMARY_FILE.exists():
        analytics = SUMMARY_FILE.read_text(encoding="utf-8")

    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    games_brief = [
        {"title": g["title"], "genre": g.get("genre"), "inspiration": g.get("inspiration"),
         "ai_score": g.get("ai_score"), "user_rating": g.get("user_rating"),
         "user_note": g.get("user_note")}
        for g in data["games"]
    ]

    prompt = f"""你是「SlimeCat 遊戲工作室」的製作人，今天 {today}，做每週檢討。
（直接輸出文字、不要使用任何工具）

═══ 全部教訓紀錄 ═══
{LEARN_FILE.read_text(encoding="utf-8")}

═══ 目前作品與評分（user_rating 是玩家真實評分，權重最高）═══
{json.dumps(games_brief, ensure_ascii=False, indent=1)}

═══ 遊玩數據（opens=開啟、med_session_sec=活躍停留中位秒[掛機不計]、return_rate=回訪率）═══
{analytics}

任務：像遊戲公司的週會一樣檢討——哪些設計被數據/評分證實有效？哪些假設被打臉？
下一款該押什麼方向？設計聖經有沒有哪條該修？

輸出格式（嚴格遵守，每行一條）：
LEARN: <新教訓，具體可執行，3~5 條>
PRINCIPLE: <對設計聖經的修訂建議，0~2 條；沒有就不要輸出 PRINCIPLE 行>
SUMMARY: <給老闆看的三句話週報，一行>
"""
    try:
        out = run_claude(prompt, SMALL_TIMEOUT)
    except Exception as e:
        log(f"❌ 檢討失敗：{e}")
        return 1

    learns = [l[6:].strip() for l in out.splitlines() if l.startswith("LEARN:")]
    princs = [l[10:].strip() for l in out.splitlines() if l.startswith("PRINCIPLE:")]
    summary = next((l[8:].strip() for l in out.splitlines() if l.startswith("SUMMARY:")), "")

    with LEARN_FILE.open("a", encoding="utf-8") as f:
        for l in learns:
            f.write(f"- {today} 週檢討：{l}\n")

    if princs:
        with KB_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n## 檢討修訂（{today}）\n")
            for p in princs:
                f.write(f"- {p}\n")

    log(f"✅ 檢討完成：{len(learns)} 條教訓、{len(princs)} 條聖經修訂")
    if tg and tg.available():
        try:
            body = "\n".join(f"• {l}" for l in learns)
            tg.send(f"📅 SlimeCat 每週檢討\n{summary}\n─────\n{body}"
                    + (f"\n─────\n聖經修訂：\n" + "\n".join(f"• {p}" for p in princs) if princs else ""))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
