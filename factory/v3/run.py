# -*- coding: utf-8 -*-
"""v3 的「一輪紀錄」：factory/runs/<run_id>/ 資料夾＋run.json 狀態。

為什麼每階段都落檔：
  1. 出事可驗屍（引擎交了什麼、內容包哪裡不合 schema、評審說了什麼，全都在資料夾裡）
  2. 撞額度補跑可以從斷點續跑——引擎那一階段要 $3～4、十幾分鐘，不該因為評審撞額度就整輪重付
  3. Echo 稽核／Boss 本機試玩都能直接讀檔

資料夾內容（依階段陸續出現）：
  decon.json / decon.md      解構筆記（或原創企劃）
  plan.md / contract.json    企劃書＋模組合約
  engine.html                引擎（內含 examples 版 SC_CONTENT）
  content_<key>.json         各內容包
  assembled.html             組裝完成（品管用的版本，不含 stats 標籤）
  qa.json / review.json      品管結果／評審結果
  patch.txt / polished.html  打磨 patch 與套用後版本
  run.json                   狀態（各階段完成時間、gid、用量小計）
"""
import datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # factory/
RUNS_DIR = HERE / "runs"
RESUME_PTR = HERE / "v3_resume.json"   # 撞額度時記「哪一輪要續跑」（gitignored）
RESUME_MAX_HOURS = 36                  # 指標超過這麼久就當過期（別把上上週的半成品接回來）


class Run:
    """一輪 v3 生產的資料夾操作。run_id 不給＝開新的一輪。"""

    def __init__(self, run_id: str = None):
        RUNS_DIR.mkdir(exist_ok=True)
        self.id = run_id or "v3-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = RUNS_DIR / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.dir / "run.json"
        self.state = self._load_state()

    # ---- 狀態 ----
    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"id": self.id,
                    "created": datetime.datetime.now().isoformat(timespec="seconds"),
                    "stages": {}}

    def save(self) -> None:
        self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2),
                                   encoding="utf-8")

    def mark(self, stage: str, **info) -> None:
        """記某階段完成（含附帶資訊，例如用了哪個模型、幾筆內容）。"""
        rec = {"done_at": datetime.datetime.now().isoformat(timespec="seconds")}
        rec.update(info)
        self.state.setdefault("stages", {})[stage] = rec
        self.save()

    def unmark(self, stage: str) -> None:
        """把某階段標回未完成（例如引擎品管沒過要重生）。"""
        self.state.setdefault("stages", {}).pop(stage, None)
        self.save()

    def done(self, stage: str) -> bool:
        return stage in self.state.get("stages", {})

    def set(self, key: str, value) -> None:
        self.state[key] = value
        self.save()

    def get(self, key: str, default=None):
        return self.state.get(key, default)

    # ---- 檔案 ----
    def path(self, name: str) -> Path:
        return self.dir / name

    def has(self, name: str) -> bool:
        return (self.dir / name).exists()

    def write_text(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def read_text(self, name: str) -> str:
        return (self.dir / name).read_text(encoding="utf-8")

    def write_json(self, name: str, obj) -> Path:
        return self.write_text(name, json.dumps(obj, ensure_ascii=False, indent=2))

    def read_json(self, name: str):
        return json.loads(self.read_text(name))

    # ---- 撞額度續跑指標 ----
    def set_resume_pointer(self) -> None:
        RESUME_PTR.write_text(json.dumps(
            {"run_id": self.id, "at": datetime.datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def clear_resume_pointer() -> None:
        try:
            RESUME_PTR.unlink()
        except OSError:
            pass

    @staticmethod
    def pending_resume() -> str:
        """有沒有一輪等著續跑？回 run_id 或空字串（指標過期／資料夾不在＝當沒有）。"""
        try:
            ptr = json.loads(RESUME_PTR.read_text(encoding="utf-8"))
            at = datetime.datetime.fromisoformat(ptr["at"])
            rid = ptr["run_id"]
        except (OSError, ValueError, KeyError, TypeError):
            return ""
        if datetime.datetime.now() - at > datetime.timedelta(hours=RESUME_MAX_HOURS):
            return ""
        if not (RUNS_DIR / rid / "run.json").exists():
            return ""
        return rid

    def summary(self) -> str:
        stages = self.state.get("stages", {})
        return f"{self.id}：" + "→".join(stages.keys()) if stages else f"{self.id}：（還沒開始）"
