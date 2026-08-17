"""证据层：投标 + 招标两层底稿入 FTS5 索引（KD1）。按项检索组装见 ``evidence_retrieval``。

**为什么单独建模块而不是扩 context_slim**：那里是"招标底稿按 criteria 瘦身"（D8），语义是
*裁剪一份文本*；这里是"两层底稿入索引"，语义是 *建立可检索的证据底座*。两者变更理由不同，
且 context_slim 已 200+ 行，合并后必越 300 线。

设计前提（2026-08-15 实测，见 sprint design）：单次评标注入必须**与投标体量脱钩**。招标层
38,541 字 + 投标层 370,529 字 ≈ 409K token，而 bundled CLI 约 200K token 即一次性硬拒——
分配算法怎么改都不够，只有"规则层常驻 + 证据层按项检索"能脱钩。
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from server.stores import rag_store
from server.tender.evidence_chunks import build_chunks

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
