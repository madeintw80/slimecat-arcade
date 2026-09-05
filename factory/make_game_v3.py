# -*- coding: utf-8 -*-
"""SlimeCat 遊戲工作室 v3 入口 —— 一週一款・大型化・靈感探索器（2026-09-05 Phase 1）。

用法：
    python make_game_v3.py                     # 全流程：抓榜（App Store＋Steam）→ 解構 → v3 生產線 → 上架
    python make_game_v3.py --pick "遊戲名"     # 先點名解構（不看榜）再生產
    python make_game_v3.py --decon <筆記路徑>  # 用既有解構筆記（「解構 <遊戲名>」存的）直接生產
    python make_game_v3.py --resume <run_id>   # 從 factory/runs/<run_id>/ 的斷點續跑
    python make_game_v3.py --regen <run_id> --packs scenes,objects   # 已上架遊戲：重生指定內容包（沿用引擎）並覆蓋上線
    python make_game_v3.py --polish <run_id>   # 已上架遊戲：用最新評審的稽核 bug／合約缺陷再打磨一輪（patch）
    python make_game_v3.py --no-publish        # 跑到上架為止，不部署不推播（開發用）
    python make_game_v3.py --no-echo           # 評審不問 Echo，直接 sonnet

排程（run_factory.bat）跑的就是不帶參數的版本；撞額度時 make_game.schedule_retry 會排補跑，
補跑那輪看到 v3_resume.json 指標就自動續跑上一輪（不用重付已完成的階段）。
v2.2 單線管線（make_game.py）保留當退路。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch_trends          # noqa: E402
import make_game as mg       # noqa: E402
from v3 import pipeline      # noqa: E402
from v3.run import Run       # noqa: E402


def load_decon_file(path: Path) -> dict:
    """讀既有解構筆記：旁邊有 .json 側檔（save_decon 存的標頭）就用，沒有就從標題行推 source。"""
    path = Path(path)
    doc = path.read_text(encoding="utf-8")
    meta = {}
    side = path.with_suffix(".json")
    if side.exists():
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    m = re.search(r"^#\s*解構[：:]\s*(.+)$", doc, re.M)
    return {
        "source": meta.get("source") or (m.group(1).strip() if m else path.stem),
        "title": meta.get("title", ""),
        "genre": mg.normalize_genre(meta.get("genre", "")),
        "origin": meta.get("origin", "note"),
        "doc": doc.strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="SlimeCat v3 生產線")
    ap.add_argument("--pick", default="", help="點名解構的遊戲名（不看榜）")
    ap.add_argument("--decon", default="", help="既有解構筆記路徑")
    ap.add_argument("--resume", default="", help="續跑的 run_id")
    ap.add_argument("--regen", default="", help="已上架遊戲：重生內容包的 run_id（配 --packs）")
    ap.add_argument("--packs", default="", help="--regen 要重生的內容包 key，逗號分隔")
    ap.add_argument("--polish", default="", help="已上架遊戲：用最新評審的稽核結果再打磨一輪的 run_id")
    ap.add_argument("--no-publish", action="store_true", help="不部署不推播")
    ap.add_argument("--no-echo", action="store_true", help="評審不問 Echo")
    args = ap.parse_args()
    if args.no_echo:
        pipeline.USE_ECHO = False

    if args.regen:
        keys = [k.strip() for k in args.packs.split(",") if k.strip()]
        if not keys:
            print("--regen 要配 --packs <key,key>（例 --packs scenes）")
            return 2
        return pipeline.regen_content(Run(args.regen), keys, publish=not args.no_publish)
    if args.polish:
        return pipeline.polish_released(Run(args.polish), publish=not args.no_publish)

    mg.log("🏭 SlimeCat 遊戲工作室 v3 開工（企劃書 → 引擎 → 內容包 → 組裝 → 品管 → 評審 → 打磨）")
    mg.clear_retry("factory")   # 這輪若是補跑本身，先把一次性排程收掉

    # 續跑：明講 --resume，或排程補跑時發現有續跑指標
    rid = args.resume or ("" if (args.pick or args.decon) else Run.pending_resume())
    if rid:
        run = Run(rid)
        mg.log(f"⏯️ 續跑 {run.summary()}")
        return pipeline.produce_v3(None, run=run, publish=not args.no_publish)

    if args.decon:
        decon = load_decon_file(Path(args.decon))
        mg.log(f"📖 用既有解構筆記：{decon['source']}（{Path(args.decon).name}）")
    else:
        history = (json.loads(mg.HISTORY_FILE.read_text(encoding="utf-8"))
                   if mg.HISTORY_FILE.exists() else {"used": []})
        data = json.loads(mg.GAMES_JSON.read_text(encoding="utf-8"))
        try:
            if args.pick:
                mg.log(f"🔍 點名解構《{args.pick}》…")
                decon = mg.stage_deconstruct(None, history, data["games"], pick=args.pick)
            else:
                trends = fetch_trends.fetch()
                mg.log(f"📈 榜單 OK（App Store {len(trends['games'])} 款、"
                       f"Steam {len((trends.get('steam') or {}).get('games', []))} 款）")
                mg.log("🔍 策劃解構中（兩份榜單挑一款、拆解上癮機制）…")
                decon = mg.stage_deconstruct(trends, history, data["games"])
            note = mg.save_decon(decon)
            mg.log(f"📖 解構完成：{decon['source']}（{decon['origin']}）→ {note.name}")
        except mg.QuotaError as e:
            mg.log(f"⏳ 解構撞額度：{e}")
            return 0 if mg.schedule_retry("factory", e.resets_at, str(e)) else 1
        except Exception as e:  # noqa: BLE001
            mg.log(f"❌ 靈感／解構階段失敗：{e}")
            mg.notify_fail(f"靈感／解構階段失敗：{e}")
            return 1

    return pipeline.produce_v3(decon, publish=not args.no_publish)


if __name__ == "__main__":
    sys.exit(main())
