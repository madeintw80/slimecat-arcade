# -*- coding: utf-8 -*-
"""把遊戲區推上 GitHub Pages（工廠每次上架新遊戲後自動呼叫，也可手動跑）。

用法：
    python publish_site.py [提交訊息]
"""
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

# 🔴 部署白名單（2026-07-12 健檢批1）：只有「站點內容」會被自動 commit + push。
# 故意不含 factory/*.py、run_*.bat、apps_script/ —— 程式碼變更屬於開發行為，
# 要人看過再手動 commit，不給工廠 add -A 自動夾帶上公開站。
PUBLISH_PATHS = [
    "index.html", "games.js", "games.json", "stats.js", "sc_config.js",
    "games/",                    # 遊戲本體＋截圖
    "factory/history.json",      # 上架紀錄
    "factory/knowledge/",        # 解構筆記／learnings（檢討排程會更新）
    "DESIGN.md",                 # 設計聖經（週檢討會回修）
]

# 白名單路徑內若出現長得像機密的檔名，一律擋下不部署（第二層保險；
# 這支跑在 python subprocess 裡，不會經過 Claude 的 secret_guard hook）
SECRET_NAME = re.compile(
    r"(^|/)(\.env(\..*)?|[^/]*\.env|auth\.json|token\.json"
    r"|.*credential.*|.*\.pem|.*\.key|.*\.p12)$", re.I)


def _git(*args):
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def publish(msg: str = "🏭 SlimeCat 遊戲區更新") -> int:
    _git("add", "--", *PUBLISH_PATHS)
    staged = [n.strip() for n in _git("diff", "--cached", "--name-only").stdout.splitlines() if n.strip()]
    if not staged:
        print("ℹ️ 沒有變更，不用部署")
        return 0
    bad = [n for n in staged if SECRET_NAME.search(n)]
    if bad:
        _git("reset")  # 只退 staging，不動工作區
        raise RuntimeError("疑似機密檔被擋下、未部署：" + ", ".join(bad[:5]))
    c = _git("commit", "-m", msg)
    if c.returncode != 0:
        # 🔴 失敗改用 raise（原本 return 1 呼叫端不看→靜默失敗：站沒更新卻已推「新品出爐」）。
        # 讓上層的 try/except 接住 → 記 log／改發失敗告警。
        raise RuntimeError(f"commit 失敗：{c.stderr[-300:]}")
    p = _git("push", "origin", "main")
    if p.returncode != 0:
        raise RuntimeError(f"push 失敗：{p.stderr[-300:]}")
    print(f"🚀 已部署：{msg}")
    print("   （GitHub Pages 約 1-2 分鐘後生效）")
    return 0


if __name__ == "__main__":
    message = " ".join(sys.argv[1:]) or "🏭 SlimeCat 遊戲區更新"
    # 直接在命令列跑時，把 raise 轉回乾淨的 exit 1（保留原本 CLI 退出碼契約，不噴 traceback）
    try:
        sys.exit(publish(message))
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
