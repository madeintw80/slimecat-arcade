# -*- coding: utf-8 -*-
"""原創模式 —— 不看榜單，從機制原子庫抽組合生原創遊戲。

跟每日生產（make_game，臨摹模式）的差別：
  臨摹：App Store 榜單 → 挑一款解構 → 做變形版（起點是別人的遊戲）
  原創：原子庫抽「操作+規則+壓力+約束」→ 3 個候選企劃 → 用戶挑一個 → 開工
        （起點是機制組合，沒有原作——用戶當創意總監，工廠當開發團隊）

用法：
    python original_mode.py propose            # 抽 3 組合＋一句話企劃（約 1 分鐘），等用戶挑
    python original_mode.py build 2            # 把第 2 案展開成企劃書 → 走生產管線（20~40 分鐘）
    python original_mode.py build 2 --spawn    # 背景開工立刻返回（Telegram listen 用）

抽選規則：
  - 冷門原子優先（權重 = 1/(1+已用次數)^1.5，已用次數 parse 原子庫第七節對照表）
  - 避開庫裡標明的相剋組合（parse 各原子「相剋：」行裡的原子 ID）
  - 3 組彼此不重複
"""
import datetime
import json
import random
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
KNOW = HERE / "knowledge"
ATOMS_FILE = KNOW / "mechanism_atoms.md"
ORIGINALS_DIR = KNOW / "originals"
PENDING_FILE = HERE / "original_pending.json"

sys.path.insert(0, str(HERE))
import make_game  # noqa: E402  共用 run_claude / log / 生產管線
from make_game import log, run_claude, SMALL_TIMEOUT  # noqa: E402

ID_RE = re.compile(r"\b(OP\d+|RU\d+|PR\d+)\b")


# ---------------------------------------------------------------- 讀原子庫
def parse_library() -> dict:
    """把 mechanism_atoms.md 解析成 {atoms, usage, conflicts, constraints}。"""
    text = ATOMS_FILE.read_text(encoding="utf-8")

    # 原子條目：### OP1 單擊點選 ～ 下一個標題之間的全文
    atoms = {}
    for m in re.finditer(r"^### (OP\d+|RU\d+|PR\d+) (.+?)$\n(.*?)(?=^###|^## )",
                         text, re.M | re.S):
        aid, name, body = m.group(1), m.group(2).strip(), m.group(3).strip()
        atoms[aid] = {"name": name, "body": body}

    # 已用次數：第七節對照表（只算表格行，避免把「觀察」說明文字裡的 ID 也計數）
    usage = {aid: 0 for aid in atoms}
    sec7 = re.search(r"^## 七、.*?(?=^## |\Z)", text, re.M | re.S)
    if sec7:
        for line in sec7.group(0).splitlines():
            if line.lstrip().startswith("|"):
                for aid in ID_RE.findall(line):
                    if aid in usage:
                        usage[aid] += 1

    # 相剋：各原子 body 裡「相剋：」到「難度」之間點名的 ID
    conflicts = set()
    for aid, a in atoms.items():
        m = re.search(r"相剋：(.*?)(?:難度：|$)", a["body"], re.S)
        if m:
            for other in ID_RE.findall(m.group(1)):
                if other in atoms and other != aid:
                    conflicts.add(frozenset((aid, other)))

    # 約束卡：第五節的編號清單
    constraints = []
    sec5 = re.search(r"^## 五、.*?(?=^## |\Z)", text, re.M | re.S)
    if sec5:
        constraints = re.findall(r"^\d+\.\s*(.+)$", sec5.group(0), re.M)

    if not atoms or not constraints:
        raise RuntimeError("原子庫解析失敗（原子或約束卡是空的），檢查 mechanism_atoms.md 格式")
    return {"atoms": atoms, "usage": usage,
            "conflicts": conflicts, "constraints": constraints}


# ---------------------------------------------------------------- 抽組合
def weighted_pick(pool: list, usage: dict, exclude=()) -> str:
    """冷門優先的加權抽選（已用越多權重越低）。"""
    cands = [a for a in pool if a not in exclude]
    weights = [1.0 / (1 + usage.get(a, 0)) ** 1.5 for a in cands]
    return random.choices(cands, weights=weights, k=1)[0]


def draw_combo(lib: dict) -> dict:
    """抽一組：操作×1 + 規則×1~2 + 壓力×1 + 約束×1，避開相剋。"""
    ops = [a for a in lib["atoms"] if a.startswith("OP")]
    rus = [a for a in lib["atoms"] if a.startswith("RU")]
    prs = [a for a in lib["atoms"] if a.startswith("PR")]
    for _ in range(40):  # 抽到相剋就重抽
        picked = [weighted_pick(ops, lib["usage"])]
        picked.append(weighted_pick(rus, lib["usage"]))
        if random.random() < 0.5:  # 一半機率配第二個規則原子
            picked.append(weighted_pick(rus, lib["usage"], exclude=picked))
        picked.append(weighted_pick(prs, lib["usage"]))
        pairs = {frozenset((x, y)) for x in picked for y in picked if x != y}
        if not (pairs & lib["conflicts"]):
            return {"atoms": picked,
                    "constraint": random.choice(lib["constraints"])}
    raise RuntimeError("重抽 40 次都撞相剋，檢查原子庫的相剋標記是否過密")


def draw_combos(lib: dict, n: int = 3) -> list:
    """抽 n 組互不重複的組合；操作原子盡量互異（三案手感才真的不同）。"""
    combos, seen, used_ops = [], set(), set()
    for attempt in range(120):
        c = draw_combo(lib)
        key = frozenset(c["atoms"])
        op = c["atoms"][0]
        if key in seen:
            continue
        if op in used_ops and attempt < 80:  # 前 80 次堅持操作互異，之後放寬保底
            continue
        seen.add(key)
        used_ops.add(op)
        combos.append(c)
        if len(combos) == n:
            return combos
    raise RuntimeError("抽不出足夠的不重複組合")


# ---------------------------------------------------------------- propose
def cmd_propose() -> int:
    log("🧪 原創模式：抽組合中（冷門原子優先）…")
    lib = parse_library()
    combos = draw_combos(lib)

    blocks = []
    for i, c in enumerate(combos, 1):
        entries = "\n".join(f"### {aid} {lib['atoms'][aid]['name']}\n{lib['atoms'][aid]['body']}"
                            for aid in c["atoms"])
        blocks.append(f"═══ 組合 {i} ═══\n{entries}\n約束卡：{c['constraint']}")

    prompt = f"""你是「SlimeCat 遊戲工作室」的首席遊戲策劃。今天不臨摹任何現有遊戲——
下面是從機制原子庫隨機抽出的 3 個組合，替每一組發想一款「30 秒上手的網頁小遊戲」原創企劃。
（直接輸出文字、不要使用任何工具）

{chr(10).join(blocks)}

要求：
- 每組的企劃必須用滿抽到的所有原子，並遵守該組約束卡
- 主角美術是「史萊姆貓」宇宙（綠色史萊姆＋貓耳）
- 發想時自問：核心迴圈一圈幾秒？失敗歸因於誰？near-miss 長什麼樣？答不出來就換個切入點再想
- 企劃要具體到「看得見畫面」，不要抽象口號

輸出格式（嚴格遵守，每組三行）：
CONCEPT1: <30字內的一句話企劃，說清楚玩家在做什麼>
GENRE1: <類型一詞>
HOOK1: <為什麼會上癮，一句話>
CONCEPT2: ...（依此類推到 3）
"""
    out = run_claude(prompt, SMALL_TIMEOUT)

    proposals = []
    for i, c in enumerate(combos, 1):
        concept = re.search(rf"^CONCEPT{i}:\s*(.+)$", out, re.M)
        genre = re.search(rf"^GENRE{i}:\s*(.+)$", out, re.M)
        hook = re.search(rf"^HOOK{i}:\s*(.+)$", out, re.M)
        if not concept:
            raise RuntimeError(f"策劃輸出缺 CONCEPT{i}，重跑一次 propose")
        proposals.append({
            "atoms": c["atoms"],
            "names": [lib["atoms"][a]["name"] for a in c["atoms"]],
            "constraint": c["constraint"],
            "concept": concept.group(1).strip(),
            "genre": (genre.group(1).strip() if genre else "小遊戲"),
            "hook": (hook.group(1).strip() if hook else ""),
        })

    PENDING_FILE.write_text(json.dumps(
        {"created": datetime.datetime.now().isoformat(timespec="seconds"),
         "proposals": proposals}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["🧪 原創模式 — 3 個候選組合（冷門原子優先）", "─" * 14]
    for i, p in enumerate(proposals, 1):
        lines.append(f"【{i}】{' × '.join(p['names'])}")
        lines.append(f"    約束：{p['constraint']}")
        lines.append(f"    企劃：{p['concept']}")
        if p["hook"]:
            lines.append(f"    亮點：{p['hook']}")
        lines.append("")
    lines += ["─" * 14,
              "回「原創 1」/「原創 2」/「原創 3」開工（約 20~40 分鐘，出爐自動推通知）",
              "都不喜歡 → 再打「生原創遊戲」重抽"]
    print("\n".join(lines))
    return 0


# ---------------------------------------------------------------- build
def cmd_build(idx: int) -> int:
    if not PENDING_FILE.exists():
        print("❌ 沒有待選的原創提案，先打「生原創遊戲」抽組合")
        return 1
    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    props = pending["proposals"]
    if not (1 <= idx <= len(props)):
        print(f"❌ 只有 {len(props)} 個提案，請回 1~{len(props)}")
        return 1
    p = props[idx - 1]
    log(f"🧪 原創開工：{p['concept']}（{' × '.join(p['names'])}）")

    lib = parse_library()
    entries = "\n".join(f"### {aid} {lib['atoms'][aid]['name']}\n{lib['atoms'][aid]['body']}"
                        for aid in p["atoms"] if aid in lib["atoms"])
    prompt = f"""你是「SlimeCat 遊戲工作室」的首席遊戲策劃。用戶已從候選中選定這個原創企劃，
請把它展開成可直接實作的完整企劃書。（直接輸出文字、不要使用任何工具）

一句話企劃：{p['concept']}
上癮亮點：{p['hook']}
約束卡（硬性遵守）：{p['constraint']}

═══ 選用的機制原子（完整條目）═══
{entries}

輸出格式（嚴格遵守，前三行標頭，之後是企劃書本體）：
TITLE: <遊戲中文名建議（史萊姆貓宇宙、全新命名）>
GENRE: {p['genre']}
SOURCE: 原創組合：{'×'.join(p['names'])}

# 原創企劃：{p['concept']}
## 核心迴圈（一圈幾秒？操作→回饋→獎勵怎麼轉？具體描述玩家的手和眼在做什麼）
## 上癮機制（near-miss/歸因於己/變動獎勵…逐一寫「在這款怎麼掛」，要具體可實作）
## 玩法規格（盤面尺寸/物件/生成規則/判定/難度曲線/計分，具體到工程師能直接照做）
## 風險與捨棄（這個組合最容易不好玩的點是什麼？怎麼避？哪些誘人但要忍住不做？）
## 我們的變形版一句話企劃（原創模式：此節就是最終企劃，含核心樂趣一句話）
"""
    out = run_claude(prompt, SMALL_TIMEOUT)
    ttl = re.search(r"^TITLE:\s*(.+)$", out, re.M)
    doc_start = out.find("# 原創企劃")
    doc = out[doc_start:] if doc_start >= 0 else out
    decon = {
        "source": f"原創組合：{'×'.join(p['names'])}",
        "title": (ttl.group(1).strip() if ttl else ""),
        "genre": p["genre"],
        "doc": doc.strip(),
    }

    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    plan_file = ORIGINALS_DIR / f"{today}-{'_'.join(p['atoms'])}.md"
    plan_file.write_text(decon["doc"], encoding="utf-8")
    log(f"📖 原創企劃書完成 → {plan_file.name}")

    rc = make_game.produce_from_decon(decon)
    if rc == 0:
        PENDING_FILE.unlink(missing_ok=True)  # 開工成功才清掉，失敗可重試
    return rc


# ---------------------------------------------------------------- 入口
def spawn_detached(argv_rest: list) -> None:
    """背景開工立刻返回（Telegram listen 的 Bash 有時限，build 要 20~40 分鐘）。"""
    args = [sys.executable, str(Path(__file__).resolve())] + argv_rest
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    logf = (HERE / "factory.log").open("a", encoding="utf-8")
    subprocess.Popen(args, creationflags=flags, stdout=logf, stderr=subprocess.STDOUT)
    print("🧪 原創遊戲已在背景開工（約 20~40 分鐘）！")
    print("   流程：企劃書 → 實作 → Playwright 品管 → 自評 → 上架，出爐自動推 Telegram。")
    print("   進度看 factory/factory.log")


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--spawn"]
    if not argv or argv[0] not in ("propose", "build"):
        print("用法: python original_mode.py propose | build <1~3> [--spawn]")
        return 2
    if argv[0] == "propose":
        return cmd_propose()
    if len(argv) < 2 or not argv[1].isdigit():
        print("用法: python original_mode.py build <1~3> [--spawn]")
        return 2
    if "--spawn" in sys.argv:
        spawn_detached(["build", argv[1]])
        return 0
    return cmd_build(int(argv[1]))


if __name__ == "__main__":
    sys.exit(main())
