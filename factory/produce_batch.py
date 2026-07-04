# -*- coding: utf-8 -*-
"""批量生產：串行連生 N 款遊戲（每款完整走 解構→設計→品管→自評→上架→部署→推播）。

用法：
    python produce_batch.py [N]          # 串行生 N 款（預設 3），前景跑
    python produce_batch.py [N] --spawn  # 背景開工立刻返回（Telegram listen 用）

設計說明：
  - 為什麼串行不並行：多個 make_game 同時跑會撞 games.json / 編號 / git push
  - 開跑前若工廠已有一輪在生產（每日排程或「生一個新遊戲」），會先等它完成
  - 批量期間別再按「生一個新遊戲」（會並行撞車）
"""
import datetime
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent

sys.path.insert(0, "C:/Users/User/projects/_common")
try:
    import batnini_telegram as tg
except Exception:
    tg = None

PER_GAME_TIMEOUT = 7200  # 單款上限（兩次嘗試 45 分鐘 + 品管自評的餘裕）


def log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def factory_running() -> bool:
    """看系統上有沒有別的 make_game.py 程序在跑（避免並行撞 games.json）。"""
    try:
        import psutil
    except ImportError:
        return False  # 沒 psutil 就不等（機率低，接受）
    me = str(Path(__file__))
    for p in psutil.process_iter(["cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if "make_game.py" in cmd and me not in cmd:
                return True
        except Exception:
            pass
    return False


def spawn_detached(n: int) -> None:
    """背景開工立刻返回（Telegram listen 的 Bash 有 10 分鐘上限）。"""
    args = [sys.executable, str(Path(__file__).resolve()), str(n)]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    logf = (HERE / "factory.log").open("a", encoding="utf-8")
    subprocess.Popen(args, creationflags=flags, stdout=logf, stderr=subprocess.STDOUT)
    print(f"🏭 批量生產已在背景開工：目標 {n} 款、串行生產")
    print(f"   每款約 20~45 分鐘，每款出爐都會推 Telegram，全部收工再推總結")
    print(f"   ⚠️ 批量期間別再按「生一個新遊戲」（會撞車）；進度看 factory/factory.log")


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--spawn"]
    n = 3
    if argv:
        try:
            n = max(1, min(10, int(argv[0])))  # 1~10 款，防手滑打錯數字
        except ValueError:
            print("用法: python produce_batch.py [N] [--spawn]")
            return 2

    if "--spawn" in sys.argv:
        spawn_detached(n)
        return 0

    log(f"🏭 批量生產開始：目標 {n} 款（串行）")

    # 等既有生產完成（每日排程或手動觸發的那輪）
    waited = 0
    while factory_running():
        if waited == 0:
            log("⏳ 工廠已有一輪在生產，等它完成再開始批量…")
        time.sleep(60)
        waited += 1
        if waited > 90:  # 90 分鐘還沒完＝卡死，放棄等待直接報錯
            log("❌ 等了 90 分鐘前一輪還沒結束，批量取消（看 factory.log 查原因）")
            if tg and tg.available():
                tg.send("🏭❌ 批量生產取消：前一輪生產卡住超過 90 分鐘，請回電腦看 factory.log")
            return 1

    made, failed = 0, 0
    for i in range(1, n + 1):
        log(f"────── 批量進度 {i}/{n} ──────")
        try:
            r = subprocess.run([sys.executable, str(HERE / "make_game.py")],
                               timeout=PER_GAME_TIMEOUT)
            ok = (r.returncode == 0)
        except subprocess.TimeoutExpired:
            log(f"❌ 第 {i} 款超過 {PER_GAME_TIMEOUT//60} 分鐘，強制跳過")
            ok = False
        made += ok
        failed += (not ok)
        time.sleep(5)  # 喘口氣（git push / Telegram 推播收尾）

    log(f"🏁 批量生產收工：成功 {made} 款、失敗 {failed} 款（目標 {n}）")
    if tg and tg.available():
        try:
            tg.send(f"🏭🏁 SlimeCat 批量生產收工！\n"
                    f"成功 {made} 款、失敗 {failed} 款（目標 {n}）\n"
                    f"每款詳情看上面的新品通知；玩完記得「遊戲評分」餵回工廠 🐱")
        except Exception:
            pass
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
