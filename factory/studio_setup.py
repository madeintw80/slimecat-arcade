# -*- coding: utf-8 -*-
"""SlimeCat Studio 群組推播設定（2026-09-05：新品兩則介紹改推私人群組，不用新 bot、不用新程序）。

用法：
    python studio_setup.py --discover   # 從 bridge.log 找最近被 bridge 忽略的群組 chat_id（負數）
    python studio_setup.py <chat_id>    # 寫入 factory/studio_chat.json，並發一則測試訊息到群組
    python studio_setup.py --status     # 看目前設定
    python studio_setup.py --clear      # 清掉設定（新品推播改回 Boss 私訊）

Boss 操作流程（一次就好）：
    1. Telegram 開新群組「SlimeCat Studio」→ 把 Batnini bot 加進去
    2. 在群組打一則「/hi」（斜線開頭的訊息 bot 才收得到）；bridge 會在 log 記
       「ignore non-allowlisted chat_id=-100…」然後不理它（群組不在白名單，安全）
    3. 回電腦跑 --discover 拿到 chat_id → 跑 python studio_setup.py <chat_id>
    4. 群組收到「🐱 SlimeCat Studio 推播測試」就完成

只有「對外內容」（新品介紹＋工廠備註、修復完成）會進群組；失敗告警／檢討會週報／留言處理摘要
仍走 Boss 私訊（見 make_game.send_public / notify_fail）。
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
CFG = HERE / "studio_chat.json"
BRIDGE_LOG = Path("C:/Users/User/scripts/logs/bridge.log")

sys.path.insert(0, "C:/Users/User/projects/_common")
try:
    import batnini_telegram as tg
except Exception:
    tg = None


def discover() -> int:
    if not BRIDGE_LOG.exists():
        print(f"❌ 找不到 bridge log：{BRIDGE_LOG}")
        return 1
    with BRIDGE_LOG.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 2_000_000))
        text = f.read().decode("utf-8", errors="replace")
    seen = []
    for cid in re.findall(r"non-allowlisted chat_id=(-\d+)", text):
        if cid in seen:
            seen.remove(cid)
        seen.append(cid)   # 越後面越新
    if not seen:
        print("🔍 bridge.log 裡沒看到被忽略的群組訊息。先在群組打一則「/hi」再跑一次。")
        return 1
    print("🔍 最近被 bridge 忽略的群組 chat_id（最新在最上面）：")
    for cid in reversed(seen[-5:]):
        print(f"   {cid}")
    print(f"\n設定：python {Path(__file__)} {seen[-1]}")
    return 0


def status() -> int:
    if CFG.exists():
        print(f"📡 目前新品推播群組：{json.loads(CFG.read_text(encoding='utf-8')).get('chat_id')}")
    else:
        print("📡 尚未設定群組，新品推播走 Boss 私訊（預設對象）")
    return 0


def set_chat(cid: str) -> int:
    if not re.fullmatch(r"-?\d+", cid):
        print(f"❌ chat_id 要是整數（群組通常是負數），拿到的是：{cid}")
        return 1
    CFG.write_text(json.dumps({"chat_id": cid, "note": "SlimeCat Studio 群組；由 studio_setup.py 設定"},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已寫 {CFG.name}：chat_id={cid}")
    if tg and tg.available():
        ok = tg.send("🐱 SlimeCat Studio 推播測試：之後每週六新品的兩則介紹（靈感／機制／怎麼玩＋工廠備註）"
                     "都會發在這裡。玩完到大廳按「評分」留一句，工廠會照留言改。", chat_id=cid)
        print("✅ 測試訊息已送達群組" if ok else "❌ 測試訊息送不出去（bot 加進群組了嗎？chat_id 對嗎？）")
        return 0 if ok else 1
    print("⚠️ Telegram 模組不可用，沒發測試訊息")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    arg = sys.argv[1]
    if arg == "--discover":
        return discover()
    if arg == "--status":
        return status()
    if arg == "--clear":
        CFG.unlink(missing_ok=True)
        print("✅ 已清掉群組設定，新品推播改回 Boss 私訊")
        return 0
    return set_chat(arg)


if __name__ == "__main__":
    sys.exit(main())
