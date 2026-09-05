# -*- coding: utf-8 -*-
"""v3 品管：既有的煙霧測試（validate_game.validate）＋延長的「壓力測試」。

煙霧測試只看開場 3 秒；v3 遊戲有關卡／波次／升級，很多錯誤要玩到第 2 波才炸。
壓力測試：真的按 SC_HOOKS.start() 開始遊戲，然後亂點亂拖亂按十幾秒，
順便確認 SC_CONTENT 真的載進來了（組裝沒把內容包接上就會在這裡被抓到）。

引擎合約（見 stages.ENGINE_CONTRACT）要求暴露：
  window.SC_HOOKS = { start(), snapshot() }   沒有也不算失敗（只記 warning），但有的話品管更準。
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # factory/
sys.path.insert(0, str(HERE))
from validate_game import validate   # noqa: E402

STRESS_SECS = 12          # 壓力測試亂玩幾秒
KEYS = ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Space", "Enter")


def stress(html_path: Path, secs: int = STRESS_SECS, seed: int = 7) -> tuple:
    """亂玩 secs 秒。回 (錯誤清單, 資訊 dict)。錯誤清單空＝通過。"""
    from playwright.sync_api import sync_playwright

    rng = random.Random(seed)
    html_path = Path(html_path).resolve()
    errors, info = [], {"hooks": False, "content": None, "snapshot": None, "warnings": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 480, "height": 800})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console",
                lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
        page.goto(html_path.as_uri())
        page.wait_for_timeout(1200)

        # 內容包有沒有真的載進來（v3 組裝的核心檢查）
        try:
            info["content"] = page.evaluate(
                "() => window.SC_CONTENT ? Object.fromEntries(Object.entries(window.SC_CONTENT)"
                ".map(([k,v]) => [k, Array.isArray(v) ? v.length : 1])) : null")
        except Exception as e:
            info["warnings"].append(f"讀 SC_CONTENT 失敗：{e}")
        if info["content"] is None:
            errors.append("window.SC_CONTENT 不存在（內容包沒接上引擎）")

        # 開始遊戲：有 hooks 就直接呼叫，沒有就點畫面中央
        try:
            info["hooks"] = bool(page.evaluate(
                "() => !!(window.SC_HOOKS && typeof window.SC_HOOKS.start === 'function')"))
        except Exception:
            info["hooks"] = False
        try:
            if info["hooks"]:
                page.evaluate("() => window.SC_HOOKS.start()")
            else:
                info["warnings"].append("引擎沒暴露 SC_HOOKS.start（改用點畫面開始）")
            page.mouse.click(240, 400)
        except Exception as e:
            errors.append(f"開始遊戲失敗: {e}")

        # 亂玩：點／拖／按鍵混著來，每 150～400ms 一個動作
        deadline = secs * 1000
        elapsed = 0
        try:
            while elapsed < deadline:
                act = rng.random()
                if act < 0.45:
                    page.mouse.click(rng.randint(20, 460), rng.randint(60, 780))
                elif act < 0.75:
                    x0, y0 = rng.randint(40, 440), rng.randint(100, 700)
                    page.mouse.move(x0, y0)
                    page.mouse.down()
                    page.mouse.move(x0 + rng.randint(-150, 150), y0 + rng.randint(-150, 150), steps=5)
                    page.mouse.up()
                else:
                    page.keyboard.press(rng.choice(KEYS))
                wait = rng.randint(150, 400)
                page.wait_for_timeout(wait)
                elapsed += wait
        except Exception as e:
            errors.append(f"壓力測試互動失敗: {e}")

        # 收尾快照（純資料，給評審／備註參考）
        if info["hooks"]:
            try:
                snap = page.evaluate(
                    "() => { try { const s = window.SC_HOOKS.snapshot ? window.SC_HOOKS.snapshot() : null;"
                    " return JSON.parse(JSON.stringify(s)); } catch (e) { return {error: String(e)}; } }")
                info["snapshot"] = snap
            except Exception as e:
                info["warnings"].append(f"snapshot 失敗：{e}")
        browser.close()

    # 去重＋截短（同一個錯誤每 frame 噴一次會有幾百行）
    seen, uniq = set(), []
    for e in errors:
        key = e[:160]
        if key not in seen:
            seen.add(key)
            uniq.append(e[:300])
    return uniq[:10], info


def run_qa(html_path: Path, gid: str, stress_secs: int = STRESS_SECS) -> tuple:
    """完整品管：煙霧（含截圖）→ 壓力。回 (通過?, 錯誤清單, 資訊)。"""
    try:
        ok, errs = validate(html_path, shot_name=gid)
    except Exception as e:
        return False, [f"playwright 掛了：{e}"], {"smoke": False}
    info = {"smoke": ok}
    if not ok:
        return False, errs, info
    try:
        errs2, info2 = stress(html_path, stress_secs)
    except Exception as e:
        return False, [f"壓力測試掛了：{e}"], info
    info.update(info2)
    return (not errs2), errs2, info


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m v3.qa <遊戲html路徑> [截圖名]")
        sys.exit(2)
    ok, errs, info = run_qa(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "manual")
    print("✅ 品管通過" if ok else "❌ 品管失敗")
    for e in errs:
        print("  -", e)
    print(json.dumps(info, ensure_ascii=False, indent=1)[:1500])
    sys.exit(0 if ok else 1)
