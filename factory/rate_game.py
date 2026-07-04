# -*- coding: utf-8 -*-
"""玩家評分入口 —— 學習迴圈裡權重最高的訊號（玩家評分 > AI 自評 > 理論）。

用法：
    python rate_game.py <遊戲名或id關鍵字> <1-10> [評語]
例：
    python rate_game.py 彈跳 8 手感很好但後期太簡單

做三件事：
  1. 寫進 games.json（大廳卡片會顯示 👤 分數）
  2. 追加到 knowledge/learnings.md（工廠下次生產會讀，據此調整設計）
  3. 重建 games.js
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

sys.path.insert(0, str(HERE))
import rebuild  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: python rate_game.py <遊戲名或id關鍵字> <1-10> [評語]")
        return 2
    query = sys.argv[1].strip()
    try:
        score = int(sys.argv[2])
        assert 1 <= score <= 10
    except (ValueError, AssertionError):
        print("❌ 分數要是 1~10 的整數")
        return 2
    note = " ".join(sys.argv[3:]).strip()

    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    hits = [g for g in data["games"] if query in g["title"] or query in g["id"]]
    if not hits:
        print(f"❌ 找不到遊戲「{query}」。目前有：")
        for g in data["games"]:
            print(f"   - {g['title']}（{g['id']}）")
        return 1
    if len(hits) > 1:
        print(f"⚠️ 「{query}」對到多款，請講更完整的名字：")
        for g in hits:
            print(f"   - {g['title']}（{g['id']}）")
        return 1

    g = hits[0]
    g["user_rating"] = score
    if note:
        g["user_note"] = note
    g["rated_at"] = datetime.date.today().isoformat()
    GAMES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    rebuild.rebuild()

    # 追加教訓（工廠下次生產會讀最新 60 行）
    line = f"- {g['rated_at']} 玩家評《{g['title']}》{score}/10"
    if note:
        line += f"：{note}"
    with LEARN_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    print(f"✅ 已記錄：《{g['title']}》玩家評 {score}/10" + (f"：{note}" if note else ""))
    print("   這條回饋會餵給工廠，影響下一款的設計。")

    # 順便秀目前戰績榜
    rated = [x for x in data["games"] if x.get("user_rating")]
    if rated:
        print("\n📊 玩家評分榜：")
        for x in sorted(rated, key=lambda v: -v["user_rating"]):
            ai = f"｜AI {x['ai_score']}/50" if x.get("ai_score") else ""
            print(f"   {x['user_rating']}/10 《{x['title']}》{ai}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
