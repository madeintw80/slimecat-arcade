# -*- coding: utf-8 -*-
"""拉「SlimeCat Analytics」Sheet 的事件，算每款遊戲的成績單。

指標（單機小站版的點擊率/留存率）：
  - opens        開啟次數（點擊率分子）
  - devices      不重複裝置數
  - avg_session  平均停留秒數
  - return_rate  回訪率＝「首訪隔天以後又來的裝置」比例（D1+ 留存 proxy）
  - avg_score    平均分數（over 事件）

認證：借用 Portfolio 專案現成的 OAuth token（同一個 Google 帳號、同 Sheets scope）。
用法：
  python analytics_pull.py            # 印報表 + 存 factory/analytics_summary.json
  python analytics_pull.py --quiet    # 只存檔（給排程用）
"""
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SUMMARY_FILE = HERE / "analytics_summary.json"

SHEET_ID = "1lWyPRyRXr3hB6i-lVksq6pozFl0CXQYZa9RhnkDyRoA"  # SlimeCat Analytics
PORTFOLIO_TOKEN = Path("C:/Users/User/projects/Portfolio/token.json")


def fetch_rows():
    """讀 events 分頁全部資料列（跳過標題）。"""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(PORTFOLIO_TOKEN))
    svc = build("sheets", "v4", credentials=creds)
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="events!A2:G").execute()
    return resp.get("values", [])


def summarize(rows):
    """rows: [時間, 事件, 遊戲, 數值, 裝置ID, 距首訪天數, 手機]"""
    g = defaultdict(lambda: {"opens": 0, "devices": set(), "return_devices": set(),
                             "sessions": [], "scores": [], "mobile": 0})
    for r in rows:
        r = r + [""] * (7 - len(r))  # 短列補齊
        _, ev, game, val, did, days, mob = r[:7]
        if not game:
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
            "avg_session_sec": round(sum(s["sessions"]) / len(s["sessions"]), 1) if s["sessions"] else 0,
            "plays_reported": len(s["scores"]),
            "avg_score": round(sum(s["scores"]) / len(s["scores"]), 1) if s["scores"] else 0,
            "return_rate": round(len(s["return_devices"]) / n_dev, 2),
            "mobile_ratio": round(s["mobile"] / s["opens"], 2) if s["opens"] else 0,
        }
    return out


def report_text(summary) -> str:
    if not summary:
        return "（還沒有任何事件——網站有人玩之後這裡就會有數據）"
    lines = ["🎮 SlimeCat 數據成績單", "─" * 24]
    order = sorted(summary.items(), key=lambda kv: -kv[1]["opens"])
    for game, s in order:
        name = "🏠 大廳" if game == "arcade" else f"《{game}》"
        lines.append(f"{name}")
        lines.append(f"  開啟 {s['opens']} 次｜{s['devices']} 台裝置｜手機占比 {int(s['mobile_ratio']*100)}%")
        lines.append(f"  平均停留 {s['avg_session_sec']} 秒｜回訪率 {int(s['return_rate']*100)}%")
        if s["plays_reported"]:
            lines.append(f"  回報 {s['plays_reported']} 局｜平均分 {s['avg_score']}")
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
    summary = summarize(rows)
    SUMMARY_FILE.write_text(json.dumps({
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "total_events": len(rows),
        "games": summary,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if not quiet:
        print(report_text(summary))
        print(f"\n（共 {len(rows)} 筆事件，已存 {SUMMARY_FILE.name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
