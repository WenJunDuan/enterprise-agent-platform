"""命中块之后**续接到哪里为止**：命中块或额度先到者收口，两者都没到就走完了文档时退回
排版边界（KD6-c/S7/pass3-F2）。

从 ``evidence_retrieval`` 拆出来的理由与 KD6-d 那次同款：变更理由不同，且合在一处已越
coding-standards P0 的 300 行硬线。那边回答"给定 criteria 怎么取出该注入哪些段落"（查询串 /
每项额度 / 跨项去重），这里只回答一个问题——"从命中块往后走，走到哪停"。这个问题自 S5 起
已被改写两次半（S5 排版边界 → S7 hit-stop + 排版兜底 → pass3 把"额度用尽"归位成终点），
是独立的变更轴。

为什么需要续接：评分项名往往只出现在**小节标题**里（``4.10.技术参数指标``），偏离表行 /
业绩表 / 方案正文都不含该词——2026-08-17 实测该项全文字面命中仅 2 块且互为重复，25 分的项
因此只拿到 221 字的标题加表头。**加大检索 limit 对这种形态一定无效**，只有沿文档顺序续接
才取得到正文。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from server.ocr.rag import following
from server.tender.evidence_chunks import has_substance, heading_rank, slice_heading
from server.tender.injection_budget import estimate_tokens

# 一次向索引取多少续接块。**纯取数批量**（取不满就再取一批），不是语义阈值——真正的收口
# 是每项 token 额度。
_CONTINUATION_BATCH = 16


def _walk_following(
    hit: dict[str, Any], *, conn: sqlite3.Connection, budget: int, stop_ids: set[str]
) -> tuple[list[dict[str, Any]], bool]:
    """Collect the chunks after ``hit``; returns ``(块, 续接是否已有终点)``。

    终点有两种，都算"有"：撞上另一项的命中块（hit-stop 本义），或**前瞻额度用尽**——额度
    就是本项装得下的全部，走到额度即已收口，再往后有什么与本项无关。pass3/F2 修的正是后者
    被当成"没找到终点"：已收集的正文整批交给排版兜底，而兜底在标题认不出时（AC14 语料的
    前提）返回空 → 该项只剩一个标题块，且既不进 ``unresolved`` 也不进 ``truncated``。实测
    该项注入量 4,825 → 2,018 token，而生产口径 per_item≈6.6K、相邻命中块间隔通常更大，
    故这条路径是常态不是极端。

    ``False`` 只留给一种形态：**没耗尽额度就走完了整份文档**（末项之后 / 文档尾），那时
    确实一个终点也看不见，边界交给 :func:`_bounded_by_layout`。

    无实质内容的块**跳过但继续往后走**（合同扫描件那 26 页只剩页码，跳过才取得到后面的
    4.8.2/4.8.3）。``budget`` 只作**前瞻上界**（决定往后看多远），真正的收口在调用方：被跨项
    去重跳过的块在这里仍计入前瞻，故极端情况下会少看几块——宁可少取，不可越预算。
    """
    picked: list[dict[str, Any]] = []
    used = estimate_tokens(hit["text"])
    cursor = hit["chunk_id"]
    while used < budget:
        batch = following(cursor, conn=conn, limit=_CONTINUATION_BATCH)
        if not batch:
            return picked, False
        for row in batch:
            if row["chunk_id"] in stop_ids:
                return picked, True
            if not has_substance(row["text"]):
                continue
            picked.append(row)
            used += estimate_tokens(row["text"])
            if used >= budget:
                return picked, True
        cursor = batch[-1]["chunk_id"]
    # 命中块自身就已吃满额度：同样是"额度收口"，且此时一块都没续接到。
    return picked, True


def _bounded_by_layout(hit: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """走完文档也没碰到任何终点时的兜底：按排版止步（S5 的两条原边界）。

    **没有终点的续接会把注入量重新绑回投标体量**——同一招标下 40 页 / 400 页两份投标，前者
    命中块后面没东西可吃、后者一路吃到文档尾，AC5 判据句「差异 ≤20%」当场失守（实测：去掉
    本兜底后「无关正文不该整份注入」三条守卫同时转红）。故走到文档尾仍无终点时退回 S5：
    命中块自身不是可识别小节标题就完全不续接（匹配到的内容就在本块里，"后面还有本节正文"
    这个前提不成立），否则续到同族同级的下一小节为止。

    调用面**只剩这一种形态**（pass3/F2）：额度用尽本身就是终点，那条路不再进来——此前它
    也走兜底，于是"标题认不出"时把已收集的正文整批丢掉，等于把 AC14 修复的适用范围缩到
    "下一个命中块恰好在额度内"的小语料。

    同族才比深度：更深的是子节（``4.8.1`` 之于 ``4.8``，要跟着来），同深或更浅的是下一个
    评分项的小节（``4.9`` 之于 ``4.8``，必须止步）。跨族不可通约——``一、`` 与 ``4.10`` 硬比
    会让偏离表正文在第一行就被截断，那正好退回"25 分的项只有表头"。
    """
    boundary = heading_rank(slice_heading(hit["text"].splitlines()) or "")
    if boundary is None:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        rank = heading_rank(slice_heading(row["text"].splitlines()) or "")
        if rank is not None and rank[0] == boundary[0] and rank[1] <= boundary[1]:
            break
        out.append(row)
    return out


def continuation(
    hit: dict[str, Any], *, conn: sqlite3.Connection, budget: int, stop_ids: set[str]
) -> list[dict[str, Any]]:
    """Return the text that follows ``hit`` up to the next chunk hit by any item (hit-stop).

    终点优先取 ``stop_ids``（本次检索**全项命中块的并集**）：各项的命中点天然把文档分了段，
    用它当边界对编号排版**零假设**。S5 原本只按"同族同级的下一小节"止步，而投标里 ``(一)``
    ``1)`` 这类编号两个识别器都不认，认不出时续接**静默不发生**——证据从整节缩成一个标题块，
    既不进 ``unresolved`` 也不进 ``truncated``（S7/AC14）。

    命中块够不着时**额度就是终点**：走到额度即收口并保留已收集的正文（pass3/F2）。生产口径
    per_item≈6.6K token 而相邻命中块间隔通常更大，这条路径是常态——把它当成"没有终点"再走
    排版兜底，等于让 AC14 那条修复只在小语料成立。

    Args:
        hit: 命中块（``rag.search`` 形态）。
        conn: 证据索引连接。
        budget: 本项的 token 额度，同时是前瞻上界与终点之一。
        stop_ids: 本次检索全部命中块的 chunk_id。

    Returns:
        跟在 ``hit`` 之后、仍属于该项的块；两种终点都没碰到就走完了文档时按排版边界收口
        （理由见 :func:`_bounded_by_layout`）。本函数只管"取到哪"，"装不装得下"仍由
        ``_assemble_item`` 按每项额度与全局余量收口，故账目闭式不变。
    """
    picked, bounded = _walk_following(hit, conn=conn, budget=budget, stop_ids=stop_ids)
    return picked if bounded else _bounded_by_layout(hit, picked)
