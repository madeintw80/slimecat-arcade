// SlimeCat 遊戲區 — 匿名數據回報（點擊率 / 停留時長 / 回訪留存）
// 原理：sendBeacon 把小事件丟到 Google Apps Script → 寫進「SlimeCat Analytics」Sheet。
// 沒設定 SC_ANALYTICS_URL 時整支自動休眠，遊戲照常玩。
(function () {
  const URL = window.SC_ANALYTICS_URL || "";
  if (!URL) return;

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

  // 事件 2：離開時回報這次玩了幾秒（= 停留時長）
  const t0 = Date.now();
  let sent = false;
  function bye() {
    if (sent) return;
    sent = true;
    send("session", Math.round((Date.now() - t0) / 1000));
  }
  addEventListener("pagehide", bye);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") bye();
  });

  // 事件 3（選配）：遊戲主動回報一局結束與分數 → window.SC.over(score)
  window.SC = { over: (s) => send("over", s | 0) };
})();
