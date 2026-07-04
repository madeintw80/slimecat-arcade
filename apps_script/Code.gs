// SlimeCat Analytics — 接收遊戲區的匿名事件
// 部署方式見專案根目錄 SETUP_ANALYTICS.md（貼在「SlimeCat Analytics」Sheet 的 Apps Script 裡）

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    SpreadsheetApp.getActive().getSheetByName("events").appendRow([
      new Date(),
      String(d.ev || ""),     // 事件：open / session / over
      String(d.game || ""),   // 遊戲 id（arcade = 大廳）
      Number(d.val || 0),     // session=秒數、over=分數
      String(d.did || ""),    // 匿名裝置 ID
      Number(d.days || 0),    // 距這台裝置首訪的天數（算留存）
      Number(d.mob || 0),     // 1=手機
    ]);
  } catch (err) { /* 壞資料直接略過 */ }
  return ContentService.createTextOutput("ok");
}

function doGet() {
  return ContentService.createTextOutput("SlimeCat Analytics alive 🐱");
}
