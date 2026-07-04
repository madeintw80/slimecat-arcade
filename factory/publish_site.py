# -*- coding: utf-8 -*-
"""把遊戲區推上 GitHub Pages（工廠每次上架新遊戲後自動呼叫，也可手動跑）。

用法：
    python publish_site.py [提交訊息]
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def _git(*args):
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def publish(msg: str = "🏭 SlimeCat 遊戲區更新") -> int:
    _git("add", "-A")
    if not _git("status", "--porcelain").stdout.strip():
        print("ℹ️ 沒有變更，不用部署")
        return 0
    c = _git("commit", "-m", msg)
    if c.returncode != 0:
        print(f"❌ commit 失敗：{c.stderr[-300:]}")
        return 1
    p = _git("push", "origin", "main")
    if p.returncode != 0:
        print(f"❌ push 失敗：{p.stderr[-300:]}")
        return 1
    print(f"🚀 已部署：{msg}")
    print("   （GitHub Pages 約 1-2 分鐘後生效）")
    return 0


if __name__ == "__main__":
    message = " ".join(sys.argv[1:]) or "🏭 SlimeCat 遊戲區更新"
    sys.exit(publish(message))
