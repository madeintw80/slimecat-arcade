# -*- coding: utf-8 -*-
"""把 games.json（真相來源）轉成 games.js 給大廳網頁用。

為什麼不讓 index.html 直接 fetch games.json？
  因為本機是用 file:// 打開網頁，fetch 會被瀏覽器 CORS 擋掉；
  改成 <script src="games.js"> 載入就沒這個問題。

手動下架遊戲：把 games.json 裡那筆刪掉 → 重跑本腳本 →（可選）刪 games/<id>/ 資料夾。
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GAMES_JSON = ROOT / "games.json"
GAMES_JS = ROOT / "games.js"
INDEX = ROOT / "index.html"


def rebuild() -> int:
    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    # 對外的 games.js 剔除 inspiration（原作名只留在內部紀錄，避免商標/攀附疑慮）
    games = [{k: v for k, v in g.items() if k != "inspiration"}
             for g in data.get("games", [])]
    js = ("// 此檔由 factory/rebuild.py 自動產生，別手改（改 games.json 再重跑）\n"
          "const GAMES = " + json.dumps(games, ensure_ascii=False, indent=2) + ";\n")
    GAMES_JS.write_text(js, encoding="utf-8")

    # cache-busting：大廳引用帶內容指紋（名錄一變網址就變，玩家不用等瀏覽器快取過期）
    v = hashlib.md5(js.encode("utf-8")).hexdigest()[:8]
    html = INDEX.read_text(encoding="utf-8")
    new_html = re.sub(r'src="games\.js[^"]*"', f'src="games.js?v={v}"', html)
    if new_html != html:
        INDEX.write_text(new_html, encoding="utf-8")
    return len(games)


if __name__ == "__main__":
    n = rebuild()
    print(f"✅ games.js 重建完成，共 {n} 款遊戲")
