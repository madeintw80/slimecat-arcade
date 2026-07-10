# -*- coding: utf-8 -*-
"""拉「SlimeCat Analytics」Sheet 的事件，算每款遊戲的成績單。

指標（單機小站版的點擊率/留存率）：
  - opens        開啟次數（點擊率分子）
  - devices      不重複裝置數
  - med_session  停留中位秒數（前端只回報「活躍時間」，掛機不計；中位數抗極端值）
  - return_rate  回訪率＝「首訪隔天以後又來的裝置」比例（D1+ 留存 proxy）
  - med_score    分數中位數（over 事件；防 console 偽造分數污染）
  - 事件的遊戲 id 只認 games.json 名錄（含 retired），垃圾 id 整筆排除

認證：借用 Portfolio 專案現成的 OAuth token（同一個 Google 帳號、同 Sheets scope）。
用法：
  python analytics_pull.py            # 印報表 + 存 factory/analytics_summary.json
  python analytics_pull.py --quiet    # 只存檔（給排程用）
"""
import datetime
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SUMMARY_FILE = HERE / "analytics_summary.json"

SHEET_ID = "1lWyPRyRXr3hB6i-lVksq6pozFl0CXQYZa9RhnkDyRoA"  # SlimeCat Analytics
# OAuth 憑證改走 Batnini 共用模組（single source of truth），不再寫死路徑：
# Portfolio 一旦重新授權/搬家，這裡自動跟著換，不會各自過期而靜默 401。
sys.path.insert(0, "C:/Users/User/projects/_common")
from batnini_secrets import OAUTH_TOKEN_FILE  # noqa: E402
PORTFOLIO_TOKEN = OAUTH_TOKEN_FILE            # 沿用原變數名（daily_feedback 有 import 它）
GAMES_JSON = HERE.parent / "games.json"


def known_ids():
    """大廳 + 上架中 + 已下架的遊戲 id——事件只認這些，垃圾 id 不進報表也不進週報。"""
    ids = {"arcade"}
    try:
        data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
        for g in data.get("games", []) + data.get("retired", []):
            ids.add(g["id"])
    except Exception:
        pass
    return ids


def fetch_rows():
    """讀 events 分頁全部資料列（跳過標題）。"""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(PORTFOLIO_TOKEN))
    svc = build("sheets", "v4", credentials=creds)
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="events!A2:G").execute()
    return resp.get("values", [])


def fetch_ratings():
    """讀 ratings 分頁（網頁評分＋留言）。分頁還沒建（GAS v3 未部署）就回空。"""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(PORTFOLIO_TOKEN))
    svc = build("sheets", "v4", credentials=creds)
    try:
        resp = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range="ratings!A2:F").execute()
        return resp.get("values", [])
    except Exception:
        return []


def summarize_ratings(rows):
    """rows: [時間, 遊戲, 分數, 留言, 裝置ID, 手機]
    同一裝置對同一款以最後一筆為準（可改評），回傳 {game: {...}}。"""
    known = known_ids()
    latest = {}  # (game, did) -> (score, note)，列序即時間序
    for r in rows:
        r = r + [""] * (6 - len(r))
        _, game, score, note, did, _ = r[:6]
        if game not in known:
            continue
        try:
            score = int(float(score))
        except ValueError:
            continue
        if not 1 <= score <= 10:
            continue
        latest[(game, did)] = (score, str(note)[:100].strip())

    out = {}
    for (game, _did), (score, note) in latest.items():
        s = out.setdefault(game, {"scores": [], "notes": []})
        s["scores"].append(score)
        if note:
            s["notes"].append({"score": score, "note": note})
    for game, s in out.items():
        s["web_raters"] = len(s["scores"])
        s["web_score_med"] = round(statistics.median(s["scores"]), 1)
        s["notes"] = s["notes"][-5:]  # 只留最新 5 條給週檢討，防灌太長
        del s["scores"]
    return out


def summarize(rows):
    """rows: [時間, 事件, 遊戲, 數值, 裝置ID, 距首訪天數, 手機]
    回傳 (每款統計, 被排除的未知事件數)。"""
    known = known_ids()
    unknown = 0
    g = defaultdict(lambda: {"opens": 0, "devices": set(), "return_devices": set(),
                             "sessions": [], "scores": [], "mobile": 0})
    for r in rows:
        r = r + [""] * (7 - len(r))  # 短列補齊
        _, ev, game, val, did, days, mob = r[:7]
        if not game:
            continue
        if game not in known:  # 只認名錄裡的遊戲，垃圾/偽造 id 直接排除
            unknown += 1
            continue
        s = g[game]
        try:
            val = float(val or 0)
            days = int(float(days or 0))
        except ValueError:
            continue
        if ev == "open":
            s["opens"] += 1
            s["devices"].add(did)
            if days >= 1:
                s["return_devices"].add(did)
            if str(mob) == "1":
                s["mobile"] += 1
        elif ev == "session" and 0 < val < 7200:   # 秒數異常值剔除
            s["sessions"].append(val)
        elif ev == "over":
            s["scores"].append(val)

    out = {}
    for game, s in g.items():
        n_dev = len(s["devices"]) or 1
        out[game] = {
            "opens": s["opens"],
            "devices": len(s["devices"]),
            # 中位數比平均抗灌水：單一極端值（掛機/偽造）拉不動它
            "med_session_sec": round(statistics.median(s["sessions"]), 1) if s["sessions"] else 0,
            "avg_session_sec": round(sum(s["sessions"]) / len(s["sessions"]), 1) if s["sessions"] else 0,
            "plays_reported": len(s["scores"]),
            "med_score": round(statistics.median(s["scores"]), 1) if s["scores"] else 0,
            "avg_score": round(sum(s["scores"]) / len(s["scores"]), 1) if s["scores"] else 0,
            "return_rate": round(len(s["return_devices"]) / n_dev, 2),
            "mobile_ratio": round(s["mobile"] / s["opens"], 2) if s["opens"] else 0,
        }
    return out, unknown


def report_text(summary) -> str:
    if not summary:
        return "（還沒有任何事件——網站有人玩之後這裡就會有數據）"
    lines = ["🎮 SlimeCat 數據成績單", "─" * 24]
    order = sorted(summary.items(), key=lambda kv: -kv[1]["opens"])
    for game, s in order:
        name = "🏠 大廳" if game == "arcade" else f"《{game}》"
        lines.append(f"{name}")
        lines.append(f"  開啟 {s['opens']} 次｜{s['devices']} 台裝置｜手機占比 {int(s['mobile_ratio']*100)}%")
        lines.append(f"  活躍停留中位 {s['med_session_sec']} 秒｜回訪率 {int(s['return_rate']*100)}%")
        if s["plays_reported"]:
            lines.append(f"  回報 {s['plays_reported']} 局｜分數中位 {s['med_score']}")
        if s.get("web_raters"):
            lines.append(f"  👥 網頁評分中位 {s['web_score_med']}/10（{s['web_raters']} 人）")
    return "\n".join(lines)


def main() -> int:
    quiet = "--quiet" in sys.argv
    try:
        rows = fetch_rows()
    except Exception as e:
        print(f"❌ 讀不到 Analytics Sheet：{e}")
        print("   （還沒部署 Apps Script？看 SETUP_ANALYTICS.md；"
              "或 Portfolio token 過期，跑 portfolio_cli.py status 重新 OAuth）")
        return 1
    summary, unknown = summarize(rows)

    # 網頁評分＋留言併進每款統計（web-only 的遊戲補一個基本骨架）
    for game, w in summarize_ratings(fetch_ratings()).items():
        summary.setdefault(game, {
            "opens": 0, "devices": 0, "med_session_sec": 0, "avg_session_sec": 0,
            "plays_reported": 0, "med_score": 0, "avg_score": 0,
            "return_rate": 0, "mobile_ratio": 0,
        }).update(w)

    SUMMARY_FILE.write_text(json.dumps({
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "total_events": len(rows),
        "unknown_events": unknown,
        "games": summary,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if not quiet:
        print(report_text(summary))
        if unknown:
            print(f"\n⚠️ 另有 {unknown} 筆未知遊戲 id 的事件已排除（垃圾或測試資料）")
        print(f"\n（共 {len(rows)} 筆事件，已存 {SUMMARY_FILE.name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
