"""BOQ（已标价工程量清单）感知抽取：把超大工程量清单的关键金额结构化抽成紧凑摘要。

业务背景（R2）：已标价工程量清单（BOQ）动辄数千页（R2024-007 二建 1.05 = 8417 页 / 8M 字符），
`build_extraction_block` 旧逻辑从头截 200k → 投标总价虽在 p2 扉页（头部未截），但**淹没在 ~210 页
密集表行噪音里**（项目编码/工程量/综合单价/特征描述），模型不稳定识别/引用；且 97% 单位工程清单
不可见、200k 噪音挤占上下文。本模块确定性抽取**投标总价 / 各类合计 / Top-N 高价**，注入几 KB
紧凑摘要替代噪音从头截——显式提升 grand total 为结构化字段，省上下文，亦覆盖"总价在尾部"变体。

设计要点（两轮设计审查 critic + codex 后）：
- 金额两档：严格档（带小数/千分逗号，排除 12 位项目编码）；宽松档（仅「投标总价」label 锚定下
  允许纯整数 ≥5 位，治整数总价漏抽）。
- 投标总价**候选打分**（扉页/前5页 + 小写 + 大写校验，减"单位工程/税金"局部小计上下文），非取首个。
- **页锚点独占一行**输出（R1 evidence_resolution `_PAGE_RE` 要求），逐字保留金额（R1 可回查）。
- **page-carry 行距上限**：`draft_render.render_body` 把无页号的 ``tables`` 段追加在 blocks 后 → 该段金额不得
  继承末页页号（codex P1#4），超 carry 行距 → 页 None。
- 仅 native blocks 路径（数字文本层）；扫描件 BOQ（OCR pages 管道表格）超本轮范围 → R3。

纯函数，无模型 / 无网络。
"""

from __future__ import annotations

import logging
import re

from server.common.corpus import ARTIFACT_ORIGINAL, page_anchor_text, parse_page_anchor

logger = logging.getLogger(__name__)

# is_boq 信号
_BOQ_NAME_KEYWORDS = ("工程量清单", "已标价清单", "已标价工程量", "分部分项")
_NATIVE_KINDS = frozenset({"pdf_text", "word", "excel", "text"})

# 金额两档：严格（带小数/千分逗号，排除整数项目编码）；宽松（额外允许 ≥5 位纯整数，仅总价 label 用）
_AMOUNT_STRICT = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{1,2}")
_AMOUNT_LOOSE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{1,2}|\d{5,}")
# 页锚点解析统一走 server.common.corpus（唯一单点，含【转换稿第M页】变体，H2 KD0）
# 大写中文金额（≥4 个大写数字/单位连写即视作金额大写校验行）
_DAXIE_RE = re.compile(r"[壹贰叁肆伍陆柒捌玖零拾佰仟万亿圆元角分整]{4,}")

_BIDTOTAL_KW = "投标总价"
_SUBTOTAL_KW = ("分部分项合计", "单价措施合计", "措施项目", "其他项目", "规费", "税金", "合计", "总计", "价款")
# 投标总价候选打分负向上下文（这些是单位工程局部小计，不是 grand total）
_NEG_CTX = ("单位工程", "税金", "分部分项", "措施", "规费")

# 页锚点携带行距上限：页锚点的页号仅对其后 N 行内有效；超出（如无锚点的 tables 追加尾段）→ 页 None。
_PAGE_CARRY_LINES = 300
# 摘要内邻近行搜索窗口（label 与金额相邻行：同行 / 后 3 / 前 2）。
_NEAR_FORWARD = 3
_NEAR_BACKWARD = 2


def normalize_amount(s: str) -> float:
    """金额字符串 → float（去千分逗号）。"""
    return float(s.replace(",", ""))


def is_boq(name: str, full_body: str, *, kind: str | None = None) -> bool:
    """是否为（数字文本层）BOQ：文件名信号 或 内容表头特征。

    ``kind`` 非 native 类（如 OCR pages 扫描件）→ False（扫描件 BOQ 留 R3，本轮不处理）。
    """
    if kind is not None and kind not in _NATIVE_KINDS:
        return False
    n = name or ""
    if any(k in n for k in _BOQ_NAME_KEYWORDS):
        return True
    body = full_body or ""
    return (
        "项目编码" in body
        and "综合单价" in body
        and ("合价" in body or "金额" in body)
        and ("合计" in body or "分部分项" in body)
    )


def _nonempty_neighbors(lines: list[str], idx: int) -> list[str]:
    """返回 idx 行用于找金额的邻近行序：同行 → 后 _NEAR_FORWARD 非空 → 前 _NEAR_BACKWARD 非空。"""
    seq = [lines[idx]]
    fwd = 0
    j = idx + 1
    while j < len(lines) and fwd < _NEAR_FORWARD:
        if lines[j].strip():
            seq.append(lines[j])
            fwd += 1
        j += 1
    bwd = 0
    j = idx - 1
    while j >= 0 and bwd < _NEAR_BACKWARD:
        if lines[j].strip():
            seq.append(lines[j])
            bwd += 1
        j -= 1
    return seq


def _find_amount_near(lines: list[str], idx: int, *, loose: bool) -> tuple[float, str] | None:
    """在 idx 行的邻近行（同行/后/前）找金额。返回 (值, 原文) 或 None。

    - strict 档：取**首个**带小数/逗号的金额（合计明细相邻行）。
    - loose 档（投标总价）：额外允许 ≥5 位整数，但邻近窗口可能混入序号/编码（reviewer F1）→
      取窗口内**最大**金额（投标总价是大数、序号/页码是小数），避免选错成序号。
    """
    pat = _AMOUNT_LOOSE if loose else _AMOUNT_STRICT
    if loose:
        best: tuple[float, str] | None = None
        for ln in _nonempty_neighbors(lines, idx):
            for m in pat.finditer(ln):
                val = normalize_amount(m.group())
                if best is None or val > best[0]:
                    best = (val, m.group())
        return best
    for ln in _nonempty_neighbors(lines, idx):
        m = pat.search(ln)
        if m:
            return normalize_amount(m.group()), m.group()
    return None


def _find_daxie_near(lines: list[str], idx: int) -> str | None:
    """在 idx 行后若干行找大写金额校验行（叁亿…元玖角柒分）。"""
    j = idx
    seen = 0
    while j < len(lines) and seen < 4:
        if lines[j].strip():
            seen += 1
            m = _DAXIE_RE.search(lines[j])
            if m:
                return m.group()
        j += 1
    return None


def _score_bidtotal(page: int | None, line: str, daxie: str | None, ctx: str) -> int:
    """投标总价候选打分：扉页/前5页 + 小写 + 大写校验为正；局部小计上下文为负。"""
    score = 0
    if page is not None and page <= 5:
        score += 3
    if "小写" in line:
        score += 3
    if daxie:
        score += 2
    if any(k in ctx for k in _NEG_CTX):
        score -= 3
    return score


def _page_label(page: int | None, artifact: str = ARTIFACT_ORIGINAL) -> str:
    """摘要里重放的页锚点行。artifact 随原底稿——转换稿页不得冒充原文档页（H2 KD1）。"""
    return page_anchor_text(page, artifact=artifact) if page is not None else "【页未知】"


def extract_boq_summary(
    name: str,
    full_body: str,
    *,
    top_n: int = 8,
    max_chars: int | None = None,
    subtotal_limit: int = 12,
) -> str | None:
    """从 BOQ 全文（带页锚点）抽关键金额，组装紧凑摘要字符串；抽不到关键金额 / 异常 → None。

    Args:
        name: 文件名（用于摘要头）。
        full_body: ``draft_render.render_body`` 产物（含 ``【第 N 页】`` 锚点 + 可能的无锚点 tables 尾段）。
        top_n: Top-N 高价金额条数。
        max_chars: 摘要长度上限（None → 不限；调用方传 MAX//4）。
        subtotal_limit: 各类合计最多列出条数（其余只报总数）。

    Returns:
        紧凑摘要（页锚点独占行，逐字金额），或 None（回落调用方截断）。
    """
    try:
        lines = full_body.splitlines()
        cur_page: int | None = None
        # 整份 body 属同一文件 → 同一 artifact 坐标系；由首个锚点确定，供摘要重放锚点用。
        body_artifact = ARTIFACT_ORIGINAL
        since = 0

        def anchor_line(page: int | None) -> str:
            return _page_label(page, body_artifact)

        bidtotal_cands: list[tuple[int, int | None, str, str | None, float]] = []
        subtotals: list[tuple[int | None, str, float, str]] = []
        amounts: list[tuple[float, int | None, str]] = []

        for i, raw in enumerate(lines):
            anchor = parse_page_anchor(raw)
            if anchor is not None:
                cur_page, body_artifact = anchor
                since = 0
                continue
            since += 1
            # page-carry：超行距（无锚点 tables 尾段）→ 页号失效，置 None（codex P1#4）
            page = cur_page if since <= _PAGE_CARRY_LINES else None
            s = raw.strip()
            if not s:
                continue

            if _BIDTOTAL_KW in s:
                found = _find_amount_near(lines, i, loose=True)
                if found is not None:
                    amt, amt_str = found
                    daxie = _find_daxie_near(lines, i)
                    ctx = " ".join(lines[max(0, i - 2) : i + 3])
                    score = _score_bidtotal(page, s, daxie, ctx)
                    bidtotal_cands.append((score, page, amt_str, daxie, amt))

            if any(k in s for k in _SUBTOTAL_KW):
                found = _find_amount_near(lines, i, loose=False)
                if found is not None:
                    amt, amt_str = found
                    subtotals.append((page, s[:40], amt, amt_str))

            for m in _AMOUNT_STRICT.finditer(s):
                amounts.append((normalize_amount(m.group()), page, s[:50]))

        if not bidtotal_cands and not subtotals:
            return None  # 抽不到任何关键金额 → 回落截断（不更差）

        # 注意：不以 ``###`` 开头（build_extraction_block 已加 ``### 文件:`` 头，本块是 body，
        # 避免与 R1 _FILE_RE 文件头解析混淆）。
        out: list[str] = [
            (
                f"[本块为 BOQ 结构化摘要] {name} 原文过大（{len(full_body)} 字符），"
                "已按结构抽取关键金额，未全文注入。"
            )
        ]

        chosen_value: float | None = None
        if bidtotal_cands:
            bidtotal_cands.sort(key=lambda c: c[0], reverse=True)
            score, page, amt_str, daxie, amt = bidtotal_cands[0]
            chosen_value = amt
            out.append(anchor_line(page))
            daxie_part = f"  (大写: {daxie})" if daxie else ""
            out.append(f"投标总价: {amt_str}{daxie_part}  [grand total · 候选打分={score}]")
            if len(bidtotal_cands) > 1:
                cand_str = " / ".join(
                    f"{anchor_line(c[1])}={c[2]}" for c in bidtotal_cands[:6]
                )
                out.append(f"投标总价全部候选(供人核): {cand_str}")

        if subtotals:
            subtotals.sort(key=lambda t: t[2], reverse=True)
            out.append(f"各类合计(共 {len(subtotals)} 处，列金额最大 {min(subtotal_limit, len(subtotals))})：")
            for page, label, amt, amt_str in subtotals[:subtotal_limit]:
                out.append(anchor_line(page))
                out.append(f"{label} {amt_str}")

        if amounts:
            seen: set[float] = set()
            if chosen_value is not None:
                seen.add(chosen_value)
            uniq: list[tuple[float, int | None, str]] = []
            for val, page, snip in sorted(amounts, key=lambda t: t[0], reverse=True):
                if val in seen:
                    continue
                seen.add(val)
                uniq.append((val, page, snip))
                if len(uniq) >= top_n:
                    break
            if uniq:
                out.append(f"Top-{len(uniq)} 高价金额(供异常价抽查)：")
                for val, page, snip in uniq:
                    out.append(anchor_line(page))
                    out.append(snip)

        out.append("[完整逐行清单未注入；逐项核验请人工查原文件]")
        summary = "\n".join(out)

        # 摘要长度上限（critic F5）：优先保投标总价段，超限裁减尾部 + 标注。
        if max_chars is not None and len(summary) > max_chars:
            summary = summary[:max_chars].rstrip() + "\n...[BOQ 摘要超长，已裁减；逐项查原文件]"
        return summary
    except Exception:  # noqa: BLE001 - 抽取失败绝不拖垮底稿组装，回落截断
        logger.warning("extract_boq_summary failed for %s; falling back to truncation", name, exc_info=True)
        return None
