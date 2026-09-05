# -*- coding: utf-8 -*-
"""抓熱門遊戲榜單，當 SlimeCat 遊戲工廠的靈感來源。

兩個來源（2026-09-05 v3 Phase 1 起「靈感探索器」）：
  1. App Store 台灣「免費遊戲排行榜」（原有；Apple 官方 RSS/JSON，不用金鑰、格式穩定）
  2. Steam 商店「熱銷 Top Sellers」＋「新品熱門 New & Trending」（Boss 拍板 2A：一榜合併、策劃自己挑）
     - featuredcategories 端點有繁中名稱；再用 appdetails 補「簡介＋類型」、順便濾掉 DLC/原聲帶
     - Steam 上多是 PC 大型遊戲，解構時要濃縮成核心迴圈（提示寫在 make_game.stage_deconstruct）

為什麼不用 Google Play？沒有官方 API、要爬網頁比較脆弱。

輸出 trends.json：
  {"fetched_at", "source", "games": [App Store 榜…],
   "steam": {"fetched_at", "source", "games": [{rank, appid, name, list, summary, genres}…]}}
兩邊各自獨立失敗：Steam 抓不到就沿用上次快取（沒有就空清單），不影響 App Store 榜。
"""
import datetime
import json
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")  # Windows 主控台印中文不炸

HERE = Path(__file__).resolve().parent
TRENDS_FILE = HERE / "trends.json"

# 舊版 iTunes RSS：可以直接指定「遊戲類 genre=6014」，還附每款的簡介
LEGACY_URL = "https://itunes.apple.com/tw/rss/topfreeapplications/limit=100/genre=6014/json"
# 新版 Marketing Tools API：備援用（全類 app，要自己過濾出遊戲）
V2_URL = "https://rss.applemarketingtools.com/api/v2/tw/apps/top-free/100/apps.json"

# Steam：featuredcategories 一次給熱銷／新品／特價（帶繁中名稱）；appdetails 一次只能查一款
STEAM_FEATURED_URL = "https://store.steampowered.com/api/featuredcategories/?cc=tw&l=tchinese"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails?appids={appid}&cc=tw&l=tchinese"
STEAM_TOP_SELLERS = 10     # 熱銷榜取幾款（端點本身就只給 10）
STEAM_NEW_TRENDING = 15    # 新品熱門取幾款（端點給 30，取前 15 夠用）
STEAM_DETAIL_CAP = 25      # 最多補幾款簡介（appdetails 有速率限制：約 200 次／5 分鐘，別貪）
STEAM_DETAIL_GAP = 0.4     # 每次 appdetails 之間喘一下（秒）

HEADERS = {"User-Agent": "Mozilla/5.0 (SlimeCatArcade trend fetcher)",
           "Accept-Language": "zh-TW,zh;q=0.9"}


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


# ---------------------------------------------------------------- Steam
def _steam_details(appid: int) -> dict | None:
    """查一款的簡介／類型／是否為遊戲本體；查不到回 None（呼叫端自己決定要不要留）。"""
    r = requests.get(STEAM_DETAILS_URL.format(appid=appid), headers=HEADERS, timeout=12)
    r.raise_for_status()
    node = (r.json() or {}).get(str(appid)) or {}
    if not node.get("success"):
        return None
    d = node.get("data") or {}
    # 成人內容濾掉（Steam content descriptor：1＝部分裸露／性內容、3＝純成人性內容、4＝頻繁裸露；
    # 或 required_age ≥ 18）——新品熱門榜偶爾混進這類，解構它們沒意義也不該進工廠筆記
    desc_ids = set((d.get("content_descriptors") or {}).get("ids") or [])
    try:
        age = int(d.get("required_age") or 0)
    except (TypeError, ValueError):
        age = 0
    return {
        "type": d.get("type", ""),                       # game / dlc / music / demo …
        "summary": (d.get("short_description") or "")[:150],
        "genres": [g.get("description", "") for g in (d.get("genres") or []) if g.get("description")],
        "adult": bool(desc_ids & {1, 3, 4}) or age >= 18,
    }


def _from_steam() -> list:
    """Steam 熱銷 Top 10 ＋ 新品熱門 Top 15，合併去重、補簡介、濾掉非遊戲本體。"""
    r = requests.get(STEAM_FEATURED_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    feed = r.json() or {}
    picked, seen = [], set()
    for key, label, limit in (("top_sellers", "熱銷", STEAM_TOP_SELLERS),
                              ("new_releases", "新品熱門", STEAM_NEW_TRENDING)):
        items = ((feed.get(key) or {}).get("items") or [])[:limit]
        for it in items:
            appid, name = it.get("id"), (it.get("name") or "").strip()
            if not appid or not name or appid in seen:
                continue
            seen.add(appid)
            picked.append({"appid": int(appid), "name": name, "list": label,
                           "summary": "", "genres": []})

    # 補簡介＋類型；DLC／原聲帶／demo 這種不是遊戲本體的丟掉（解構它沒意義）
    games = []
    for g in picked:
        if len(games) >= STEAM_DETAIL_CAP:
            break
        try:
            info = _steam_details(g["appid"])
            time.sleep(STEAM_DETAIL_GAP)
        except Exception as e:  # 單款查不到就只留名字，別讓整榜掛掉
            print(f"⚠️ Steam appdetails {g['appid']} 失敗：{e}")
            info = None
        if info:
            if info["type"] and info["type"] != "game":
                continue
            if info["adult"] or info["genres"] == ["工具"]:   # 成人作／純工具軟體都不是靈感
                continue
            g["summary"], g["genres"] = info["summary"], info["genres"]
        games.append(g)
    for i, g in enumerate(games, 1):
        g["rank"] = i
    return games


def _load_cache() -> dict:
    try:
        return json.loads(TRENDS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fetch_steam() -> dict:
    """抓 Steam 榜 → 回 {"fetched_at","source","games"}；失敗退回上次快取的 steam 區塊（沒有就空清單）。"""
    try:
        games = _from_steam()
        if games:
            return {"fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "source": "steam-featured-tw", "games": games}
        print("⚠️ Steam 榜抓到 0 款")
    except Exception as e:
        print(f"⚠️ Steam 榜抓取失敗：{e}")
    cached = _load_cache().get("steam") or {}
    if cached.get("games"):
        print("⚠️ Steam 改用上次的快取")
        return cached
    return {"fetched_at": "", "source": "steam-unavailable", "games": []}


def fetch() -> dict:
    """抓兩個榜單 → 存 trends.json → 回傳資料。

    App Store 兩個來源都掛就退回舊快取（連快取都沒有才 raise）；Steam 掛了不影響主流程。
    """
    games, source = [], ""
    for fn, name in ((_from_legacy, "appstore-tw-legacy"), (_from_v2, "appstore-tw-v2")):
        try:
            games = fn()
            source = name
            if games:
                break
        except Exception as e:
            print(f"⚠️ {name} 抓取失敗：{e}")
    steam = fetch_steam()
    if not games:
        cached = _load_cache()
        if cached.get("games"):
            print("⚠️ 兩個來源都失敗，改用上次的快取 trends.json")
            cached["steam"] = steam
            TRENDS_FILE.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")
            return cached
        raise RuntimeError("抓不到排行榜，也沒有快取可用")
    data = {
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "games": games,
        "steam": steam,
    }
    TRENDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


if __name__ == "__main__":
    data = fetch()
    print(f"✅ App Store 來源 {data['source']}，共 {len(data['games'])} 款，Top 15：")
    for g in data["games"][:15]:
        print(f"  {g['rank']:>3}. {g['name']}（{g['artist']}）")
    st = data.get("steam") or {}
    print(f"✅ Steam 來源 {st.get('source')}，共 {len(st.get('games', []))} 款：")
    for g in st.get("games", []):
        tags = "／".join(g.get("genres") or []) or "—"
        print(f"  {g['rank']:>3}. [{g['list']}] {g['name']}（{tags}）")
