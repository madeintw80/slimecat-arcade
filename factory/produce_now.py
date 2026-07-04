# -*- coding: utf-8 -*-
"""立刻叫工廠生一款新遊戲（不等每天 12:00 排程）。

原理：觸發排程任務 → run_factory.bat 在背景跑 make_game.py。
fire-and-forget：這支腳本秒回，生產完成（約 20~40 分鐘）工廠自己會推 Telegram。
Telegram listen session 用這支，不用自己等長任務。
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

TASK_NAME = "SlimeCat Factory Daily"


def main() -> int:
    proc = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True)
    out = (proc.stdout + proc.stderr).decode("cp950", errors="replace").strip()
    if proc.returncode == 0:
        print("🏭 已叫工廠立刻開工！")
        print("   全流程（解構→設計→品管→自評）約 20~40 分鐘，")
        print("   出爐會自動推 Telegram 新品通知＋截圖，不用等在這。")
        print("   進度可看：C:/Users/User/projects/SlimeCatArcade/factory/factory.log")
    else:
        print(f"❌ 觸發失敗：{out}")
        print('   備援：直接跑 python C:/Users/User/projects/SlimeCatArcade/factory/make_game.py')
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
