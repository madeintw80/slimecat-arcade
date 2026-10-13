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
from urllib.parse import unquote, urlparse

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SHOTS_DIR = HERE / "shots"
SITE_ROOT = HERE.parent   # 專案根目錄＝公開站根目錄（index.html、games/、vendor/…）

# 2026-10-13 3D 遊戲上線：Chrome 不准 file:// 載入 JS 模組，站內的 three.js（vendor/）會載不到，
# 所以品管改用「虛擬網址」開遊戲：Playwright 攔下請求、直接回本機檔案，不用真的開伺服器。
# 主機名一定要是 localhost：stats.js 看到 localhost 就不回報，品管亂玩才不會灌進真實數據。
QA_ORIGIN = "http://localhost:47977"
QA_FALLBACK_PATH = "/games/_qa/index.html"   # 遊戲檔不在站內（測試暫存檔）時掛的位置


def open_game(page, html_path) -> None:
    """用虛擬網址打開遊戲。站內的遊戲照真實相對位置掛（../../vendor 才對得上）；
    同站其他檔案從專案根目錄回；任何對外請求一律擋掉（規格本來就是零外部資源）。"""
    html_path = Path(html_path).resolve()
    try:
        game_url_path = "/" + html_path.relative_to(SITE_ROOT).as_posix()
    except ValueError:
        game_url_path = QA_FALLBACK_PATH
    html_bytes = html_path.read_bytes()

    def handle(route):
        url = urlparse(route.request.url)
        if f"{url.scheme}://{url.netloc}" != QA_ORIGIN:
            route.abort()   # 對外請求（CDN、數據回報…）
            return
        path = unquote(url.path)
        if path == game_url_path:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html_bytes)
            return
        local = (SITE_ROOT / path.lstrip("/")).resolve()
        if local.is_file() and local.is_relative_to(SITE_ROOT):
            route.fulfill(status=200, path=str(local))
        else:
            route.fulfill(status=404, body="not found")

    page.route("**/*", handle)
    page.goto(QA_ORIGIN + game_url_path)


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
        open_game(page, html_path)
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
