# -*- coding: utf-8 -*-
"""建立「每週日 18:00 檢討」排程（run_weekly.bat + schtasks，冪等可重跑）。"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "run_weekly.bat"
TASK_NAME = "SlimeCat Weekly Review"

PYTHON = sys.executable  # 真實 python 絕對路徑（不能用 WindowsApps 假捷徑）


def write_bat() -> None:
    script = ROOT / "factory" / "weekly_review.py"
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
           "/SC", "WEEKLY", "/D", "SUN", "/ST", "18:00", "/F"]
    proc = subprocess.run(cmd, capture_output=True)
    print((proc.stdout + proc.stderr).decode("cp950", errors="replace").strip())
    if proc.returncode == 0:
        print(f"✅ 排程「{TASK_NAME}」已建立：每週日 18:00 檢討")
    return proc.returncode


if __name__ == "__main__":
    write_bat()
    sys.exit(create_task())
