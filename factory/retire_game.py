# -*- coding: utf-8 -*-
"""下架不好玩的遊戲（移到 retired 名單，大廳不再顯示；檔案保留可復活）。

用法：
    python retire_game.py <遊戲名或id關鍵字>          # 下架
    python retire_game.py <遊戲名或id關鍵字> --revive  # 復活
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GAMES_JSON = ROOT / "games.json"

sys.path.insert(0, str(HERE))
import rebuild  # noqa: E402


def find(pool, query):
    return [g for g in pool if query in g["title"] or query in g["id"]]


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python retire_game.py <遊戲名或id> [--revive]")
        return 2
    query = sys.argv[1].strip()
    revive = "--revive" in sys.argv

    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    data.setdefault("retired", [])
    src, dst, verb = (data["retired"], data["games"], "復活") if revive \
        else (data["games"], data["retired"], "下架")

    hits = find(src, query)
    if not hits:
        print(f"❌ 找不到「{query}」。目前可{verb}的：")
        for g in src:
            print(f"   - {g['title']}（{g['id']}）")
        return 1
    if len(hits) > 1:
        print(f"⚠️ 「{query}」對到多款，講更完整的名字：")
        for g in hits:
            print(f"   - {g['title']}（{g['id']}）")
        return 1

    g = hits[0]
    src.remove(g)
    dst.append(g)
    GAMES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    n = rebuild.rebuild()
    print(f"✅ 已{verb}《{g['title']}》，大廳現有 {n} 款")
    print("   （要讓線上同步：python factory/publish_site.py）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
