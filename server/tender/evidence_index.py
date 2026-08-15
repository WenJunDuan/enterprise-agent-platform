"""证据层：投标 + 招标入索引，按 criteria 逐项检索组装（KD1/KD2）。

**为什么单独建模块而不是扩 context_slim**：那里是"招标底稿按 criteria 瘦身"（D8），语义是
*裁剪一份文本*；这里是"按项取证据"，语义是 *从两层索引里检索并组装*。两者变更理由不同，
且 context_slim 已 200+ 行，合并后必越 300 线。

设计前提（2026-08-15 实测，见 sprint design）：单次评标注入必须**与投标体量脱钩**。招标层
38,541 字 + 投标层 370,529 字 ≈ 409K token，而 bundled CLI 约 200K token 即一次性硬拒——
分配算法怎么改都不够，只有"规则层常驻 + 证据层按项检索"能脱钩。

检索**在会话前由服务端机械完成**（KD3b），不是 agentic 工具：会话中检索会把轮次与注入量
重新变成不可控变量，而 2026-08-14 事故正是"反复 Read → error_max_turns"。
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from server.ocr.rag import search
from server.stores import rag_store
from server.tender.evidence_chunks import MAX_CHUNK_CHARS, build_chunks
from server.tender.injection_budget import InjectionPlan, estimate_tokens, plan_injection

logger = logging.getLogger(__name__)

# 索引里两层各自的 file 标识。必须不同——``index_document`` 按 file 先删后插，同名会让
# 后建的那层把先建的清掉。
TENDER_FILE = "__tender__"
BID_FILE = "__bid__"

# 招标侧 chunk 的 tag 由 docstructure 给出（qualification_review / evaluation_method 等）；
# 投标侧统一 bid——投标文件没有"评标办法"这类语义章节，按语义标签过滤会把它全过滤掉。
BID_TAG = "bid"


@dataclass(frozen=True)
class IndexStats:
    """一次索引构建的产出规模（供可见性与耗时观测）。"""

    tender_chunks: int
    bid_chunks: int

    @property
    def total_chunks(self) -> int:
        return self.tender_chunks + self.bid_chunks


def build_evidence_index(
    conn: sqlite3.Connection,
    *,
    tender_text: str,
    bid_text: str,
    project_id: str,
) -> IndexStats:
    """把招标层与投标层一起写进证据索引（AC4）。

    ``context_slim`` 此前只索引招标——**投标从未入索引**，这是"证据层按项检索"完全无法
    工作的根本缺口。两层用不同 file 标识，故重建其中一层不会清掉另一层；同一层重复构建
    幂等（先删后插）。

    Args:
        conn: 索引连接（``:memory:``，现建现用）。
        tender_text: 招标底稿全文。
        bid_text: **当前被评标这一家**的投标底稿全文。
        project_id: 仅用于日志定位。

    Returns:
        :class:`IndexStats`。
    """
    tender_chunks = build_chunks(tender_text, file_name=TENDER_FILE, tag=None)
    bid_chunks = build_chunks(bid_text, file_name=BID_FILE, tag=BID_TAG)
    for file_name, chunks in ((TENDER_FILE, tender_chunks), (BID_FILE, bid_chunks)):
        rag_store.delete_rows_for_file(conn, file_name)
        if chunks:
            rag_store.insert_rows(conn, chunks)
    conn.commit()
    stats = IndexStats(tender_chunks=len(tender_chunks), bid_chunks=len(bid_chunks))
    logger.info(
        "tender_evidence_indexed",
        extra={
            "project_id": project_id,
            "tender_chunks": stats.tender_chunks,
            "bid_chunks": stats.bid_chunks,
        },
    )
    return stats


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


def _search_item(
    queries: list[str], *, conn: sqlite3.Connection, limit: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run one item's queries and return ``(hits, queries_actually_used)``.

    按顺序试：项名 → 类别/basis。命中即停——第一个查询串通常最贴题，继续试只会稀释相关性。
    ``basis`` 指向招标章节的项（典型："逐条响应第 X 章技术参数"）因此能带出招标侧 chunk：
    criteria 只有项名和满分，装不下几十页技术参数表（KD1 F5）。
    """
    used: list[str] = []
    for query in queries:
        used.append(query)
        hits = search(query, conn=conn, tag=None, limit=limit)
        if hits:
            return hits, used
    return [], used


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
    # 每项取几个 chunk：由该项的 token 额度除以单 chunk 上限得出，至少 1 个。
    per_item_chunks = max(1, plan.per_item_tokens // MAX_CHUNK_CHARS)

    blocks: list[EvidenceBlock] = []
    unresolved: list[UnresolvedItem] = []
    seen: set[str] = set()
    used_tokens = 0
    for name, queries in items:
        hits, tried = _search_item(queries, conn=conn, limit=per_item_chunks)
        if not hits:
            unresolved.append(UnresolvedItem(item=name, queries=tried))
            continue
        for hit in hits:
            # 跨项去重：多个评分项常命中同一 chunk（如同一张报价表），
            # 组装期按 chunk_id 去重后再计账（KD3）。
            if hit["chunk_id"] in seen:
                continue
            cost = estimate_tokens(hit["text"])
            if used_tokens + cost > plan.evidence_tokens:
                # 额度用尽即停：宁可后面的项走 evidence_unresolved（可见、可人工补），
                # 也不越预算——越预算的代价是整单一次性硬失败。
                break
            seen.add(hit["chunk_id"])
            used_tokens += cost
            blocks.append(
                EvidenceBlock(
                    chunk_id=hit["chunk_id"],
                    scope=_scope_of(hit),
                    chapter_path=hit["chapter_path"],
                    page_anchor=hit["page_anchor"],
                    text=hit["text"],
                )
            )
    return EvidenceResult(
        blocks=blocks, unresolved=unresolved, plan=plan, total_tokens=used_tokens
    )
