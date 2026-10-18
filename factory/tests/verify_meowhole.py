# -*- coding: utf-8 -*-
"""《喵窟擋十波》（2026-10-17-001）Echo 評審剩下四項的驗證腳本（2026-10-18 任務單）。

用法：python factory/tests/verify_meowhole.py [遊戲 html 路徑，預設 games/2026-10-17-001/index.html]

遊戲程式包在 IIFE 裡、外面拿不到內部函式，所以本腳本在「送給瀏覽器的那份 HTML」裡
臨時注入一個 window.__T 掛鉤（只改記憶體裡的內容，不動 repo 的檔案），再用 60Hz 固定步長
在一次 evaluate 裡同步模擬整局（瀏覽器自己的 rAF 迴圈插不進來，結果可重現）。

驗四項：
  (a) 第 10 波清完之前不會進無限波（王慢慢走＋提早開波鈕都試）；提早清完第 10 波時會很快接第 11 波
  (b) shuttle_moth／split_thread／loose_thread 都排進第 1～10 波的 waves.groups，而且真的有生成
  (c) 任意 12 秒窗口至少有一個買得起的操作（放塔／升級／提早開波／免費拍擊）——用最刁鑽的玩法量最長空窗
  (d) 標題頁只畫一句規則（攔截 fillText 收集標題頁實際畫出的字）
另外：照開局提示操作（點彈珠喵卡 → 點閃爍格）第一個動作就成功；機器人正常玩四張圖看難度沒崩。
"""
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "http://localhost:47977"
GAME_PATH = "/games/2026-10-17-001/index.html"

# 注入在 load() 之前：把內部函式掛到 window.__T（typeof 防呆＝舊版沒有的函式就給 null）
HOOK = """window.__T={get R(){return R},get G(){return G},get scene(){return scene},set scene(v){scene=v},
  get sceneT(){return sceneT},set sceneT(v){sceneT=v},
  update,startRun,place,upgrade,callEarly,canEarly,onDown,onUp,cardRect,canBuild,cellXY,drawTitle,STEP,
  pawReady:typeof pawReady==='function'?pawReady:null,usePaw:typeof usePaw==='function'?usePaw:null,
  PAW_BOX:typeof PAW_BOX!=='undefined'?PAW_BOX:null};
"""

SIM_JS = r"""
(cfg) => {
  const T = window.__T, G = T.G;
  const out = {};
  const ids = ['marble_cat','marble_cat','marble_cat','popcorn_cat','whisker_cat','longshot_cat','popcorn_cat',
               'mist_cat','whisker_cat','longshot_cat','popcorn_cat','longshot_cat','whisker_cat','popcorn_cat'];
  const tIdx = id => G.towers.findIndex(t => t.id === id);
  // 所有可蓋格
  const cells = () => { const a = []; for (let r = 0; r < 11; r++) for (let c = 0; c < 10; c++) if (T.canBuild(c, r)) a.push({c, r}); return a; };
  // 「現在有沒有買得起的操作」：放塔／升級／提早開波／免費拍擊（拍擊要場上有怪才算數）。賣塔不算。
  const opAvail = () => {
    const R = T.R;
    const placeOk = G.towers.some(t => R.wave >= t.unlockWave && t.cost <= R.fish) && cells().length > 0;
    const upOk = R.wave >= 2 && R.towers.some(t => t.lv < t.T.levels.length - 1 && t.T.upgradeCost[t.lv] <= R.fish);
    const pawOk = !!(T.pawReady && T.pawReady() && R.enemies.some(e => !e.dead));
    return placeOk || upOk || T.canEarly() || pawOk;
  };
  // 路徑覆蓋分數：range 內有幾個路徑取樣點（只算已開的路）
  const cover = (c, r, range) => {
    const R = T.R, p0 = T.cellXY(c, r); let n = 0;
    R.mp.paths.forEach(p => { if (p.from > Math.max(1, R.wave + 1)) return;
      for (let i = 1; i < p.pts.length; i++) { const a = p.pts[i-1], b = p.pts[i], L = Math.hypot(b.x-a.x, b.y-a.y);
        for (let d = 0; d < L; d += 10) { const x = a.x + (b.x-a.x)*d/L, y = a.y + (b.y-a.y)*d/L;
          if ((x-p0.x)**2 + (y-p0.y)**2 <= range*range) n++; } } });
    return n;
  };
  const botStep = (t, st) => {
    const R = T.R;
    if (T.pawReady && T.pawReady() && R.enemies.some(e => !e.dead)) T.usePaw();
    // 依計畫放塔
    let k = st.k; while (k < ids.length && R.wave < G.towers[tIdx(ids[k])].unlockWave) k++;
    if (k < ids.length) { const ti = tIdx(ids[k]), Tw = G.towers[ti];
      if (R.fish >= Tw.cost) { let best = null, bs = -1; cells().forEach(q => { const s = cover(q.c, q.r, Tw.levels[0].range); if (s > bs) { bs = s; best = q; } });
        if (best && T.place(ti, best.c, best.r)) { if (k === st.k) st.k++; else ids.splice(k, 1); return; } }
      if (R.towers.length < 4) return; }
    // 升級最便宜的
    if (R.wave >= 2) { let bt = null; R.towers.forEach(t => { if (t.lv < t.T.levels.length - 1 && (!bt || t.T.upgradeCost[t.lv] < bt.T.upgradeCost[bt.lv])) bt = t; });
      if (bt && R.fish >= bt.T.upgradeCost[bt.lv] + (k < ids.length ? 0 : 0)) T.upgrade(bt); }
  };

  // 一局模擬。policy(t, st) 每 0.5 秒呼叫一次；回傳統計
  const run = (mi, policy, opts) => {
    opts = opts || {};
    T.startRun(mi); const R = T.R;
    if (opts.lives) R.lives = opts.lives;
    const st = {k: 0}, waveLog = [], spawnByWave = {};
    let lastOk = 0, maxGap = 0, gapAt = null, victoryAt = null, t11 = null, victoryAt11 = null, earlyTried = [];
    let nextPolicy = 0;
    const steps = Math.round((opts.maxT || 700) / T.STEP);
    for (let i = 0; i < steps; i++) {
      if (R.t >= nextPolicy) { nextPolicy += 0.5; policy && policy(R.t, st, R); }
      const w0 = R.wave, n0 = R.enemies.length;
      if (opts.tryEarlyAt10 && R.wave === G.fixedN && !R.victory && R.queue.length === 0 && R.enemies.some(e => !e.dead)) {
        const before = R.wave; T.callEarly(); earlyTried.push({t: +R.t.toFixed(1), waveBefore: before, waveAfter: R.wave}); opts.tryEarlyAt10 = false; }
      T.update(T.STEP);
      if (T.scene !== 'play') break;
      R.enemies.forEach(e => { if (!e._seen) { e._seen = 1; (spawnByWave[e.wn] = spawnByWave[e.wn] || {}); spawnByWave[e.wn][e.def.id] = (spawnByWave[e.wn][e.def.id] || 0) + 1; } });
      if (R.wave !== w0) waveLog.push({n: R.wave, t: +R.t.toFixed(2), victory: R.victory});
      if (R.victory && victoryAt === null) victoryAt = +R.t.toFixed(2);
      if (R.wave === G.fixedN + 1 && t11 === null) { t11 = +R.t.toFixed(2); victoryAt11 = R.victory; if (opts.stopAt11) break; }
      if (opts.killAllAt10 && R.wave === G.fixedN && R.queue.length === 0 && !R.victory) R.enemies.forEach(e => { if (!e.dead) e.d = 1e9; });   // 全部瞬間走到底（命 999）＝第 10 波立刻清完
      if (opAvail()) lastOk = R.t; else if (R.t - lastOk > maxGap) { maxGap = R.t - lastOk; gapAt = +lastOk.toFixed(1); }
    }
    return {map: G.maps[mi].id, endT: +R.t.toFixed(1), scene: T.scene, wave: R.wave, victory: R.victory, lives: R.lives, fish: R.fish,
            score: R.score, stars: R.starsGot, towers: R.towers.length, victoryAt, t11, victoryAt11, earlyTried,
            maxNoOpGap: +maxGap.toFixed(2), gapStartsAt: gapAt, spawnByWave, waves: waveLog.map(w => w.n + '@' + w.t).join(' ')};
  };

  // (a)-1 不放塔、命設 999：王走完整條路才清完第 10 波；第 11 波必須在通關之後才開
  out.a_hold = run(0, null, {lives: 999, stopAt11: true, tryEarlyAt10: true});
  // (a)-2 第 10 波出完怪就立刻清場：通關後應該很快接第 11 波（不等原本的倒數）
  out.a_fastClear = run(0, null, {lives: 999, stopAt11: true, killAllAt10: true});
  // (b) 第 1～10 波 waves.groups 的怪種
  out.b_groups = G.fixed.map(w => w.index + ':' + w.groups.map(g => g.enemy + 'x' + g.count).join(','));
  out.b_templ = G.templ.map(w => w.index + ':' + w.groups.map(g => g.enemy).join(','));
  // (c) 刁鑽玩法量最長空窗
  out.c_echo = run(0, (t, st, R) => { if (!st.done) { st.done = 1; T.place(0, 9, 2); T.place(0, 9, 3); } }, {maxT: 420});
  out.c_greedy = run(0, (t, st, R) => {   // 一有錢就蓋沒用的塔（永遠窮）
    const spots = [[9,2],[9,3],[9,5],[9,6],[0,8],[0,9],[1,9],[2,9],[3,9],[4,9],[5,9],[6,9],[7,9],[9,9],[0,0],[1,0],[2,0],[3,0],[4,0],[5,0],[6,0],[7,0],[8,0]];
    for (const [c, r] of spots) if (R.fish >= 40 && T.canBuild(c, r)) T.place(0, c, r); }, {maxT: 420});
  out.c_upgradeSink = run(0, (t, st, R) => {   // 一座沒用的塔、錢全拿去升級它
    if (!st.done) { st.done = 1; T.place(0, 9, 2); } const tw = R.towers[0]; if (tw) T.upgrade(tw); }, {maxT: 420});
  // 機器人正常玩四張圖
  out.bot = G.maps.map((m, mi) => { const r = run(mi, botStep, {maxT: 600, stopAt11: true}); delete r.spawnByWave; return r; });
  out.botMaxGap = Math.max(...out.bot.map(b => b.maxNoOpGap));
  // 照開局提示：點第一張卡（彈珠喵）→ 點閃爍格，第一座塔要蓋成功
  T.startRun(0); { const R = T.R, b = T.cardRect(0), s = R.suggest, p = T.cellXY(s.c, s.r), ev = {pointerType: 'touch'};
    T.onDown({x: b[0] + b[2]/2, y: b[1] + b[3]/2}); T.onDown({x: p.x, y: p.y}); T.onUp({x: p.x, y: p.y}, ev);
    out.firstAction = {selAfterCardTap: R.sel, towers: R.towers.length, fish: R.fish}; }
  // (d) 標題頁實際畫出的字（第一次玩、回訪兩種）
  const grab = () => { const got = []; const ctx = document.getElementById('cv').getContext('2d'), orig = ctx.fillText;
    ctx.fillText = function (s) { got.push(String(s)); return orig.apply(this, arguments); };
    T.scene = 'title'; T.sceneT = 0; try { T.drawTitle(); } finally { ctx.fillText = orig; } return got; };
  out.d_titleFresh = grab();
  return out;
}
"""


def open_with_hook(page, html_path: Path):
    html = html_path.read_text(encoding="utf-8")
    marker = "load();pLoad();resize();"
    assert marker in html, "找不到注入點 load();pLoad();resize();"
    body = html.replace(marker, HOOK + marker, 1).encode("utf-8")

    def handle(route):
        url = urlparse(route.request.url)
        if f"{url.scheme}://{url.netloc}" != ORIGIN:
            route.abort()
            return
        path = unquote(url.path)
        if path == GAME_PATH:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            return
        local = (ROOT / path.lstrip("/")).resolve()
        if local.is_file() and local.is_relative_to(ROOT):
            route.fulfill(status=200, path=str(local))
        else:
            route.fulfill(status=404, body="not found")

    page.route("**/*", handle)
    page.goto(ORIGIN + GAME_PATH)


def main() -> int:
    from playwright.sync_api import sync_playwright
    html_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "games" / "2026-10-17-001" / "index.html"
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 480, "height": 800})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        open_with_hook(page, html_path)
        page.wait_for_timeout(800)
        res = page.evaluate(SIM_JS, {})
        browser.close()
    res["pageerrors"] = errors

    G = res
    hold, fast = G["a_hold"], G["a_fastClear"]
    fixed_ids = set()
    for line in G["b_groups"]:
        for g in line.split(":", 1)[1].split(","):
            if g:
                fixed_ids.add(g.rsplit("x", 1)[0])
    spawned_1_10 = set()
    for wn, d in hold["spawnByWave"].items():
        if 1 <= int(wn) <= 10:
            spawned_1_10 |= set(d)
    need = {"shuttle_moth", "split_thread", "loose_thread"}
    # 標題頁除了遊戲名、開始提示、選卡示意的標籤與裝飾 emoji，剩下的字都算「規則／說明」
    deco = {"喵窟擋十波", "點一下開始", "40🐟", "① 選卡", "② 點格放塔"}
    rule_lines = [s for s in G["d_titleFresh"] if s not in deco and len(s) > 2]
    checks = [
        ("(a) 王慢走：第 11 波開打時已通關", hold["t11"] is not None and hold["victoryAt11"] is True,
         f"victoryAt={hold['victoryAt']} t11={hold['t11']} victoryAt11={hold['victoryAt11']}"),
        ("(a) 第 10 波未清時按提早開波不會跳第 11 波",
         bool(hold["earlyTried"]) and all(e["waveAfter"] == e["waveBefore"] for e in hold["earlyTried"]),
         json.dumps(hold["earlyTried"], ensure_ascii=False)),
        ("(a) 提早清完第 10 波：通關後 ≤8 秒接第 11 波",
         fast["victoryAt"] is not None and fast["t11"] is not None and 0 < fast["t11"] - fast["victoryAt"] <= 8,
         f"victoryAt={fast['victoryAt']} t11={fast['t11']}"),
        ("(b) 三種怪都在第 1～10 波 waves.groups", need <= fixed_ids, ", ".join(sorted(need - fixed_ids)) or "全在"),
        ("(b) 三種怪在第 1～10 波真的有生成", need <= spawned_1_10, ", ".join(sorted(need - spawned_1_10)) or "全有"),
        ("(c) Echo 情境（兩座打不到的塔）最長無操作空窗 <12 秒", G["c_echo"]["maxNoOpGap"] < 12,
         f"{G['c_echo']['maxNoOpGap']}s（起點 {G['c_echo']['gapStartsAt']}s）"),
        ("(c) 一有錢就蓋廢塔：最長空窗 <12 秒", G["c_greedy"]["maxNoOpGap"] < 12,
         f"{G['c_greedy']['maxNoOpGap']}s（起點 {G['c_greedy']['gapStartsAt']}s）"),
        ("(c) 錢全拿去升級廢塔：最長空窗 <12 秒", G["c_upgradeSink"]["maxNoOpGap"] < 12,
         f"{G['c_upgradeSink']['maxNoOpGap']}s（起點 {G['c_upgradeSink']['gapStartsAt']}s）"),
        ("(c) 機器人正常玩四圖：最長空窗 <12 秒", G["botMaxGap"] < 12, f"{G['botMaxGap']}s"),
        ("(d) 標題頁規則只剩一句", len(rule_lines) == 1, " / ".join(rule_lines)),
        ("開局照提示：點卡＋點閃爍格第一座塔蓋成功", G["firstAction"]["towers"] == 1, json.dumps(G["firstAction"])),
        ("頁面沒有 JS 例外", not errors, "; ".join(errors)),
    ]
    print("== 機器人四圖 ==")
    for b in G["bot"]:
        print(f"  {b['map']}: victory={b['victory']} wave={b['wave']} lives={b['lives']} score={b['score']} "
              f"stars={b['stars']} towers={b['towers']} t11={b['t11']}")
    print("== 第 1～10 波 groups ==")
    for line in G["b_groups"]:
        print("  " + line)
    print("== 無限樣板 ==")
    for line in G["b_templ"]:
        print("  " + line)
    print("== 標題頁畫出的字 ==\n  " + " | ".join(G["d_titleFresh"]))
    print("== 檢查 ==")
    ok = True
    for name, passed, detail in checks:
        ok &= bool(passed)
        print(f"  {'✅' if passed else '❌'} {name}：{detail}")
    print("🎉 四項全部通過" if ok else "⚠️ 有項目沒過")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
