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

骨架鎖定：factory/skeleton_lock.json 有今天適用的鎖定（date～date+grace_days）時，不帶參數的週更
跳過抓榜／解構，直接用鎖定規格當靈感，合約 genre 強制成鎖定類型（--pick／--decon 照舊優先）。

排程（run_factory.bat）跑的就是不帶參數的版本；撞額度時 make_game.schedule_retry 會排補跑，
補跑那輪看到 v3_resume.json 指標就自動續跑上一輪（不用重付已完成的階段）。
v2.2 單線管線（make_game.py）保留當退路。
"""
import argparse
import datetime
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


SKELETON_LOCK_FILE = HERE / "skeleton_lock.json"


def active_skeleton_lock(today: datetime.date = None, path: Path = None) -> dict:
    """查 skeleton_lock.json：今天落在某筆鎖定的 date～date+grace_days 內就回那筆，否則回 {}。
    （2026-10-13：檢討會連六週押塔防＋波次都沒落地，改成設定檔硬鎖，週更不再從榜單挑骨架）"""
    today = today or datetime.date.today()
    path = path or SKELETON_LOCK_FILE
    if not path.exists():
        return {}
    try:
        locks = json.loads(path.read_text(encoding="utf-8")).get("locks") or []
    except ValueError:
        return {}
    for lk in locks:
        try:
            start = datetime.date.fromisoformat(lk["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if start <= today <= start + datetime.timedelta(days=int(lk.get("grace_days", 0))):
            return lk
    return {}


def skeleton_decon(lock: dict) -> dict:
    """把鎖定規格組成一份「解構筆記」交給 v3 生產線（不呼叫模型、不抓榜）。
    locked_genre 讓 validate_contract 把合約 genre 強制成鎖定的類型。"""
    rules = "\n".join(f"- {r}" for r in lock.get("core_rules", []))
    spec = "\n".join(f"- {r}" for r in lock.get("spec", []))
    doc = f"""# 骨架鎖定：{lock['skeleton']}（{lock['date']} 週更，Boss 拍板）

這一場**不從排行榜挑靈感**，骨架已鎖定為「{lock['skeleton']}」，企劃書與引擎都必須照這個骨架做，
不可改成益智、消除、整理、技巧或放鬆類。主題、美術、敵我角色自由發揮，但核心迴圈＝放塔擋波次。

## 為什麼鎖定
{lock.get('reason', '')}

## 核心規則（三條都要做到，企劃書驗收條目要寫出可觀察的數字）
{rules}

## 規格（沿用 2026-10-04／10-11 檢討會版）
{spec}
"""
    return {
        "source": f"骨架鎖定：{lock['skeleton']}",
        "title": lock.get("title", ""),
        "genre": mg.normalize_genre(lock.get("genre", "")),
        "locked_genre": mg.normalize_genre(lock.get("genre", "")),
        "origin": "locked",
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

    lock = {} if (args.pick or args.decon) else active_skeleton_lock()
    if args.decon:
        decon = load_decon_file(Path(args.decon))
        mg.log(f"📖 用既有解構筆記：{decon['source']}（{Path(args.decon).name}）")
    elif lock:
        decon = skeleton_decon(lock)
        mg.log(f"🔒 骨架鎖定：{lock['skeleton']}（{lock['date']} 起 {lock.get('grace_days', 0)} 天內有效）"
               f"→ 不抓榜、不解構，直接進企劃書")
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
