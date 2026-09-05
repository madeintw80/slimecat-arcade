# -*- coding: utf-8 -*-
"""v3 生產線總管：produce_v3(decon) 把一份解構筆記（或原創企劃）變成上架的遊戲。

  企劃書＋合約 → 引擎（examples 版先過煙霧測試）→ 內容包（逐包生成＋schema 驗證）→ 組裝
  → 撥號＋品管（煙霧＋壓力；沒過先用 patch 修一輪）→ 評審（Echo → 失敗回 sonnet）
  → 打磨（稽核缺陷／低分才觸發，patch 交稿，品管過才採用）→ 上架／部署／推播

每階段落檔在 factory/runs/<run_id>/（見 run.py），撞額度 → 記續跑指標＋schedule_retry；
補跑那輪從斷點續跑（不用重付已完成的階段）。上架／部署／推播沿用 make_game 的函式。
"""
import datetime
import json
import re
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # factory/
sys.path.insert(0, str(HERE))
import make_game as mg          # noqa: E402
import rebuild                  # noqa: E402
from validate_game import validate   # noqa: E402
from v3 import stages, qa, echo_review   # noqa: E402
from v3.patch import PatchError         # noqa: E402
from v3.run import Run                  # noqa: E402

PLANS_DIR = mg.KNOW / "plans"   # 企劃書永久留存（跟解構筆記一樣是工作室的功力）
USE_ECHO = True                 # Phase 2：評審先問 Echo，不可用回 sonnet；--no-echo 可關
MAX_ENGINE_ATTEMPTS = 2         # 引擎交稿＋煙霧測試最多試幾次
MAX_PLAN_ATTEMPTS = 2           # 合約格式壞掉重做幾次


def log(msg: str) -> None:
    mg.log(msg)


def _slug(text: str) -> str:
    return re.sub(r"[^\w一-鿿-]+", "_", text or "")[:40].strip("_") or "untitled"


def _final_html(html: str, contract: dict, decon: dict) -> str:
    """成品檔＝GAMEMETA 標頭（其他工具靠它認 meta）＋stats 標籤＋組裝後網頁。"""
    meta = {"title": contract["title"], "emoji": contract["emoji"], "genre": contract["genre"],
            "inspiration": decon.get("source", ""), "desc": contract["desc"]}
    header = "<!--GAMEMETA " + json.dumps(meta, ensure_ascii=False) + "-->"
    return header + "\n" + mg.inject_stats(html)


def _write_game(gdir: Path, html: str, contract: dict, decon: dict) -> None:
    (gdir / "index.html").write_text(_final_html(html, contract, decon), encoding="utf-8")


def _save_plan_copy(plan_doc: str, contract: dict, today: str) -> Path:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    p = PLANS_DIR / f"{today}-{_slug(contract['title'])}.md"
    p.write_text(plan_doc.rstrip() + "\n\n===CONTRACT===\n"
                 + json.dumps(contract, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------- 各階段
def _plan(run: Run, decon: dict, past_games: list, today: str) -> tuple:
    if run.done("plan"):
        log(f"⏭️ 企劃書已完成（續跑），略過")
        return run.read_text("plan.md"), run.read_json("contract.json")
    feedback = ""
    for attempt in range(1, MAX_PLAN_ATTEMPTS + 1):
        log(f"📐 企劃書＋模組合約（{stages.MODEL_PLAN} effort={stages.EFFORT_PLAN or '預設'}，第 {attempt} 次）…")
        try:
            plan_doc, contract, raw = stages.stage_plan(decon, past_games, feedback)
            break
        except mg.OutputLimitError as e:
            feedback = f"上一次超過輸出上限被截斷（{e}）。企劃書本體壓在 3,000 字內、合約 JSON 精簡（每個內容包 examples 只給 1 筆）。"
            log(f"  ❌ 企劃書爆輸出上限：{e}")
            if attempt == MAX_PLAN_ATTEMPTS:
                raise RuntimeError(f"企劃書兩次都超過輸出上限：{e}")
        except ValueError as e:
            feedback = str(e)[:300]
            log(f"  ⚠️ 合約不合格：{feedback}")
            if attempt == MAX_PLAN_ATTEMPTS:
                raise RuntimeError(f"企劃書合約兩次都不合格：{feedback}")
    run.write_text("plan_raw.txt", raw)      # 原始輸出留檔（驗屍／對帳篇幅用）
    run.write_text("plan.md", plan_doc)
    run.write_json("contract.json", contract)
    packs = {p["key"]: p["count"] for p in contract["content_packs"]}
    run.mark("plan", model=stages.MODEL_PLAN, effort=stages.EFFORT_PLAN, title=contract["title"], packs=packs)
    copy = _save_plan_copy(plan_doc, contract, today)
    log(f"  📘 《{contract['title']}》合約：內容包 {packs}；企劃書 → knowledge/plans/{copy.name}")
    return plan_doc, contract


def _engine(run: Run, plan_doc: str, contract: dict, decon: dict) -> tuple:
    if run.done("engine"):
        log("⏭️ 引擎已完成（續跑），略過")
        return run.read_text("engine.html"), run.get("content_notes", "")
    feedback, tight = "", False
    for attempt in range(1, MAX_ENGINE_ATTEMPTS + 1):
        effort = stages.TIGHT_ENGINE_EFFORT if tight else stages.EFFORT_ENGINE
        log(f"🛠️ 引擎（{stages.MODEL_ENGINE} effort={effort or '預設'}，上限 {stages.engine_line_budget(contract, tight)} 行，"
            f"第 {attempt}/{MAX_ENGINE_ATTEMPTS} 次，最多等 {stages.ENGINE_TIMEOUT // 60} 分鐘）…")
        try:
            engine_html, notes = stages.stage_engine(plan_doc, contract, decon, feedback, tight=tight)
        except mg.OutputLimitError as e:
            # 交稿被輸出上限截斷：下一次用緊縮模式（行數 1,400、effort medium）
            tight = True
            feedback = (f"上一次交稿超過輸出上限被截斷（{e}）。這次整個檔案必須壓在 {stages.TIGHT_ENGINE_LINES} 行內："
                        f"去掉裝飾性註解、合併小模組、不要重複程式碼；寧可少一個次要系統也要一次交完整。")
            log(f"  ❌ 引擎爆輸出上限：{e} → 下次改緊縮模式")
            continue
        except ValueError as e:
            feedback = str(e)
            log(f"  ❌ 引擎交稿失敗：{e}")
            continue
        # 用合約的 examples 先跑煙霧測試——引擎壞了就別浪費內容包那幾次呼叫
        probe = stages.assemble(engine_html, stages.examples_content(contract))
        run.write_text("engine_probe.html", probe)
        try:
            ok, errs = validate(run.path("engine_probe.html"), shot_name=f"{run.id}-engine")
        except Exception as e:
            ok, errs = False, [f"playwright 掛了：{e}"]
        lines = engine_html.count("\n") + 1
        if ok:
            run.write_text("engine.html", engine_html)
            run.set("content_notes", notes)
            run.mark("engine", model=stages.MODEL_ENGINE, effort=effort, tight=tight,
                     lines=lines, attempts=attempt, has_notes=bool(notes),
                     has_hooks="SC_HOOKS" in engine_html)
            log(f"  ✅ 引擎 {lines} 行通過煙霧測試（CONTENT-NOTES {'有' if notes else '無'}）")
            return engine_html, notes
        feedback = "\n".join(errs)[:800]
        log(f"  ❌ 引擎煙霧測試失敗：{errs}")
    raise RuntimeError(f"引擎 {MAX_ENGINE_ATTEMPTS} 次都沒過：{feedback[:200]}")


def _content(run: Run, plan_doc: str, contract: dict, notes: str, regen: set = None) -> dict:
    """逐包生成：被引用的包先生，後面的包拿到「可引用 id 清單」，生完做跨包引用驗證。

    regen：要重生的 pack key（其他包沿用 run 裡的檔案）；None＝正常流程（已有檔案就略過）。
    """
    content, available = {}, {}
    for pack in stages.order_packs(contract):
        key, name = pack["key"], f"content_{pack['key']}.json"
        if run.has(name) and not (regen and key in regen):
            content[key] = run.read_json(name)
            available[key] = stages.pack_ids(content[key])
            log(f"⏭️ 內容包 {key} 已有（{len(content[key])} 筆），沿用")
            continue
        refs = stages.ref_fields(pack, contract)
        log(f"📦 內容包「{pack['label']}」{key} ×{pack['count']}（{stages.MODEL_CONTENT}"
            + (f"；引用 {sorted(set(refs.values()))}" if refs else "") + "）…")
        items = stages.stage_content(pack, plan_doc, contract, notes, available)
        run.write_json(name, items)
        content[key] = items
        available[key] = stages.pack_ids(items)
        log(f"  ✅ {len(items)} 筆通過驗證（schema＋跨包引用）")
    # 全部生完再交叉核對一次（排序退回合約順序時，先生的包可能引用後生的）
    for pack in contract["content_packs"]:
        bad = stages.find_bad_refs(content.get(pack["key"], []), stages.ref_fields(pack, contract), available)
        if bad:
            log(f"  ⚠️ 內容包 {pack['key']} 仍有無效引用（引擎會略過）：{bad[:3]}")
    run.mark("content", packs={k: len(v) for k, v in content.items()}, model=stages.MODEL_CONTENT)
    return content


def _review(run: Run, plan_doc: str, contract: dict, html: str, qa_info: dict, gid: str):
    if run.has("review.json"):
        log("⏭️ 評審已完成（續跑），略過")
        return run.read_json("review.json")
    crit = None
    if USE_ECHO:
        try:
            crit = echo_review.review(run, plan_doc, contract, html, qa_info, gid)
        except mg.QuotaError:
            raise
        except echo_review.EchoUnavailableError as e:
            log(f"  ⚠️ Echo 不可用，fail-open 回 {stages.MODEL_CRITIC}：{e}")
        except Exception as e:  # noqa: BLE001 — 任何意外都不該擋生產
            log(f"  ⚠️ Echo 委派出錯，fail-open 回 {stages.MODEL_CRITIC}：{e}")
    if crit is None:
        log(f"🧐 評審自評中（{stages.MODEL_CRITIC}）…")
        crit = stages.stage_critic(plan_doc, contract, html, qa_info)
    if crit:
        run.write_json("review.json", crit)
        log(f"  📋 評審 {crit['total']}/50（{crit.get('reviewer')}）：{crit.get('verdict', '')}")
    return crit


def _polish_issues(crit: dict) -> list:
    """要修什麼：稽核的 bug 優先、再合約缺陷；都沒有但低分就修評審第一條。"""
    au = crit.get("audit") or {}
    issues = [f"[bug] {b}" for b in (au.get("bugs") or [])[:2]]
    issues += [f"[合約缺陷] {c}" for c in (au.get("contract_issues") or [])[:1]]
    if not issues and crit["total"] < mg.POLISH_BAR and crit.get("fixes"):
        issues = [f"[評審改進點] {crit['fixes'][0]}"]
    return issues


# ---------------------------------------------------------------- 主流程
def produce_v3(decon: dict, run: Run = None, publish: bool = True) -> int:
    """回 0＝上架完成或已排補跑；1＝失敗。decon 可為 None（續跑時從 run 資料夾讀）。"""
    run = run or Run()
    if run.has("decon.json"):
        decon = run.read_json("decon.json")
    else:
        run.write_json("decon.json", decon)
        run.write_text("decon.md", decon.get("doc", ""))
    log(f"🏭 v3 生產線 run={run.id}（靈感：{decon.get('source', '?')}，來源 {decon.get('origin', '?')}）")
    data = json.loads(mg.GAMES_JSON.read_text(encoding="utf-8"))   # 只當 prompt 素材
    today = datetime.date.today().isoformat()
    gdir, released = None, False
    try:
        plan_doc, contract = _plan(run, decon, data["games"], today)
        engine_html, notes = _engine(run, plan_doc, contract, decon)
        content = _content(run, plan_doc, contract, notes)

        # ── 組裝 ──
        html = run.read_text("polished.html") if run.has("polished.html") else stages.assemble(engine_html, content)
        run.write_text("assembled.html", html)

        # ── 撥號＋品管 ──
        gid = run.get("gid")
        if gid and (mg.GAMES_DIR / gid).exists():
            gdir = mg.GAMES_DIR / gid
        else:
            gid, gdir = mg.reserve_game_dir(today)
            run.set("gid", gid)
        _write_game(gdir, html, contract, decon)
        log(f"🧪 品管（煙霧＋壓力 {qa.STRESS_SECS} 秒）→ games/{gid}/ …")
        ok, errs, qa_info = qa.run_qa(gdir / "index.html", gid)
        run.write_json("qa.json", {"ok": ok, "errors": errs, "info": qa_info})
        if not ok:
            log(f"  ❌ 品管失敗：{errs}；用 patch 修一輪…")
            fixed = False
            try:
                patch_text, html2 = stages.stage_polish_patch(
                    html, [f"[品管錯誤] {e}" for e in errs[:3]], contract)
                run.write_text("patch_qa.txt", patch_text)
                if html2:
                    _write_game(gdir, html2, contract, decon)
                    ok, errs, qa_info = qa.run_qa(gdir / "index.html", gid)
                    run.write_json("qa.json", {"ok": ok, "errors": errs, "info": qa_info, "after_patch": True})
                    fixed = ok
                    if ok:
                        html = html2
                        run.write_text("assembled.html", html)
            except (PatchError, ValueError, RuntimeError) as e:
                log(f"  ⚠️ 品管修復 patch 失敗：{e}")
            if not fixed:
                raise RuntimeError(f"品管沒過：{'；'.join(errs)[:300]}")
        log(f"  ✅ 品管通過（內容包 {qa_info.get('content')}）")

        # ── 評審（Echo → sonnet）──
        crit = _review(run, plan_doc, contract, html, qa_info, gid)

        # ── 打磨（patch；稽核缺陷／低分才觸發）──
        polish_note = ""
        if crit and not run.done("polish"):
            issues = _polish_issues(crit)
            if issues:
                log(f"🪄 打磨（{stages.MODEL_POLISH} effort={stages.EFFORT_POLISH}）：{len(issues)} 項 → patch…")
                for it in issues:
                    log(f"    • {it[:100]}")
                try:
                    patch_text, html2 = stages.stage_polish_patch(html, issues, contract)
                    run.write_text("patch.txt", patch_text)
                    if html2 is None:
                        log("  ↩️ 開發者回 NOPATCH，沿用原版")
                    else:
                        _write_game(gdir, html2, contract, decon)
                        ok2, errs2, _ = qa.run_qa(gdir / "index.html", gid)
                        if ok2:
                            html = html2
                            run.write_text("polished.html", html2)
                            polish_note = "；".join(i.split("] ", 1)[-1][:40] for i in issues)
                            mg.append_learning(f"- {today} 打磨《{contract['title']}》patch 修 {len(issues)} 項："
                                               f"{polish_note[:80]}（品管通過採用）")
                            log("  ✨ 修訂版品管通過，採用")
                        else:
                            log(f"  ↩️ 修訂版品管沒過（{errs2}），改回原版")
                            _write_game(gdir, html, contract, decon)
                            qa.run_qa(gdir / "index.html", gid)   # 換回原版縮圖
                except (PatchError, ValueError, RuntimeError) as e:
                    log(f"  ⚠️ 打磨 patch 失敗（沿用原版）：{e}")
                    _write_game(gdir, html, contract, decon)
                run.mark("polish", adopted=bool(polish_note), issues=issues)
            else:
                run.mark("polish", adopted=False, issues=[])
                log("  🪄 稽核零缺陷且評審達標，不打磨")

        # ── 上架 ──
        shot_src = mg.HERE / "shots" / f"{gid}.png"
        if shot_src.exists():
            shutil.copy(shot_src, gdir / "shot.png")
        packs = {k: len(v) for k, v in content.items()}
        entry = {"id": gid, "title": contract["title"], "emoji": contract["emoji"],
                 "genre": contract["genre"], "date": today,
                 "inspiration": decon.get("source", ""), "desc": contract["desc"],
                 "pipeline": "v3", "packs": packs}
        if crit:
            entry["ai_score"] = crit["total"]
            entry["reviewer"] = crit.get("reviewer", "")
            if crit.get("howto"):
                entry["howto"] = crit["howto"]
            au = crit.get("audit") or {}
            mg.append_learning(
                f"- {today} AI 自評《{contract['title']}》{crit['total']}/50："
                f"{crit.get('verdict', '')}；待改進：{'；'.join(crit.get('fixes', [])[:3])}"
                f"（v3、評審 {crit.get('reviewer', '?')}、稽核 合約 {len(au.get('contract_issues', []))}／"
                f"bug {len(au.get('bugs', []))}）")
        if polish_note:
            entry["polished"] = polish_note
        fresh = json.loads(mg.GAMES_JSON.read_text(encoding="utf-8"))   # read-then-update，防蓋檔
        fresh["games"].append(entry)
        mg.GAMES_JSON.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        rebuild.rebuild()
        history = (json.loads(mg.HISTORY_FILE.read_text(encoding="utf-8"))
                   if mg.HISTORY_FILE.exists() else {"used": []})
        history["used"].append({"date": today, "inspiration": decon.get("source", ""),
                                "title": contract["title"], "id": gid, "run": run.id})
        mg.HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        released = True
        run.mark("release", gid=gid, published=publish)
        run.write_json("usage.json", {"records": mg.USAGE, "summary": mg.usage_summary()})
        Run.clear_resume_pointer()
        log(f"✅ 上架完成：《{contract['title']}》（全站第 {len(fresh['games'])} 款，games/{gid}/）")
        log(f"   本次用量：{mg.usage_summary()}")

        if not publish:
            log("   --no-publish：不部署、不推播（本機 games/ 已可玩）")
            return 0
        extra = (f"v3 生產線：企劃書→引擎({run.state['stages'].get('engine', {}).get('lines', '?')}行)"
                 f"→內容包 {packs}→組裝→品管→評審→打磨\n"
                 f"評審：{(crit or {}).get('reviewer', '無')}"
                 + (f"（稽核：合約缺陷 {len((crit.get('audit') or {}).get('contract_issues', []))}、"
                    f"bug {len((crit.get('audit') or {}).get('bugs', []))}）" if crit else "")
                 + f"\n紀錄：factory/runs/{run.id}")
        try:
            import publish_site
            publish_site.publish(f"🏭 新遊戲《{contract['title']}》上架（v3）")
            mg.notify_release(entry, crit, decon, polish_note, extra=extra)
        except Exception as e:
            log(f"⚠️ 自動部署失敗（本機照常可玩）：{e}")
            mg.notify_fail(f"《{contract['title']}》已生成但部署失敗、公開站尚未更新：{e}")
        return 0

    except mg.QuotaError as e:
        run.set_resume_pointer()
        log(f"⏳ 撞額度（{run.summary()}），下輪從斷點續跑：{e}")
        return 0 if mg.schedule_retry("factory", e.resets_at, str(e)) else 1
    except Exception as e:  # noqa: BLE001
        log(f"❌ v3 生產失敗：{e}")
        log(traceback.format_exc()[-1500:])
        Run.clear_resume_pointer()
        if gdir is not None and not released:
            shutil.rmtree(gdir, ignore_errors=True)
        mg.notify_fail(f"v3 run {run.id} 失敗：{str(e)[:200]}")
        return 1


# ---------------------------------------------------------------- 已上架遊戲：再打磨一輪（patch）
def polish_released(run: Run, publish: bool = True, max_items: int = 3) -> int:
    """對已上架的 v3 遊戲，拿最新一份評審（review_regen.json 優先）的稽核 bug／合約缺陷再打磨一輪。

    跟生產線裡的打磨同一套：fable 交 SEARCH/REPLACE patch → 套用 → 品管過才覆蓋上線＋更新日誌。
    """
    gid = run.get("gid")
    gdir = mg.GAMES_DIR / gid if gid else None
    if not gid or not (gdir / "index.html").exists():
        log(f"❌ run {run.id} 沒有上架的遊戲可打磨（gid={gid}）")
        return 1
    rev_name = "review_regen.json" if run.has("review_regen.json") else "review.json"
    if not run.has(rev_name):
        log("❌ 沒有評審結果可用，先跑評審")
        return 1
    crit = run.read_json(rev_name)
    issues = _polish_issues(crit)[:max_items]
    if not issues:
        log("🪄 評審沒有要修的項目，不打磨")
        return 0
    contract, decon = run.read_json("contract.json"), run.read_json("decon.json")
    base_name = "polished.html" if run.has("polished.html") else "assembled.html"
    html = run.read_text(base_name)
    prev_game = (gdir / "index.html").read_text(encoding="utf-8")
    log(f"🪄 再打磨《{contract['title']}》（{stages.MODEL_POLISH} effort={stages.EFFORT_POLISH}）：{len(issues)} 項 → patch…")
    for it in issues:
        log(f"    • {it[:110]}")
    try:
        patch_text, html2 = stages.stage_polish_patch(html, issues, contract)
        run.write_text("patch_released.txt", patch_text)
        if html2 is None:
            log("  ↩️ 開發者回 NOPATCH，維持現版")
            return 0
        _write_game(gdir, html2, contract, decon)
        ok, errs, _ = qa.run_qa(gdir / "index.html", gid)
        if not ok:
            (gdir / "index.html").write_text(prev_game, encoding="utf-8")
            log(f"  ↩️ 修訂版品管沒過（{errs}），還原現版")
            return 1
        run.write_text("polished.html", html2)
        shot_src = mg.HERE / "shots" / f"{gid}.png"
        if shot_src.exists():
            shutil.copy(shot_src, gdir / "shot.png")
        today = datetime.date.today().isoformat()
        note = "；".join(i.split("] ", 1)[-1][:40] for i in issues)
        fresh = json.loads(mg.GAMES_JSON.read_text(encoding="utf-8"))
        for g in fresh.get("games", []):
            if g["id"] == gid:
                g["updated_at"] = today
                g.setdefault("changelog", []).append({"date": today, "summary": f"評審稽核後修正：{note[:120]}"})
                g["polished"] = note[:80]
                break
        mg.GAMES_JSON.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        rebuild.rebuild()
        mg.append_learning(f"- {today} 打磨《{contract['title']}》patch 修 {len(issues)} 項：{note[:80]}（品管通過採用）")
        run.mark("polish_released", issues=issues)
        log(f"  ✨ 修訂版品管通過，已採用（{len(issues)} 項）")
        if not publish:
            return 0
        try:
            import publish_site
            publish_site.publish(f"🔧 修復《{contract['title']}》：評審稽核後打磨（{len(issues)} 項）")
            if mg.tg and mg.tg.available():
                mg.tg.send(f"🪄《{contract['title']}》打磨上線：{note[:200]}\n👉 {mg.SITE_URL}games/{gid}/index.html")
        except Exception as e:
            log(f"⚠️ 部署失敗（本機已更新）：{e}")
            mg.notify_fail(f"《{contract['title']}》打磨完成但部署失敗：{e}")
        return 0
    except (PatchError, ValueError, RuntimeError) as e:
        (gdir / "index.html").write_text(prev_game, encoding="utf-8")
        log(f"  ⚠️ 打磨 patch 失敗（維持現版）：{e}")
        return 1


# ---------------------------------------------------------------- 已上架遊戲：重生內容包
def regen_content(run: Run, keys: list, review: bool = True, publish: bool = True) -> int:
    """對已上架的 v3 遊戲重生指定內容包（沿用引擎），品管過就覆蓋上線並記更新日誌。

    用途：內容包出問題（引用不存在的 id、數值曲線壞掉…）時不用重做整款——引擎那 $5 留著，
    只重付幾毛錢的內容包。流程：重生（帶跨包引用驗證）→ 接進最新版 html → 品管 → 再評審（記錄用）
    → 覆蓋 games/<gid>/index.html → games.json 更新日誌 → 部署 → 私訊 Boss。
    """
    gid = run.get("gid")
    gdir = mg.GAMES_DIR / gid if gid else None
    if not gid or not (gdir / "index.html").exists():
        log(f"❌ run {run.id} 沒有上架的遊戲可修（gid={gid}）")
        return 1
    contract, plan_doc, decon = run.read_json("contract.json"), run.read_text("plan.md"), run.read_json("decon.json")
    notes = run.get("content_notes", "")
    known = {p["key"] for p in contract["content_packs"]}
    keys = [k for k in keys if k in known]
    if not keys:
        log(f"❌ 沒有可重生的內容包（可選：{sorted(known)}）")
        return 1
    base_name = "polished.html" if run.has("polished.html") else "assembled.html"
    base_html = run.read_text(base_name)
    prev_game = (gdir / "index.html").read_text(encoding="utf-8")
    log(f"♻️ 重生內容包 {keys}（run {run.id}，games/{gid}，底稿 {base_name}）")
    try:
        content = _content(run, plan_doc, contract, notes, regen=set(keys))
        html = stages.assemble(base_html, content)
        _write_game(gdir, html, contract, decon)
        ok, errs, qa_info = qa.run_qa(gdir / "index.html", gid)
        run.write_json("qa_regen.json", {"ok": ok, "errors": errs, "info": qa_info, "packs": keys})
        if not ok:
            (gdir / "index.html").write_text(prev_game, encoding="utf-8")
            log(f"❌ 重生版品管沒過，已還原原版：{errs}")
            return 1
        run.write_text(base_name, html)
        log(f"  ✅ 品管通過（內容包 {qa_info.get('content')}）")
        crit = None
        if review:
            run.path("review.json").rename(run.path("review_before_regen.json")) if run.has("review.json") else None
            crit = _review(run, plan_doc, contract, html, qa_info, gid)
            if crit:
                run.write_json("review_regen.json", crit)
        shot_src = mg.HERE / "shots" / f"{gid}.png"
        if shot_src.exists():
            shutil.copy(shot_src, gdir / "shot.png")
        today = datetime.date.today().isoformat()
        labels = {p["key"]: p["label"] for p in contract["content_packs"]}
        summary = f"重生{'／'.join(labels[k] for k in keys)}內容：修正引用不存在的物件、每房都有可吞的成長階梯"
        fresh = json.loads(mg.GAMES_JSON.read_text(encoding="utf-8"))
        for g in fresh.get("games", []):
            if g["id"] == gid:
                g["updated_at"] = today
                g.setdefault("changelog", []).append({"date": today, "summary": summary})
                g["packs"] = {k: len(v) for k, v in content.items()}
                if crit:
                    g["ai_score"] = crit["total"]
                    g["reviewer"] = crit.get("reviewer", "")
                    if crit.get("howto"):
                        g["howto"] = crit["howto"]
                break
        mg.GAMES_JSON.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        rebuild.rebuild()
        mg.append_learning(f"- {today} 修復《{contract['title']}》重生內容包 {keys}：跨包引用驗證後首房可通關"
                           + (f"（再評 {crit['total']}/50 by {crit.get('reviewer')}）" if crit else ""))
        run.mark("regen:" + ",".join(keys), review=(crit or {}).get("total"))
        log(f"✅ 《{contract['title']}》內容包重生完成" + (f"，再評 {crit['total']}/50" if crit else ""))
        if not publish:
            return 0
        try:
            import publish_site
            publish_site.publish(f"🔧 修復《{contract['title']}》：內容包重生（{'、'.join(labels[k] for k in keys)}）")
            if mg.tg and mg.tg.available():
                au = (crit or {}).get("audit") or {}
                mg.tg.send(f"🔧《{contract['title']}》內容包重生上線：{summary}\n"
                           + (f"再評：{crit['total']}/50（{crit.get('reviewer')}）— {crit.get('verdict', '')}\n"
                              f"稽核：合約缺陷 {len(au.get('contract_issues', []))}、bug {len(au.get('bugs', []))}\n" if crit else "")
                           + f"👉 {mg.SITE_URL}games/{gid}/index.html")
        except Exception as e:
            log(f"⚠️ 部署失敗（本機已更新）：{e}")
            mg.notify_fail(f"《{contract['title']}》內容包重生完成但部署失敗：{e}")
        return 0
    except mg.QuotaError as e:
        (gdir / "index.html").write_text(prev_game, encoding="utf-8")
        log(f"⏳ 重生撞額度，已還原原版：{e}")
        return 1
    except Exception as e:  # noqa: BLE001
        (gdir / "index.html").write_text(prev_game, encoding="utf-8")
        log(f"❌ 重生失敗，已還原原版：{e}")
        log(traceback.format_exc()[-1200:])
        return 1
