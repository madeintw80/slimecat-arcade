// SlimeCat 遊戲區 — 匿名數據回報（點擊率 / 活躍時長 / 回訪留存）
// 原理：sendBeacon 把小事件丟到 Google Apps Script → 寫進「SlimeCat Analytics」Sheet。
// 沒設定 SC_ANALYTICS_URL 時整支自動休眠，遊戲照常玩。
// 自己人排除：在瀏覽器 console 跑 localStorage.sc_ignore = 1 → 這台裝置從此不回報。
(function () {
  const URL = window.SC_ANALYTICS_URL || "";
  if (!URL) return;
  try { if (localStorage.getItem("sc_ignore")) return; } catch (e) {}

  // 這是哪一款遊戲（大廳 = arcade）
  const m = location.pathname.match(/games\/([^/]+)\//);
  const gid = m ? m[1] : "arcade";

  // 匿名裝置 ID（隨機字串，不含任何個資）
  let did = "anon";
  try {
    did = localStorage.getItem("sc_did");
    if (!did) {
      did = Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem("sc_did", did);
    }
  } catch (e) {}

  // 留存：這台裝置第一次來是什麼時候（算 D1/D7 回訪用）
  let days = 0;
  try {
    let first = localStorage.getItem("sc_first");
    if (!first) { first = String(Date.now()); localStorage.setItem("sc_first", first); }
    days = Math.floor((Date.now() - +first) / 86400000);
  } catch (e) {}

  function send(ev, val) {
    try {
      navigator.sendBeacon(URL, JSON.stringify({
        ev, game: gid, val: val || 0, did, days,
        mob: /Mobi|Android/i.test(navigator.userAgent) ? 1 : 0,
      }));
    } catch (e) {}
  }

  // 事件 1：打開（= 點擊率的分子）
  send("open");

  // 事件 2：離開時回報「活躍秒數」——只累積有互動的時間。
  // 兩次互動間隔超過 30 秒的部分不計，所以頁面開著掛機不會灌水。
  const IDLE_GAP = 30000;
  let activeMs = 0;
  let lastPoke = Date.now();
  function poke() {
    const now = Date.now();
    activeMs += Math.min(now - lastPoke, IDLE_GAP);
    lastPoke = now;
  }
  ["pointerdown", "pointermove", "touchstart", "touchmove", "keydown"].forEach(
    (e) => addEventListener(e, poke, { passive: true })
  );

  let sent = false;
  function bye() {
    if (sent) return;
    sent = true;
    poke(); // 把最後一段活躍時間結清
    send("session", Math.round(activeMs / 1000));
  }
  addEventListener("pagehide", bye);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") bye();
  });

  // 事件 3（選配）：遊戲主動回報一局結束與分數 → window.SC.over(score)
  window.SC = { over: (s) => send("over", s | 0) };
})();
