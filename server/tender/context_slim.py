"""D8 底稿瘦身：按项目 criteria 检索招标文件相关章节，替代全量灌注。

criteria.eligibility_rules[] 对应招标文件的"资格审查"章节（docstructure 语义标签
qualification_review），criteria.items[] 对应"评标办法/评分标准"章节（语义标签
evaluation_method）——两者都是 D6 docstructure._TAG_KEYWORDS 现成的固定标签，criteria
本身在抽取时就是从这两类章节里解析出来的（见 .claude/commands/tender-evaluate.md S1），
用它做检索 query 天然贴合真实定位需求。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from server.ocr.docstructure import build_doc_structure
from server.ocr.rag import index_document, search

_ELIGIBILITY_TAG = "qualification_review"
_EVALUATION_TAG = "evaluation_method"
# 每条 criteria 项检索几个 chunk：给到"整章+相邻子节"的量级，过大会让去重后仍逼近全量。
_CHUNKS_PER_QUERY = 3


def _criteria_queries(criteria: dict[str, Any]) -> list[tuple[str, str, str]]:
    """把 criteria 的 eligibility_rules/items 转成 (query_text, tag, label) 三元组列表。"""
    queries: list[tuple[str, str, str]] = []
    for rule in criteria.get("eligibility_rules") or []:
        text = " ".join(filter(None, [rule.get("check"), rule.get("requirement")])).strip()
        if text:
            queries.append((text, _ELIGIBILITY_TAG, f"资格审查:{rule.get('check', '')}"))
    for item in criteria.get("items") or []:
        text = " ".join(filter(None, [item.get("item"), item.get("category")])).strip()
        if text:
            queries.append((text, _EVALUATION_TAG, f"评分项:{item.get('item', '')}"))
    return queries


def build_slim_tender_context(
    tender_text: str, criteria: dict[str, Any], *, file_name: str
) -> str | None:
    """按 criteria 检索招标文件相关章节，组装精简 context；无法安全精简时返回 None。

    None 的三种触发条件（调用方一律回退全量原文，绝不静默丢项）：
    1. criteria 不含任何可用于检索的 eligibility_rules/items 文本；
    2. tender_text 没有可识别的章节（build_doc_structure 产物 chapters 为空）；
    3. 任一检索项零命中——宁可整份回退全量，不做"部分精简、部分静默缺失"。
    """
    queries = _criteria_queries(criteria)
    if not queries:
        return None

    structure = build_doc_structure(tender_text, file_name=file_name)
    if not structure["chapters"]:
        return None

    conn = sqlite3.connect(":memory:")
    index_document(structure, tender_text, conn=conn)

    collected: dict[str, dict[str, Any]] = {}
    for query_text, tag, _label in queries:
        hits = search(query_text, conn=conn, tag=tag, limit=_CHUNKS_PER_QUERY)
        if not hits:
            conn.close()
            return None
        for hit in hits:
            collected.setdefault(hit["chunk_id"], hit)

    conn.close()
    blocks = [f"{hit['page_anchor']}\n{hit['text']}" for hit in collected.values()]
    return "\n\n".join(blocks)
