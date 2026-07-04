# -*- coding: utf-8 -*-
"""建立/更新「每日留言處理」排程（照 setup_schedule.py 的慣例）。

做兩件事：
  1. 產生 run_feedback.bat（CRLF＋純 ASCII＋python 絕對路徑，避開排程器三地雷）
  2. schtasks 建每天 11:30 的排程（在 12:00 生產之前，讓當天新遊戲吃到最新留言教訓）
     重跑本腳本＝更新設定，冪等
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "run_feedback.bat"
TASK_NAME = "SlimeCat Daily Feedback"
RUN_AT = "11:30"

PYTHON = sys.executable  # 真實 python 絕對路徑（不能用 WindowsApps 假捷徑）


def write_bat() -> None:
    script = ROOT / "factory" / "daily_feedback.py"
    logf = ROOT / "factory" / "factory.log"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f'"{PYTHON}" "{script}" >> "{logf}" 2>&1',
        "",
    ]
    BAT.write_bytes("\r\n".join(lines).encode("ascii"))
    print(f"✅ 已寫 {BAT}")


def create_task() -> int:
    cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", str(BAT),
           "/SC", "DAILY", "/ST", RUN_AT, "/F"]
    proc = subprocess.run(cmd, capture_output=True)
    out = (proc.stdout + proc.stderr).decode("cp950", errors="replace").strip()
    print(out)
    if proc.returncode == 0:
        print(f"✅ 排程「{TASK_NAME}」已建立：每天 {RUN_AT} 讀玩家留言（能改的改款、都會回覆）")
        print(f'   暫停：schtasks /Change /TN "{TASK_NAME}" /Disable')
        print(f'   立刻跑一次：schtasks /Run /TN "{TASK_NAME}"')
    return proc.returncode


if __name__ == "__main__":
    write_bat()
    sys.exit(create_task())
