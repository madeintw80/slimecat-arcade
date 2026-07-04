# -*- coding: utf-8 -*-
"""立刻開一場檢討會（不等排程）。

原理：觸發「SlimeCat Weekly Review」排程任務 → run_weekly.bat 在背景跑 weekly_review.py。
fire-and-forget：這支腳本秒回，檢討完成（約 5~20 分鐘，若有 open bugs 要先修會更久）
會自己推 Telegram 檢討報告。Telegram listen session 用這支，不用自己等長任務。
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

TASK_NAME = "SlimeCat Weekly Review"


def main() -> int:
    proc = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True)
    out = (proc.stdout + proc.stderr).decode("cp950", errors="replace").strip()
    if proc.returncode == 0:
        print("📅 已叫製作人立刻開檢討會！")
        print("   流程（修 open bugs→拉數據→claude 檢討→更新設計聖經）約 5~20 分鐘，")
        print("   完成會自動推 Telegram 檢討報告，不用等在這。")
        print("   進度可看：C:/Users/User/projects/SlimeCatArcade/factory/factory.log")
        print("   （若檢討已在跑，重複觸發不會開第二場）")
    else:
        print(f"❌ 觸發失敗：{out}")
        print('   備援：直接跑 python C:/Users/User/projects/SlimeCatArcade/factory/weekly_review.py')
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
