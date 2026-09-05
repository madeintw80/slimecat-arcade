# -*- coding: utf-8 -*-
"""Phase 2：委派 Echo（Codex）當「獨立評審＋整合稽核」。

流程：組評審 prompt（企劃書合約＋驗收清單＋組裝後原始碼）→ 寫進 run 資料夾的 echo_prompt.txt
     → Invoke-Echo.ps1（codex exec --json、sandbox read-only、prompt 走 -PromptFile）
     → 從委派記錄的 console.log 撈最後一則 agent_message 裡的 REVIEW JSON → normalize。

規則（2026-09-05 Boss 拍板）：
  - 不改 BRAIN.md 白名單：SlimeCat 仍保護模式、Echo 唯讀（read-only 沙盒、沒網路）
  - Echo 不可用（沒裝 codex／runner 失敗／逾時／撈不到 JSON）→ 丟 EchoUnavailableError，
    呼叫端 fail-open 回 sonnet 評審；「評得差」是正常回傳不是錯誤
  - 每次委派留 ~/agent-workspace/runs/<run-id>/（runner 自動建四檔，PROTOCOL 第十二節）
  - requested model 讀 Echo 本機 config（~/.codex/config.toml 的 model=），跟 EarningsCard 一樣對齊現役模型

範式來源：EarningsCard/verify_card.py（排程自動委派 Echo 首例）。
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # factory/
sys.path.insert(0, str(HERE))
import make_game as mg   # noqa: E402
from v3 import stages    # noqa: E402

RUNNER = Path("C:/Users/User/agent-workspace/runners/Invoke-Echo.ps1")
CODEX_CONFIG = Path("C:/Users/User/.codex/config.toml")
# 模型順序：先用 Echo config 現役模型；它若被 CLI 拒絕（2026-09-05 實測：codex-cli 0.144.1 跑 gpt-6-astra
# 回「requires a newer version of Codex」）就退到已驗證可跑的舊模型。Echo 升級 CLI 後不用改這裡。
FALLBACK_MODELS = ["gpt-5.6-sol"]
ECHO_EFFORT = "high"             # 評審＋稽核值得花；xhigh 留給對帳後決定
ECHO_TIMEOUT = 900               # 15 分鐘上限（原始碼 2,000 行、xhigh 以下夠用）
_NEEDS_UPGRADE_RE = re.compile(r"requires a newer version of Codex|Model metadata for .* not found|"
                               r"model .* (is not supported|not found|does not exist)", re.I)


class EchoUnavailableError(RuntimeError):
    """Echo 本身跑不動（≠評得差）：呼叫端回 sonnet。"""


def echo_model() -> str:
    """Echo 現役模型＝~/.codex/config.toml 的 model=（模型會輪替，別寫死）。"""
    try:
        m = re.search(r'^\s*model\s*=\s*"([^"]+)"', CODEX_CONFIG.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    return FALLBACK_MODELS[0]


def model_candidates() -> list:
    """要試的模型順序：config 現役 → 已驗證退路（去重）。"""
    out = [echo_model()]
    for m in FALLBACK_MODELS:
        if m not in out:
            out.append(m)
    return out


def available() -> bool:
    return RUNNER.exists() and bool(shutil.which("codex"))


def _model_rejected(run_dir: Path) -> bool:
    """委派失敗時看 console.log 是不是「CLI 太舊／模型不存在」——是的話換下一個模型再試。"""
    try:
        text = (run_dir / "console.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_NEEDS_UPGRADE_RE.search(text))


def _extract_review(run_dir: Path):
    """從委派記錄 console.log 撈最後一則 agent_message 的 REVIEW JSON。"""
    log_file = run_dir / "console.log"
    if not log_file.exists():
        return None
    text = None
    for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        item = obj.get("item") or {}
        if obj.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text") or text
    return stages.parse_review(text) if text else None


def _delegate(model: str, topic: str, task: str, workdir: Path, prompt_file: Path) -> tuple:
    """跑一次 runner。回 (returncode, stdout, run_dir)；逾時直接丟 EchoUnavailableError。"""
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER),
        "-Task", task, "-Topic", topic, "-Model", model, "-Effort", ECHO_EFFORT,
        "-Sandbox", "read-only", "-WorkDir", str(workdir),
        "-Permission", "唯讀（codex sandbox read-only，無網路）",
        "-PromptFile", str(prompt_file),
    ]
    # Popen＋殺程序樹：subprocess.run 的 timeout 在 Windows 殺不到孫程序（powershell→codex.exe）
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    try:
        stdout, stderr = proc.communicate(timeout=ECHO_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            import psutil
            root = psutil.Process(proc.pid)
            for child in root.children(recursive=True):
                child.kill()
            root.kill()
        except Exception:
            pass
        raise EchoUnavailableError(f"Echo 評審逾時（>{ECHO_TIMEOUT // 60} 分鐘，程序樹已清）")
    m = re.search(r"Run path\s*:\s*(.+)", stdout or "")
    run_dir = Path(m.group(1).strip()) if m else None
    return proc.returncode, (stdout or "") + (stderr or ""), run_dir


def review(run, plan_doc: str, contract: dict, html: str, qa_info: dict = None, gid: str = "") -> dict:
    """委派 Echo 評審。回 normalize 後的 review dict（含 reviewer／echo_run）；不可用丟 EchoUnavailableError。"""
    if not available():
        raise EchoUnavailableError("本機沒有 codex CLI 或 runner 不在")
    prompt = stages.build_review_prompt(plan_doc, contract, html, qa_info, for_echo=True)
    prompt_file = run.write_text("echo_prompt.txt", prompt)
    topic = re.sub(r"[^a-z0-9-]+", "-", f"slimecat-review-{gid or run.id}".lower()).strip("-")[:60]
    task = f"SlimeCat 獨立評審＋整合稽核《{contract.get('title', '')}》（唯讀）"

    stdout, run_dir, model = "", None, ""
    candidates = model_candidates()
    for i, model in enumerate(candidates):
        mg.log(f"🧑‍⚖️ 委派 Echo 評審（model={model}, effort={ECHO_EFFORT}，上限 {ECHO_TIMEOUT // 60} 分鐘）…")
        rc, stdout, run_dir = _delegate(model, topic, task, run.dir, prompt_file)
        if rc == 0:
            break
        if run_dir and _model_rejected(run_dir) and i + 1 < len(candidates):
            mg.log(f"  ↪️ 這台 codex CLI 跑不了 {model}（要升級 CLI），改試 {candidates[i + 1]}｜記錄 {run_dir.name}")
            continue
        raise EchoUnavailableError(f"Echo runner 失敗（exit {rc}）：{stdout[-300:]}"
                                   + (f"｜記錄 {run_dir}" if run_dir else ""))
    if not run_dir:
        raise EchoUnavailableError("runner 輸出裡找不到 Run path，無法定位委派記錄")
    crit = _extract_review(run_dir)
    if crit is None:
        raise EchoUnavailableError(f"Echo 回覆裡撈不到 REVIEW JSON（記錄 {run_dir}）")
    try:
        rev = stages.normalize_review(crit)
    except ValueError as e:
        raise EchoUnavailableError(f"Echo 的評分格式不合（{e}；記錄 {run_dir}）")
    rev["reviewer"] = f"echo:{model}"
    rev["echo_run"] = str(run_dir)
    # actual model 由 runner 從事件流抓（抓不到＝未確認），收據在 RESULT.md
    try:
        rm = re.search(r"Actual model\s*:\s*(.+)", stdout or "")
        rev["echo_actual_model"] = rm.group(1).strip() if rm else "未確認"
    except Exception:
        rev["echo_actual_model"] = "未確認"
    mg.log(f"  🧑‍⚖️ Echo 評審 {rev['total']}/50（稽核：合約 {len(rev['audit']['contract_issues'])} 條、"
           f"bug {len(rev['audit']['bugs'])} 條）｜記錄 {run_dir.name}")
    return rev
