"""证据层的按项检索与组装：查询构造 → 命中 → 章节内续接 → 受闭式账目约束地装配（KD1/KD2）。

与 ``evidence_index`` 分家的理由是变更理由不同：那里回答"**两层底稿怎么进索引**"（写入、
幂等、两层 file 标识），这里回答"**给定 criteria 怎么取出该注入哪些段落**"（查询串、续接
边界、每项额度）。2026-08-17 补入续接后本半边继续变厚，合在一处已越 300 行硬线。

检索**在会话前由服务端机械完成**（KD3b），不是 agentic 工具：会话中检索会把轮次与注入量
重新变成不可控变量，而 2026-08-14 事故正是"反复 Read → error_max_turns"。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from server.ocr.rag import OVERLAP_MIN_CHARS, following, search, search_overlap
from server.tender.evidence_chunks import has_substance, heading_rank, slice_heading
from server.tender.evidence_index import BID_FILE, TENDER_FILE
from server.tender.injection_budget import InjectionPlan, estimate_tokens, plan_injection


@dataclass(frozen=True)
class EvidenceBlock:
    """一段注入给模型的证据（去重后的单个 chunk）。"""

    chunk_id: str
    scope: str
    chapter_path: str
    page_anchor: str
    text: str

    def render(self) -> str:
        """Render this block for prompt injection, keeping provenance inline."""
        origin = "招标文件" if self.scope == "tender" else "投标文件"
        return f"【{origin}·{self.chapter_path}】{self.page_anchor}\n{self.text}"


@dataclass(frozen=True)
class UnresolvedItem:
    """某评分项零命中的记录——**绝不判 0**，交上层标 ``evidence_unresolved``。"""

    item: str
    queries: list[str]
    hit_count: int = 0


@dataclass
class EvidenceResult:
    """一次按项检索的完整产出。"""

    blocks: list[EvidenceBlock] = field(default_factory=list)
    unresolved: list[UnresolvedItem] = field(default_factory=list)
    # 有命中、却因证据额度先被前面的项吃光而一个块都没进注入的项（F5）。与 ``unresolved``
    # 是两回事：那是"底稿里真没有"，这是"有但没装下"，处置动作也不同（补预算 vs 人工调阅）。
    truncated: list[str] = field(default_factory=list)
    plan: InjectionPlan | None = None
    total_tokens: int = 0

    def render(self) -> str:
        """Render all evidence blocks in retrieval order."""
        return "\n\n".join(block.render() for block in self.blocks)


def _item_queries(criteria: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """把 criteria 转成 ``(项名, [查询串...])``。

    查询串只用 criteria 里**本来就有的文本**（项名 / 类别 / 检查项 / 要求）——不做任何
    词缀扩展。S0-B 已证伪那条路线：实测仅 62%，且靠猜具体标书的措辞，换一份标书即失效。
    """
    out: list[tuple[str, list[str]]] = []
    for rule in criteria.get("eligibility_rules") or []:
        check = (rule.get("check") or "").strip()
        if check:
            queries = [check]
            requirement = (rule.get("requirement") or "").strip()
            if requirement:
                queries.append(requirement)
            out.append((f"资格审查:{check}", queries))
    for item in criteria.get("items") or []:
        name = (item.get("item") or "").strip()
        if not name:
            continue
        queries = [name]
        for extra in (item.get("category"), item.get("basis")):
            text = (extra or "").strip()
            if text:
                queries.append(text)
        out.append((name, queries))
    return out


def _scope_of(row: dict[str, Any]) -> str:
    return "tender" if row.get("file") == TENDER_FILE else "bid"


# 检索的层顺序：**投标层优先**（2026-08-17 第六轮实测的抢位缺陷）。招标评分表本身字面含
# 全部项名，且比投标应答短得多，BM25 的长度归一因此稳定把它排在投标块前面——实测 `类似业绩`
# 的首块变成招标「第四章 评审方法和程序」、注入从 755 字掉到 248 字。评标判的是**投标应答**，
# 招标规定已由 criteria 注入过一次，再占一次证据额度是净损失（模型据招标原文给投标打分）。
#
# 招标层不是被关掉，而是退到兜底：投标层该轮零命中才轮到它。``basis`` 指向招标章节的项
# （KD1 F5，典型"逐条响应第 X 章技术参数"）正落在这个形态里——那串文字在投标底稿里根本不
# 存在，故仍照旧带出招标原文。判据用"投标层有没有命中"而不是去认 basis 的措辞：认措辞要引入
# 对招标文件写法的新假设，换一份标书即失效（S0-B 已证伪同类路线）。
_LAYERS: tuple[tuple[str, str], ...] = ((BID_FILE, ""), (TENDER_FILE, "（招标层）"))


def _search_item(
    queries: list[str], *, conn: sqlite3.Connection, limit: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run one item's queries bid-layer-first and return ``(hits, queries_actually_used)``.

    **两轮 × 两层**。轮次（KD7）：第一轮按整串精确短语，第一轮全部零命中才退到"共享连续原文"
    （:func:`~server.ocr.rag.search_overlap`）——实测形态是招标细则与投标应答标题共享连续 11 字、
    却互不包含整串，那一项值 15 分。两轮顺序不可颠倒：回退的相关度门槛更低。

    层内按 :data:`_LAYERS` 顺序（投标层 → 招标层，理由见该常量），层内再顺序试查询串：
    项名 → 类别/basis，命中即停——第一个查询串通常最贴题，继续试只会稀释相关性。

    Returns:
        ``queries_actually_used`` 把每次尝试**分别留痕**（招标层带 ``招标层`` 标记、回退带
        ``部分重合`` 标记），否则用户看到"检索过这些词"却分不清证据是从哪一层、哪一轮来的（AC2）。
    """
    used: list[str] = []
    rounds = (("", search), (f"（{OVERLAP_MIN_CHARS}字部分重合）", search_overlap))
    for round_label, run in rounds:
        for layer_file, layer_label in _LAYERS:
            for query in queries:
                used.append(f"{query}{round_label}{layer_label}")
                hits = run(query, conn=conn, limit=limit, file=layer_file)
                if hits:
                    return hits, used
    return [], used


# 一次向索引取多少续接块。**纯取数批量**（取不满就再取一批），不是语义阈值——真正的收口
# 是每项 token 额度。
_CONTINUATION_BATCH = 16


def _starts_sibling_section(text: str, boundary: tuple[str, int]) -> bool:
    """Return whether ``text`` opens a section that ends the hit's own section.

    只在**同一编号族**内比深度：深度更深的是子节（``4.8.1`` 之于 ``4.8``，要跟着来），
    同深或更浅的是下一个评分项的小节（``4.9`` 之于 ``4.8``，必须止步）。跨族一律不止步——
    ``一、`` 与 ``4.10`` 的层级不可通约，硬比会让偏离表正文在第一行就被截断。
    """
    rank = heading_rank(slice_heading(text.splitlines()) or "")
    return rank is not None and rank[0] == boundary[0] and rank[1] <= boundary[1]


def _continuation(
    hit: dict[str, Any], *, conn: sqlite3.Connection, budget: int
) -> Iterator[dict[str, Any]]:
    """Yield the text that follows ``hit`` while it still belongs to the hit's own section.

    评分项名往往只出现在**小节标题**里（``4.10.技术参数指标``），偏离表行 / 业绩表 / 方案
    正文都不含该词——2026-08-17 实测该项全文字面命中仅 2 块且互为重复，25 分的项因此只拿到
    221 字的标题加表头。**加大检索 limit 对这种形态一定无效**，只有沿文档顺序续接才取得到正文。

    三条边界都由实测逼出来：命中块自身不是小节标题时不续接（否则没有终点，实测一路吃进与
    任何评分项都无关的附件正文）；止于同族同级的下一小节（否则「企业综合实力」吃进「类似
    业绩」整节 39 块，在错误的小节里给分比证据少更糟）；无实质内容的块**跳过但继续往后走**
    （合同扫描件那 26 页只剩页码，跳过才取得到后面的 4.8.2/4.8.3）。

    ``budget`` 只作**前瞻上界**（决定往后看多远），真正的收口在调用方：被跨项去重跳过的块
    在这里仍计入前瞻，故极端情况下会少看几块——宁可少取，不可越预算。
    """
    boundary = heading_rank(slice_heading(hit["text"].splitlines()) or "")
    if boundary is None:
        return
    used = estimate_tokens(hit["text"])
    cursor = hit["chunk_id"]
    while used < budget:
        batch = following(cursor, conn=conn, limit=_CONTINUATION_BATCH)
        if not batch:
            return
        for row in batch:
            if _starts_sibling_section(row["text"], boundary):
                return
            if not has_substance(row["text"]):
                continue
            yield row
            used += estimate_tokens(row["text"])
            if used >= budget:
                return
        cursor = batch[-1]["chunk_id"]


def _item_evidence(
    hits: list[dict[str, Any]], *, conn: sqlite3.Connection, budget: int
) -> Iterator[dict[str, Any]]:
    """Yield one item's evidence in document order: each hit, then its section's remainder."""
    for hit in hits:
        yield hit
        yield from _continuation(hit, conn=conn, budget=budget)


def _assemble_item(
    hits: list[dict[str, Any]],
    *,
    conn: sqlite3.Connection,
    plan: InjectionPlan,
    seen: set[str],
    remaining_tokens: int,
) -> tuple[list[EvidenceBlock], int, bool]:
    """Assemble one item's blocks; returns ``(blocks, 本项耗用 token, 证据是否在场)``.

    ``seen`` **就地更新**（跨项去重的账本），故本函数按调用顺序产生副作用。

    Returns:
        第三个元素为 ``False`` 表示该项有命中却一块都没进注入 → 上层记 ``truncated``。
    """
    blocks: list[EvidenceBlock] = []
    item_tokens = 0
    has_evidence = False
    for hit in _item_evidence(hits, conn=conn, budget=plan.per_item_tokens):
        # 跨项去重：多个评分项常命中同一 chunk（如同一张报价表），组装期按 chunk_id 去重后
        # 再计账（KD3）。被去重掉的块仍在注入块里，对本项而言证据是在场的，故不算被饿死。
        if hit["chunk_id"] in seen:
            has_evidence = True
            continue
        cost = estimate_tokens(hit["text"])
        # 每项额度只约束**续接**：首块仍只受全局账目管，否则项数一多（per_item 变小）会出现
        # "全局有额度、本项却一块都装不下"的新式饿死。
        if item_tokens and item_tokens + cost > plan.per_item_tokens:
            break
        # 额度用尽即停：不越预算——越预算的代价是整单一次性硬失败。但**必须留痕**（F5）：
        # 此前这里直接 break，排序靠后的项有证据却既不出块也不进 unresolved，用户看到的是
        # 一份"证据齐全"的注入块。
        if item_tokens + cost > remaining_tokens:
            break
        seen.add(hit["chunk_id"])
        item_tokens += cost
        has_evidence = True
        blocks.append(
            EvidenceBlock(
                chunk_id=hit["chunk_id"],
                scope=_scope_of(hit),
                chapter_path=hit["chapter_path"],
                page_anchor=hit["page_anchor"],
                text=hit["text"],
            )
        )
    return blocks, item_tokens, has_evidence


def retrieve_evidence(
    criteria: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    query_count_hint: int | None = None,
) -> EvidenceResult:
    """按 criteria 逐项检索证据，跨项去重后受闭式账目约束地组装（KD1/KD2/AC5）。

    Args:
        criteria: 本次评标的项目规则。
        conn: 已建好的证据索引连接。
        query_count_hint: 预算按几项算；``None`` 表示按 criteria 实际项数。

    Returns:
        :class:`EvidenceResult`；``unresolved`` 里的项**不得判 0**，由上层标
        ``evidence_unresolved`` 并显示实际用过的查询串（AC2/AC7）。
    """
    items = _item_queries(criteria)
    if not items:
        return EvidenceResult()

    plan = plan_injection(criteria=criteria, query_count=query_count_hint or len(items))
    result = EvidenceResult(plan=plan)
    seen: set[str] = set()
    for name, queries in items:
        # 每项取几个 chunk：只在 InjectionPlan 里推导一次（P2/DRY）——此前这里与
        # ``chunks_per_query_budget`` 各推一遍同一个概念，还用了不同除数。
        hits, tried = _search_item(queries, conn=conn, limit=plan.chunks_per_item)
        if not hits:
            result.unresolved.append(UnresolvedItem(item=name, queries=tried))
            continue
        blocks, item_tokens, has_evidence = _assemble_item(
            hits,
            conn=conn,
            plan=plan,
            seen=seen,
            remaining_tokens=plan.evidence_tokens - result.total_tokens,
        )
        result.blocks.extend(blocks)
        result.total_tokens += item_tokens
        if not has_evidence:
            result.truncated.append(name)
    return result
