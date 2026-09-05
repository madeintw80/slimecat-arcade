# -*- coding: utf-8 -*-
"""SlimeCat v3 多階段生產線（2026-09-05 Boss 拍板 2B，Phase 1 落地）。

跟 v2.2「一次生成整款」的差別：把一款遊戲拆成可各自驗證的階段，每階段落檔在 factory/runs/<run_id>/：

  企劃書（模組合約）→ 引擎單檔（單一作者）→ 內容包（關卡／波次／升級／圖鑑，照合約 schema 分次生成）
  → 組裝 → Playwright 品管（煙霧＋壓力）→ 評審（Echo 獨立評審＋整合稽核，失敗回 sonnet）
  → 打磨（輸出 patch、不重印整檔）→ 上架／部署／推播（沿用 make_game 的既有函式）

模組分工：
  run.py          一輪的資料夾與狀態（斷點續跑、撞額度補跑用）
  stages.py       各階段 prompt／交稿解析／合約與內容包驗證
  patch.py        SEARCH/REPLACE patch 的解析與套用
  qa.py           品管：既有煙霧測試＋延長壓力測試
  echo_review.py  Phase 2：委派 Echo（codex exec read-only）當獨立評審，失敗 fail-open
  pipeline.py     串起所有階段的 produce_v3()

程式碼不拆給多個模型寫：引擎永遠一個作者（fable），內容包只是「照 schema 填資料」。
"""
