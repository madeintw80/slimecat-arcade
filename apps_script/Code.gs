// SlimeCat Analytics — 接收遊戲區的匿名事件（硬化版：格式不對的直接丟棄）
// 部署方式見專案根目錄 SETUP_ANALYTICS.md（貼在「SlimeCat Analytics」Sheet 的 Apps Script 裡）
// ⚠️ 改過這份檔要「重新部署」才生效：部署 → 管理部署作業 → ✏️ 編輯 → 版本選「新增版本」→ 部署（網址不變）

const MAX_ROWS = 200000; // 保險絲：events 超過這個列數就停收，防惡意灌爆 Sheet
const VAL_CAP = { open: 0, session: 86400, over: 10000000 }; // 各事件的數值上限（停留最多一天、分數最多一千萬）

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);

    // 事件白名單：只認這三種
    const ev = String(d.ev || "");
    if (ev !== "open" && ev !== "session" && ev !== "over") return _ok();

    // 遊戲 id / 裝置 id：只收小寫英數與連字號 → 垃圾字串與公式注入（=IMPORTRANGE 之類）進不來
    const game = String(d.game || "");
    const did = String(d.did || "");
    if (!/^[a-z0-9-]{1,40}$/.test(game)) return _ok();
    if (!/^[a-z0-9-]{1,40}$/.test(did)) return _ok();

    // 數值範圍檢查（超界＝亂送的，丟棄）
    const val = Number(d.val || 0);
    const days = Number(d.days || 0);
    if (!isFinite(val) || val < 0 || val > VAL_CAP[ev]) return _ok();
    if (!isFinite(days) || days < 0 || days > 36500) return _ok();

    const sheet = SpreadsheetApp.getActive().getSheetByName("events");
    if (sheet.getLastRow() >= MAX_ROWS) return _ok(); // 保險絲

    sheet.appendRow([
      new Date(),
      ev,                       // 事件：open / session / over
      game,                     // 遊戲 id（arcade = 大廳）
      Math.round(val),          // session=活躍秒數、over=分數
      did,                      // 匿名裝置 ID
      Math.round(days),         // 距這台裝置首訪的天數（算留存）
      Number(d.mob || 0) ? 1 : 0, // 1=手機
    ]);
  } catch (err) { /* 壞資料直接略過 */ }
  return _ok();
}

function _ok() { return ContentService.createTextOutput("ok"); }

function doGet() {
  return ContentService.createTextOutput("SlimeCat Analytics alive 🐱");
}
