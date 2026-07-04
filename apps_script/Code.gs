// SlimeCat Analytics — 接收遊戲區的匿名事件＋玩家評分留言（v3 硬化版）
// 部署方式見專案根目錄 SETUP_ANALYTICS.md（貼在「SlimeCat Analytics」Sheet 的 Apps Script 裡）
// ⚠️ 改過這份檔要「重新部署」才生效：部署 → 管理部署作業 → ✏️ 編輯 → 版本選「新增版本」→ 部署（網址不變）

const MAX_ROWS = 200000; // 保險絲：單一分頁超過這個列數就停收，防惡意灌爆 Sheet
const VAL_CAP = { open: 0, session: 86400, over: 10000000, rate: 10 }; // 各事件的數值上限

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);

    // 事件白名單：只認這四種
    const ev = String(d.ev || "");
    if (ev !== "open" && ev !== "session" && ev !== "over" && ev !== "rate") return _ok();

    // 遊戲 id / 裝置 id：只收小寫英數與連字號（垃圾字串與公式注入進不來）
    const game = String(d.game || "");
    const did = String(d.did || "");
    if (!/^[a-z0-9-]{1,40}$/.test(game)) return _ok();
    if (!/^[a-z0-9-]{1,40}$/.test(did)) return _ok();

    // 數值範圍檢查（超界＝亂送的，丟棄）
    const val = Number(d.val || 0);
    const days = Number(d.days || 0);
    const mob = Number(d.mob || 0) ? 1 : 0;
    if (!isFinite(val) || val < 0 || val > VAL_CAP[ev]) return _ok();
    if (!isFinite(days) || days < 0 || days > 36500) return _ok();

    if (ev === "rate") {
      // 評分要 1~10 整數，留言消毒後另存 ratings 分頁
      if (val < 1) return _ok();
      const note = _clean(d.note);
      const sheet = _sheet("ratings", ["時間", "遊戲", "分數", "留言", "裝置ID", "手機"]);
      if (sheet.getLastRow() >= MAX_ROWS) return _ok();
      sheet.appendRow([new Date(), game, Math.round(val), note, did, mob]);
      return _ok();
    }

    const sheet = _sheet("events", ["時間", "事件", "遊戲", "數值", "裝置ID", "距首訪天數", "手機"]);
    if (sheet.getLastRow() >= MAX_ROWS) return _ok();
    sheet.appendRow([new Date(), ev, game, Math.round(val), did, Math.round(days), mob]);
  } catch (err) { /* 壞資料直接略過 */ }
  return _ok();
}

// 留言消毒：截斷 200 字＋擋 Sheet 公式注入（=+-@ 開頭補一個 ' 前綴）
function _clean(raw) {
  let s = String(raw || "").slice(0, 200).replace(/[\r\n\t]+/g, " ").trim();
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  return s;
}

// 取得分頁；不存在就自動建立並補標題列（用戶不用手動開分頁）
function _sheet(name, headers) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(headers);
  }
  return sh;
}

function _ok() { return ContentService.createTextOutput("ok"); }

function doGet() {
  return ContentService.createTextOutput("SlimeCat Analytics alive 🐱 v3");
}
