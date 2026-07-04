# -*- coding: utf-8 -*-
"""建立/更新 SlimeCat 遊戲工廠的每日排程。

做兩件事：
  1. 產生 run_factory.bat
     （CRLF＋純 ASCII＋python 絕對路徑 —— Windows 排程器的三個地雷都避開）
  2. schtasks 建立每天 12:00 的排程（重跑本腳本 = 更新設定，冪等）
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "run_factory.bat"
TASK_NAME = "SlimeCat Factory Daily"
RUN_AT = "12:00"

PYTHON = sys.executable  # 真實 python 絕對路徑（不能用 WindowsApps 假捷徑）


def write_bat() -> None:
    make_game = ROOT / "factory" / "make_game.py"
    logf = ROOT / "factory" / "factory.log"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f'"{PYTHON}" "{make_game}" >> "{logf}" 2>&1',
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
        print(f"✅ 排程「{TASK_NAME}」已建立：每天 {RUN_AT} 自動生一款新遊戲")
        print(f'   暫停生產：schtasks /Change /TN "{TASK_NAME}" /Disable')
        print(f'   立刻生一款：schtasks /Run /TN "{TASK_NAME}"')
    return proc.returncode


if __name__ == "__main__":
    write_bat()
    sys.exit(create_task())
