# -*- coding: utf-8 -*-
"""「解構 <遊戲名>」—— 靈感探索器的手動入口（2026-09-05 Boss 拍板 6B+C）。

只做三件事：解構（opus）→ 存筆記到 knowledge/deconstructions/ → 回摘要。**不生產**。
之後想照這份筆記做遊戲：python make_game_v3.py --decon <筆記路徑>

用法：
    python decon_now.py "遊戲名"            # 前景跑（約 2～3 分鐘），摘要印在 stdout
    python decon_now.py "遊戲名" --spawn    # 背景跑立刻返回（Telegram 用），完成把摘要推到 Boss 私訊
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_game as mg   # noqa: E402

sys.path.insert(0, "C:/Users/User/projects/_common")
try:
    import batnini_telegram as tg
except Exception:
    tg = None


def summarize(decon: dict, note: Path) -> str:
    doc = decon.get("doc", "")
    origin = {"named": "Boss 點名", "steam": "Steam", "appstore": "App Store"}.get(decon.get("origin"), decon.get("origin", ""))
    lines = [
        f"🔍 解構完成：《{decon['source']}》（{origin}）",
        f"建議變形版：《{decon.get('title') or '（未命名）'}》｜類型 {decon.get('genre', '')}",
        f"🔁 核心迴圈：{mg.section(doc, '核心迴圈', 220) or '（見筆記）'}",
        f"🧠 上癮機制：{mg.section(doc, '上癮機制', 220) or '（見筆記）'}",
        f"🌀 變形版企劃：{mg.section(doc, '變形版', 220) or '（見筆記）'}",
        f"📖 筆記：factory/knowledge/deconstructions/{note.name}",
        f"要照這份做成遊戲：python C:/Users/User/projects/SlimeCatArcade/factory/make_game_v3.py --decon \"{note}\"",
    ]
    return "\n".join(lines)


def deconstruct(name: str) -> str:
    """跑解構＋存筆記，回摘要文字。撞額度／失敗直接 raise（手動指令不排補跑）。"""
    import json
    history = (json.loads(mg.HISTORY_FILE.read_text(encoding="utf-8"))
               if mg.HISTORY_FILE.exists() else {"used": []})
    data = json.loads(mg.GAMES_JSON.read_text(encoding="utf-8"))
    mg.log(f"🔍 點名解構《{name}》（{mg.MODEL_DECON}）…")
    decon = mg.stage_deconstruct(None, history, data["games"], pick=name)
    note = mg.save_decon(decon)
    mg.log(f"📖 解構完成：{decon['source']} → {note.name}")
    return summarize(decon, note)


def spawn_detached(name: str) -> None:
    args = [sys.executable, str(Path(__file__).resolve()), name, "--push"]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    logf = (HERE / "factory.log").open("a", encoding="utf-8")
    subprocess.Popen(args, creationflags=flags, stdout=logf, stderr=subprocess.STDOUT)
    print(f"🔍 解構《{name}》中…約 2～3 分鐘，完成會把摘要推到 Telegram（只解構、不生產）")
    print("   之後想做成遊戲，回電腦跑 make_game_v3.py --decon <筆記路徑>（摘要裡有）")


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not argv or not argv[0].strip():
        print('用法: python decon_now.py "<遊戲名>" [--spawn]')
        return 2
    name = argv[0].strip()
    if "--spawn" in sys.argv:
        spawn_detached(name)
        return 0
    push = "--push" in sys.argv
    try:
        summary = deconstruct(name)
    except Exception as e:  # noqa: BLE001
        msg = f"❌ 解構《{name}》失敗：{str(e)[:300]}"
        print(msg)
        if push and tg and tg.available():
            tg.send(msg)
        return 1
    print(summary)
    if push and tg and tg.available():
        tg.send(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
