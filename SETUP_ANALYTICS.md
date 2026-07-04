# 數據追蹤啟用步驟（一次性，約 3 分鐘）

Sheet 我已經建好了：**SlimeCat Analytics**（在你的 Google Drive 根目錄）。
剩下 Apps Script 要你在瀏覽器手動部署（Google 不開放遠端部署，跟 Portfolio 的 Apps Script 一樣）。

## 步驟

1. 打開 Google Drive → 開啟「**SlimeCat Analytics**」這份 Sheet
2. 上方選單「**擴充功能 → Apps Script**」→ 把 `apps_script/Code.gs` 的內容整份貼上（蓋掉預設內容）→ 存檔
3. 右上「**部署 → 新增部署作業**」：
   - 類型選「**網頁應用程式**」
   - 執行身分：**我**
   - 誰可以存取：**任何人**
   - 按「部署」→ 複製那串 **網頁應用程式網址**（`https://script.google.com/macros/s/…/exec`）
4. 把網址貼給 Batnini（說「analytics 網址是 …」），我會接上並重新部署網站

## 之後會發生什麼

- 每個玩家（含你自己）打開大廳/遊戲 → 匿名回報「open」
- 離開頁面 → 回報這次玩了幾秒（session）
- 遊戲結束 → 回報分數（over，新遊戲都會內建）
- 全部進 Sheet「events」分頁，**看報表**：跑
  `python C:/Users/User/projects/SlimeCatArcade/factory/analytics_pull.py`
  （或 Telegram 打「遊戲數據」）→ 每款的開啟次數／平均時長／回訪率
- 每週日 18:00 排程會把數據＋你的評分餵給工作室檢討，回頭修設計聖經

## Code.gs 改版後怎麼更新（重新部署）

`apps_script/Code.gs` 內容有更新時（例如加了防灌水驗證），要讓線上生效：

1. 開「SlimeCat Analytics」Sheet → 擴充功能 → Apps Script
2. 把新版 `apps_script/Code.gs` 整份貼上蓋掉舊的 → 存檔
3. 部署 → **管理部署作業** → 點 ✏️ 編輯 → 版本選「**新增版本**」→ 部署

⚠️ 用「管理部署作業→編輯」網址才不會變；如果按成「新增部署作業」會產生一條新網址，就要重新貼給 Batnini 接一次。

## 隱私

回報內容只有：事件名、遊戲 id、秒數/分數、隨機裝置字串、距首訪天數、是否手機。
沒有姓名、IP 不落地、沒有 cookie。
