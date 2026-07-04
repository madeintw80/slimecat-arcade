# -*- coding: utf-8 -*-
"""遊戲上架前的煙霧測試：用 Playwright 無頭瀏覽器真的打開遊戲跑一遍。

檢查三件事：
  1. 頁面載入沒有 JS 例外（pageerror）、沒有 console.error
  2. 頁面上真的有 <canvas>（遊戲畫面存在）
  3. 模擬「點一下開始 + 按方向鍵」之後也沒噴錯
順便存一張截圖到 factory/shots/，之後推播、快速檢視都用得到。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SHOTS_DIR = HERE / "shots"


def validate(html_path, shot_name: str = ""):
    """回傳 (是否通過, 錯誤清單)。"""
    from playwright.sync_api import sync_playwright

    html_path = Path(html_path).resolve()
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 480, "height": 800})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console",
                lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
        page.goto(html_path.as_uri())
        page.wait_for_timeout(1500)

        if not page.query_selector("canvas"):
            errors.append("頁面上沒有 <canvas>，不像一個遊戲")

        # 模擬玩家：點畫面開始 → 按方向鍵動一動 → 再等一下看會不會炸
        try:
            page.mouse.click(240, 400)
            page.wait_for_timeout(700)
            page.keyboard.press("ArrowLeft")
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(1200)
        except Exception as e:
            errors.append(f"互動模擬失敗: {e}")

        if shot_name:
            SHOTS_DIR.mkdir(exist_ok=True)
            page.screenshot(path=str(SHOTS_DIR / f"{shot_name}.png"))
        browser.close()
    return (not errors), errors


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python validate_game.py <遊戲html路徑> [截圖名]")
        sys.exit(2)
    ok, errs = validate(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "manual")
    if ok:
        print("✅ 煙霧測試通過")
    else:
        print("❌ 煙霧測試失敗：")
        for e in errs:
            print("  -", e)
    sys.exit(0 if ok else 1)
