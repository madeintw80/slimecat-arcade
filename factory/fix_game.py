# -*- coding: utf-8 -*-
"""AI 修復已上架遊戲 —— 維護迴圈的第二步（回報 → 修復 → 驗證 → 上線）。

用法：
    python fix_game.py <遊戲名或id>       # 修這款的全部 open bugs
    python fix_game.py <遊戲名或id> --spawn  # 背景開工立刻返回（給 Telegram listen 用）
    python fix_game.py --all              # 修所有有 open bug 的上架遊戲（週日檢討自動呼叫）

流程：
  1. 讀遊戲完整原始碼 + open bugs
  2. claude -p 修復（最小侵入合約：只修 bug、不動玩法/美術/計分）
  3. Playwright 煙霧測試（不過就帶錯誤重試一次；再不過 → 保留原版、bug 維持 open）
  4. 通過 → 覆寫檔案 + bugs 標 fixed + learnings 記教訓 + 重建大廳 + 部署 + Telegram 通知
"""
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GAMES_DIR = ROOT / "games"
GAMES_JSON = ROOT / "games.json"
LEARN_FILE = HERE / "knowledge" / "learnings.md"

sys.path.insert(0, str(HERE))
import rebuild                                          # noqa: E402
from make_game import run_claude, log, GEN_TIMEOUT, SMALL_TIMEOUT, MODEL_CRITIC  # noqa: E402
from validate_game import validate                      # noqa: E402

sys.path.insert(0, "C:/Users/User/projects/_common")
try:
    import batnini_telegram as tg
except Exception:
    tg = None

MAX_ATTEMPTS = 2  # 修復 + 驗證最多試幾次


def spawn_detached(argv_rest: list) -> None:
    """背景開工立刻返回（Telegram listen 的 Bash 有 10 分鐘上限，修復要 10~20 分鐘）。"""
    args = [sys.executable, str(Path(__file__).resolve())] + argv_rest
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    logf = (HERE / "factory.log").open("a", encoding="utf-8")
    subprocess.Popen(args, creationflags=flags, stdout=logf, stderr=subprocess.STDOUT)
    print("🔧 修復已在背景開工（約 10~20 分鐘），完成會推 Telegram 通知")
    print("   進度看 factory/factory.log")


def player_summary(g: dict, bugs: list) -> str:
    """用 haiku 把技術性的 bug 修正，改寫成一句玩家看得懂的白話更新說明。
    給大廳「📢 更新日誌」顯示用。失敗就退回 bug 原文，絕不擋部署。"""
    # 留言型 bug 格式是「原始問題 ➜ 給工程師的修復指令」，fallback 只取前半原始問題
    fallback = bugs[0]["note"].split("➜")[0].replace("[玩家留言]", "").strip()[:40]
    notes = "\n".join(f"- {b['note']}" for b in bugs)
    prompt = (
        f"你是遊戲工作室的小編。以下是《{g['title']}》這次修好的問題（技術描述）。\n"
        "請寫一句給「玩家」看的更新說明，講「這次改善了什麼」。要求：\n"
        "- 繁體中文、口語、25 字以內、只有一句話\n"
        "- 玩家視角（玩家不懂程式），只講他們玩得到的改變\n"
        "- 不要技術名詞、不要開場白、不要引號，直接給那一句話\n\n"
        f"這次修好的問題：\n{notes}"
    )
    try:
        out = run_claude(prompt, SMALL_TIMEOUT, model=MODEL_CRITIC)
        line = next((ln.strip() for ln in out.splitlines() if ln.strip()), "")
        line = line.strip("「」\"'。 ").strip()   # 去掉多餘引號/句號
        return line[:40] or fallback
    except Exception as e:
        log(f"⚠️ 產玩家更新說明失敗，改用問題描述：{e}")
        return fallback


def build_prompt(g: dict, html: str, bugs: list, feedback: str = "") -> str:
    bug_lines = "\n".join(f"- {b['date']}：{b['note']}" for b in bugs)
    fb = (f"\n⚠️ 上一次修復沒通過品管，錯誤如下，請避免同類問題：\n{feedback}\n"
          if feedback else "")
    return f"""你是「SlimeCat 遊戲工作室」的資深遊戲開發者，任務是 **bug 修復**（不是重寫）。
以下是已上架遊戲《{g['title']}》的完整原始碼，以及玩家回報的 bug。

═══ 玩家回報的 bug（全部要修好）═══
{bug_lines}

═══ 完整原始碼 ═══
{html}
{fb}
硬性要求（違反任何一條就算失敗）：
- 最小侵入：只改跟 bug 相關的程式碼；玩法、美術、計分、難度、文案一律不可動
- 第一行的 GAMEMETA 註解原樣保留
- 檔尾的 sc_config.js / stats.js 兩個 script 標籤原樣保留
- 拖曳/點擊類 bug 的常見根因是「視覺位置」與「判定位置」基準不一致——修復時讓兩者共用同一個計算函式，不要各寫一份公式
- 手機觸控與電腦滑鼠都要驗證過你的修法（在腦中實際走一遍事件流）
- 不可用 alert/confirm/prompt；不可出現 console.error 或未捕捉例外

🔴 交付方式：你唯一的交付物是「印出的文字」。不要使用任何工具、不要建立或修改任何檔案
（你也沒有寫檔權限），把修復後的完整檔案當純文字印出來就是交稿。
輸出格式：不要 markdown code fence、不要任何解說文字，
第一行是原本的 GAMEMETA 註解，接著就是修復後的完整網頁內容。
"""


def extract_fixed(output: str, orig_len: int) -> str:
    """驗收修復輸出：要有 GAMEMETA、canvas、stats 標籤，且不能是殘缺片段。"""
    i = output.find("<!--GAMEMETA")
    if i < 0:
        raise ValueError("輸出裡找不到 GAMEMETA 標頭")
    html = output[i:].strip()
    import re
    html = re.sub(r"\n```\s*$", "", html)
    if "<canvas" not in html.lower():
        raise ValueError("修復後的 HTML 裡沒有 canvas")
    if "stats.js" not in html:
        raise ValueError("修復後的 HTML 少了 stats.js 標籤（數據回報會斷）")
    if len(html) < orig_len * 0.6:
        raise ValueError(f"修復輸出只有原檔 {len(html)*100//orig_len}% 長度，疑似殘缺")
    return html


def notify_result(g: dict, bugs: list, ok: bool, reason: str = "") -> None:
    if not (tg and tg.available()):
        return
    notes = "\n".join(f"• {b['note'][:60]}" for b in bugs)
    if ok:
        text = (f"🔧✅ 《{g['title']}》bug 修復完成、已重新上線！\n"
                f"修了：\n{notes}\n\n"
                f"再玩玩看，還有問題就再「遊戲回報 {g['title']} <描述>」")
    else:
        text = (f"🔧❌ 《{g['title']}》這次修復失敗（已重試）。\n"
                f"原因：{reason[:200]}\n"
                f"bug 保持待修，週日檢討會再自動試一次；詳見 factory/factory.log")
    shot = GAMES_DIR / g["id"] / "shot.png"
    try:
        if ok and shot.exists():
            tg.push_photo(shot, caption=text)
        else:
            tg.send(text)
    except Exception as e:
        log(f"⚠️ Telegram 推播失敗：{e}")


def fix_one(g: dict, data: dict) -> bool:
    """修一款遊戲的全部 open bugs。成功回 True（並已寫檔/標記/部署）。"""
    bugs = [b for b in g.get("bugs", []) if b.get("status") == "open"]
    if not bugs:
        log(f"《{g['title']}》沒有待修 bug，跳過")
        return True

    path = GAMES_DIR / g["id"] / "index.html"
    if not path.exists():
        log(f"❌ 找不到 {path}")
        return False
    html = path.read_text(encoding="utf-8")
    log(f"🔧 修復《{g['title']}》（{len(bugs)} 條 bug，最多等 {GEN_TIMEOUT//60} 分鐘）…")

    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"  第 {attempt}/{MAX_ATTEMPTS} 次修復…")
        try:
            out = run_claude(build_prompt(g, html, bugs, feedback), GEN_TIMEOUT)
            fixed = extract_fixed(out, len(html))
        except Exception as e:
            log(f"  ❌ 修復輸出不合格：{e}")
            feedback = str(e)
            continue

        # 先寫進暫存檔跑品管，通過才覆寫正式檔
        tmp = path.with_suffix(".fixing.html")
        tmp.write_text(fixed, encoding="utf-8")
        ok, errs = validate(tmp, shot_name=g["id"])
        if not ok:
            log(f"  ❌ 煙霧測試失敗：{errs}")
            feedback = "\n".join(errs)[:800]
            tmp.unlink(missing_ok=True)
            continue

        # 通過：覆寫正式檔（舊版還在 git 歷史，要回滾隨時可以）
        tmp.replace(path)
        shot_src = HERE / "shots" / f"{g['id']}.png"
        if shot_src.exists():
            shutil.copy(shot_src, GAMES_DIR / g["id"] / "shot.png")

        today = datetime.date.today().isoformat()
        for b in bugs:
            b["status"] = "fixed"
            b["fixed_at"] = today
        # 更新日誌：記最近更新日（大廳「🔧 剛更新」徽章用）＋一句玩家白話（更新日誌用）
        g["updated_at"] = today
        g.setdefault("changelog", []).append(
            {"date": today, "summary": player_summary(g, bugs)})
        # 🔴 read-then-update（last-writer-wins bug）：不寫開場讀進來的整份 data，
        # 改重讀最新 games.json、只把「這一款」的 bug/更新日誌 merge 回去，
        # 避免抹掉並行程序（例 12:00 生產）這段期間剛上架的新遊戲。
        fresh = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
        fidx = {x["id"]: x for x in fresh.get("games", []) + fresh.get("retired", [])}
        ftgt = fidx.get(g["id"])
        if ftgt is not None:                       # 本流程是這款唯一的寫入者，可整組覆蓋這三欄
            ftgt["bugs"] = g.get("bugs", [])
            ftgt["updated_at"] = g["updated_at"]
            ftgt["changelog"] = g.get("changelog", [])
        GAMES_JSON.write_text(json.dumps(fresh, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        rebuild.rebuild()
        with LEARN_FILE.open("a", encoding="utf-8") as f:
            for b in bugs:
                f.write(f"- {today} 修復《{g['title']}》：{b['note'][:80]}（AI 修復+品管通過）\n")

        log(f"✅ 《{g['title']}》修復完成")
        notify_result(g, bugs, ok=True)
        try:
            import publish_site
            publish_site.publish(f"🔧 修復《{g['title']}》：{bugs[0]['note'][:40]}")
        except Exception as e:
            log(f"⚠️ 自動部署失敗（本機已修好）：{e}")
        return True

    log(f"❌ 《{g['title']}》重試後仍失敗，保留原版")
    notify_result(g, bugs, ok=False, reason=feedback)
    return False


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--spawn"]
    if "--spawn" in sys.argv:
        if not argv:
            print("用法: python fix_game.py <遊戲名或id> --spawn")
            return 2
        spawn_detached(argv)
        return 0

    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))

    if argv and argv[0] == "--all":
        targets = [g for g in data.get("games", [])
                   if any(b.get("status") == "open" for b in g.get("bugs", []))]
        if not targets:
            log("沒有任何待修 bug ✅")
            return 0
        log(f"🔧 待修遊戲 {len(targets)} 款：" + "、".join(g["title"] for g in targets))
        results = [fix_one(g, data) for g in targets]
        return 0 if all(results) else 1

    if not argv:
        print("用法: python fix_game.py <遊戲名或id> [--spawn] | --all")
        return 2

    query = argv[0].strip()
    pool = data.get("games", []) + data.get("retired", [])
    hits = [g for g in pool if query in g["title"] or query in g["id"]]
    if not hits:
        print(f"❌ 找不到遊戲「{query}」")
        return 1
    if len(hits) > 1:
        print(f"⚠️ 「{query}」對到多款，請講更完整的名字：")
        for g in hits:
            print(f"   - {g['title']}（{g['id']}）")
        return 1
    return 0 if fix_one(hits[0], data) else 1


if __name__ == "__main__":
    sys.exit(main())
