# -*- coding: utf-8 -*-
"""抓 App Store 台灣「免費遊戲排行榜」，當 SlimeCat 遊戲工廠的靈感來源。

為什麼用 App Store 而不是 Google Play？
  Apple 有官方 RSS/JSON 榜單（不用金鑰、格式穩定），
  Google Play 沒有官方 API、要爬網頁比較脆弱 → 留到 Phase 2 再加。
"""
import datetime
import json
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")  # Windows 主控台印中文不炸

HERE = Path(__file__).resolve().parent
TRENDS_FILE = HERE / "trends.json"

# 舊版 iTunes RSS：可以直接指定「遊戲類 genre=6014」，還附每款的簡介
LEGACY_URL = "https://itunes.apple.com/tw/rss/topfreeapplications/limit=100/genre=6014/json"
# 新版 Marketing Tools API：備援用（全類 app，要自己過濾出遊戲）
V2_URL = "https://rss.applemarketingtools.com/api/v2/tw/apps/top-free/100/apps.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (SlimeCatArcade trend fetcher)"}


def _from_legacy() -> list:
    r = requests.get(LEGACY_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    entries = r.json().get("feed", {}).get("entry", [])
    if isinstance(entries, dict):  # 只有一筆時 Apple 會直接給 dict
        entries = [entries]
    games = []
    for i, e in enumerate(entries, 1):
        games.append({
            "rank": i,
            "name": e.get("im:name", {}).get("label", ""),
            "artist": e.get("im:artist", {}).get("label", ""),
            "summary": (e.get("summary", {}) or {}).get("label", "")[:150],
        })
    return games


def _from_v2() -> list:
    r = requests.get(V2_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    results = r.json().get("feed", {}).get("results", [])
    games = []
    for e in results:
        genre_ids = {g.get("genreId") for g in e.get("genres", [])}
        if "6014" not in genre_ids:  # 6014 = Games
            continue
        games.append({"rank": len(games) + 1, "name": e.get("name", ""),
                      "artist": e.get("artistName", ""), "summary": ""})
    return games


def fetch() -> dict:
    """抓榜單 → 存 trends.json → 回傳資料；兩個來源都掛就退回舊快取。"""
    games, source = [], ""
    for fn, name in ((_from_legacy, "appstore-tw-legacy"), (_from_v2, "appstore-tw-v2")):
        try:
            games = fn()
            source = name
            if games:
                break
        except Exception as e:
            print(f"⚠️ {name} 抓取失敗：{e}")
    if not games:
        if TRENDS_FILE.exists():
            print("⚠️ 兩個來源都失敗，改用上次的快取 trends.json")
            return json.loads(TRENDS_FILE.read_text(encoding="utf-8"))
        raise RuntimeError("抓不到排行榜，也沒有快取可用")
    data = {
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "games": games,
    }
    TRENDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


if __name__ == "__main__":
    data = fetch()
    print(f"✅ 來源 {data['source']}，共 {len(data['games'])} 款，Top 15：")
    for g in data["games"][:15]:
        print(f"  {g['rank']:>3}. {g['name']}（{g['artist']}）")
