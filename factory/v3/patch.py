# -*- coding: utf-8 -*-
"""打磨／修復用的 SEARCH/REPLACE patch：解析模型輸出、套用到原始碼。

為什麼改 patch 不重印整檔（TASKS「Later」項，v3 一起做）：
  大型遊戲 1,500～2,600 行，重印整檔＝每修一條缺陷就再付 50k 輸出 tokens，
  而且重印時模型很容易「順手」改到別的地方（0809 打磨 7 次只採用 2 次的原因之一）。
  patch 只印「要換的那幾行」，便宜、改動範圍看得見、套不上就整包放棄不會半壞。

模型輸出格式（一個或多個區塊；找不到要改的就只印 NOPATCH: 理由）：

<<<<<<< SEARCH
（原始碼裡「一字不差」的連續幾行，要含足夠上下文讓它在檔案裡唯一）
=======
（換成這些行）
>>>>>>> REPLACE
"""
import re

BLOCK_RE = re.compile(
    r"<{7}\s*SEARCH[ \t]*\r?\n(?P<search>.*?)\r?\n={7}[ \t]*\r?\n(?P<replace>.*?)(?:\r?\n)?>{7}\s*REPLACE",
    re.S)


class PatchError(ValueError):
    """patch 套不上（找不到 SEARCH 段／格式壞掉）。呼叫端一律「放棄這次打磨、沿用原版」。"""


def parse(text: str) -> list:
    """把模型輸出解析成 [(search, replace), …]。回空清單＝NOPATCH 或沒有任何區塊。"""
    text = text.replace("\r\n", "\n")
    text = re.sub(r"^```[a-zA-Z]*\s*$", "", text, flags=re.M)   # 順手去掉 code fence 行
    blocks = []
    for m in BLOCK_RE.finditer(text):
        search, replace = m.group("search"), m.group("replace")
        if not search.strip():
            raise PatchError("有一個 SEARCH 段是空的")
        blocks.append((search, replace))
    return blocks


def is_nopatch(text: str) -> bool:
    return bool(re.search(r"^\s*NOPATCH\b", text or "", re.M)) and not BLOCK_RE.search(text or "")


def _norm_lines(s: str) -> list:
    """逐行去尾端空白（模型常把 tab／尾空白抄掉；比對時容忍這種差異）。"""
    return [ln.rstrip() for ln in s.replace("\r\n", "\n").split("\n")]


def _find_normalized(html: str, search: str):
    """精確比對失敗時的退路：用「去尾端空白」逐行比對，找到就回 (起點, 終點) 字元位置。"""
    hay, needle = _norm_lines(html), _norm_lines(search)
    n = len(needle)
    if n == 0:
        return None
    # 先把每行的起始字元位置算出來，命中後才能換回原文的切片
    starts, pos = [], 0
    raw_lines = html.replace("\r\n", "\n").split("\n")
    for ln in raw_lines:
        starts.append(pos)
        pos += len(ln) + 1
    for i in range(len(hay) - n + 1):
        if hay[i:i + n] == needle:
            end_line = i + n - 1
            end = starts[end_line] + len(raw_lines[end_line])
            return starts[i], end
    return None


def _find_exact_lines(html: str, search: str) -> list:
    """精確比對，但只認「整行」命中（起點在行首、終點在行尾），避免半行誤中。回所有 (起, 迄)。"""
    spans, i = [], html.find(search)
    while i >= 0:
        j = i + len(search)
        if (i == 0 or html[i - 1] == "\n") and (j == len(html) or html[j] == "\n"):
            spans.append((i, j))
        i = html.find(search, i + 1)
    return spans


def apply(html: str, blocks: list) -> tuple:
    """依序套用所有區塊，回 (新原始碼, 套用筆數)。任何一塊套不上就 raise PatchError（不做半套）。"""
    html = html.replace("\r\n", "\n")
    applied = 0
    for idx, (search, replace) in enumerate(blocks, 1):
        search_n = search.replace("\r\n", "\n")
        spans = _find_exact_lines(html, search_n)
        if spans:
            if len(spans) > 1:
                print(f"  ⚠️ patch 第 {idx} 塊的 SEARCH 在檔案裡出現 {len(spans)} 次，套用第一個")
            s, e = spans[0]
            html = html[:s] + replace + html[e:]
            applied += 1
            continue
        span = _find_normalized(html, search_n)
        if span is None:
            head = search_n.strip().splitlines()[0][:60] if search_n.strip() else ""
            raise PatchError(f"第 {idx} 塊的 SEARCH 段在原始碼裡找不到（開頭：{head!r}）")
        html = html[:span[0]] + replace + html[span[1]:]
        applied += 1
    return html, applied


def apply_text(html: str, patch_text: str) -> tuple:
    """一步到位：解析模型輸出＋套用。回 (新原始碼或 None, 套用筆數)；None＝NOPATCH。"""
    if is_nopatch(patch_text):
        return None, 0
    blocks = parse(patch_text)
    if not blocks:
        raise PatchError("輸出裡沒有任何 SEARCH/REPLACE 區塊（也不是 NOPATCH）")
    return apply(html, blocks)
