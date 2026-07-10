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
