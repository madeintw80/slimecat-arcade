# -*- coding: utf-8 -*-
"""玩家 bug 回報入口 —— 維護迴圈的第一步（回報 → 修復 → 驗證 → 上線）。

用法：
    python report_bug.py <遊戲名或id關鍵字> <bug 描述>
例：
    python report_bug.py 毛球 拖曳方塊放下的位置會錯位，手機更明顯

做兩件事：
  1. games.json 該遊戲的 bugs[] 加一筆（status=open）
  2. 追加到 knowledge/learnings.md（工廠下次生產會讀，避免新遊戲犯同類錯）

之後修復：
    python fix_game.py <遊戲>     # 立刻修
    （或不動它，週日 18:00 檢討排程會自動掃 open bugs 逐一修）
"""
import datetime
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GAMES_JSON = ROOT / "games.json"
LEARN_FILE = HERE / "knowledge" / "learnings.md"


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: python report_bug.py <遊戲名或id關鍵字> <bug 描述>")
        return 2
    query = sys.argv[1].strip()
    note = " ".join(sys.argv[2:]).strip()

    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    # 上架中與已下架的都能報（下架的修好可以復活）
    pool = data.get("games", []) + data.get("retired", [])
    hits = [g for g in pool if query in g["title"] or query in g["id"]]
    if not hits:
        print(f"❌ 找不到遊戲「{query}」。目前有：")
        for g in pool:
            print(f"   - {g['title']}（{g['id']}）")
        return 1
    if len(hits) > 1:
        print(f"⚠️ 「{query}」對到多款，請講更完整的名字：")
        for g in hits:
            print(f"   - {g['title']}（{g['id']}）")
        return 1

    g = hits[0]
    today = datetime.date.today().isoformat()
    g.setdefault("bugs", []).append({"date": today, "note": note, "status": "open"})
    GAMES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    # 教訓也記一條（新遊戲生產前會讀到，同類問題不再犯）
    with LEARN_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- {today} 玩家回報《{g['title']}》bug：{note}\n")

    n_open = sum(1 for b in g["bugs"] if b["status"] == "open")
    print(f"🐞 已登記《{g['title']}》bug（待修 {n_open} 條）：{note}")
    print("   立刻修：python fix_game.py " + g["id"])
    print("   （不動它的話，週日 18:00 檢討排程會自動修）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
