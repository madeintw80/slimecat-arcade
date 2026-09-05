# -*- coding: utf-8 -*-
"""用量對帳（v3 Phase 2 第 5 項）：把 factory/usage.jsonl 依「階段」與「每款遊戲」彙總成表。

每次 claude -p 呼叫都會記一行（stage／model／effort／tokens／CLI 自報 cost／秒數），
跑三～四款後拿這張表比「每階段成本 vs 品質」，決定 effort 與模型（改 v3/stages.py 頂端常數）。

用法：
    python usage_report.py            # 近 30 天
    python usage_report.py --days 90
    python usage_report.py --runs     # 額外列 factory/runs/ 每輪（run.json）的階段小計
"""
import argparse
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
USAGE_LOG = HERE / "usage.jsonl"
RUNS_DIR = HERE / "runs"


def load(days: int) -> list:
    if not USAGE_LOG.exists():
        return []
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    rows = []
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("ts", "") >= cutoff:
            rows.append(r)
    return rows


def k(n: float) -> str:
    return f"{n/1000:.0f}k" if n >= 1000 else f"{n:.0f}"


def by_stage(rows: list) -> str:
    agg = defaultdict(lambda: {"calls": 0, "in": 0, "cache_r": 0, "out": 0, "cost": 0.0, "secs": 0, "models": set()})
    for r in rows:
        stage = r.get("stage") or "?"
        a = agg[stage]
        a["calls"] += 1
        a["in"] += r.get("in", 0) + r.get("cache_w", 0)
        a["cache_r"] += r.get("cache_r", 0)
        a["out"] += r.get("out", 0)
        a["cost"] += r.get("cost_usd", 0)
        a["secs"] += r.get("secs", 0)
        a["models"].add(f"{r.get('model')}{'/' + r['effort'] if r.get('effort') else ''}")
    lines = [f"{'階段':<20}{'次':>4}{'in':>8}{'cache':>8}{'out':>8}{'$':>8}{'平均秒':>8}  模型/effort"]
    total = 0.0
    for stage, a in sorted(agg.items(), key=lambda x: -x[1]["cost"]):
        total += a["cost"]
        lines.append(f"{stage:<20}{a['calls']:>4}{k(a['in']):>8}{k(a['cache_r']):>8}{k(a['out']):>8}"
                     f"{a['cost']:>8.2f}{a['secs'] // max(1, a['calls']):>8}  {'、'.join(sorted(a['models']))}")
    lines.append(f"{'合計':<20}{len(rows):>4}{'':>24}{total:>8.2f}")
    return "\n".join(lines)


def by_day(rows: list) -> str:
    agg = defaultdict(lambda: {"calls": 0, "cost": 0.0, "v3": 0})
    for r in rows:
        d = r.get("ts", "")[:10]
        agg[d]["calls"] += 1
        agg[d]["cost"] += r.get("cost_usd", 0)
        agg[d]["v3"] += 1 if str(r.get("stage", "")).startswith("v3-") else 0
    lines = [f"{'日期':<12}{'呼叫':>6}{'v3 呼叫':>8}{'$':>8}"]
    for d, a in sorted(agg.items()):
        lines.append(f"{d:<12}{a['calls']:>6}{a['v3']:>8}{a['cost']:>8.2f}")
    return "\n".join(lines)


def by_run() -> str:
    if not RUNS_DIR.exists():
        return "（還沒有 v3 run）"
    lines = []
    for rd in sorted(RUNS_DIR.iterdir()):
        u = rd / "usage.json"
        st = rd / "run.json"
        if not st.exists():
            continue
        state = json.loads(st.read_text(encoding="utf-8"))
        stages = state.get("stages", {})
        title = stages.get("plan", {}).get("title", "?")
        reviewer = ""
        rv = rd / "review.json"
        if rv.exists():
            try:
                r = json.loads(rv.read_text(encoding="utf-8"))
                reviewer = f"{r.get('total')}/50 by {r.get('reviewer')}"
            except ValueError:
                pass
        cost = ""
        if u.exists():
            try:
                recs = json.loads(u.read_text(encoding="utf-8")).get("records", [])
                cost = f"${sum(x.get('cost_usd', 0) for x in recs):.2f}（{len(recs)} 次）"
                per = defaultdict(float)
                for x in recs:
                    per[x.get("stage", "?")] += x.get("cost_usd", 0)
                cost += " ＝ " + "＋".join(f"{s} {c:.2f}" for s, c in sorted(per.items(), key=lambda y: -y[1]))
            except ValueError:
                pass
        lines.append(f"{rd.name}《{title}》 階段：{'→'.join(stages)}｜評審 {reviewer or '—'}｜{cost or '（未收工）'}")
    return "\n".join(lines) or "（還沒有 v3 run）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--runs", action="store_true")
    args = ap.parse_args()
    rows = load(args.days)
    print(f"📊 SlimeCat 用量對帳（近 {args.days} 天，{len(rows)} 次呼叫；$ 為 CLI 依牌價估、Max 訂閱實際不另計費）")
    print("── 依階段 ──")
    print(by_stage(rows))
    print("── 依日期 ──")
    print(by_day(rows))
    if args.runs:
        print("── 依 v3 run ──")
        print(by_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
