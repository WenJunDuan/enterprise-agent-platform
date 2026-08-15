"""证据层的 chunk 成形：章节切分 + 超长二次切分 + 页锚保真（KD2）。

与 ``evidence_index`` 分家的理由是变更理由不同：本模块只回答"**一份底稿怎么切成带页锚的
chunk**"，索引写入与按项检索组装在 ``evidence_index``。S0-B 实测的形态约束都落在这里：

- chunk 字数 min 21 / 中位 212 / p90 3,453 / **max 26,107**，10 个超 8,000 → 二次切分必需；
- ``build_doc_structure`` 对投标能出 60 章节，但 OCR 认不出结构时会退化成单个巨 chunk。

页锚由 chunk 直接带出，证据链的 ``【第N页】`` 因此不靠模型从大段底稿自己数页码。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from server.common.corpus import ARTIFACT_ORIGINAL, parse_page_anchor
from server.ocr.docstructure import build_doc_structure
from server.ocr.rag import index_document
from server.stores import rag_store

logger = logging.getLogger(__name__)

# 单 chunk 字数硬上限。S0-B 实测投标索引 max 26,107 字、10 个超 8,000——不切分的话，一个
# 命中就吃掉整个证据预算，其余项全部饿死。取 4,000 ≈ p90(3,453) 略上浮：既不把常见整章
# 切碎，又保证最坏情况下单项能装下多个 chunk。
MAX_CHUNK_CHARS = 4_000


def _page_at(lines: list[str]) -> int | None:
    """Return the first page number carried by ``lines``' anchors, or ``None``."""
    for line in lines:
        anchor = parse_page_anchor(line)
        if anchor is not None:
            return anchor[0]
    return None


def _slice_chunk(chunk: dict[str, Any], index: int, lines: list[str]) -> dict[str, Any]:
    """Build one split piece, re-deriving its page anchor from its own lines.

    页锚**跟着内容走**：整片沿用原 chunk 的 page_start 会让后半部分的证据挂到更早的页，
    那正是"证据页码对不上"的老毛病。本片自己没有锚行时才回落原 chunk 的起始页。
    """
    own_page = _page_at(lines)
    return {
        **chunk,
        "chunk_id": f"{chunk['chunk_id']}/{index}",
        "page_start": own_page if own_page is not None else chunk.get("page_start"),
        "page_end": own_page if own_page is not None else chunk.get("page_end"),
        "chunk_text": "\n".join(lines),
    }


def split_oversized_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把超过 :data:`MAX_CHUNK_CHARS` 的 chunk 按行切成多片，页锚逐片重算。

    Args:
        chunks: ``rag.index_document`` 形态的 chunk 列表。

    Returns:
        切分后的 chunk 列表；未超限的原样透传（不制造无谓切分）。
    """
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        text = chunk.get("chunk_text") or ""
        if len(text) <= MAX_CHUNK_CHARS:
            out.append(chunk)
            continue
        buffer: list[str] = []
        size = 0
        piece = 0
        for line in text.splitlines():
            # 页锚行本身是切点信号：在换页处断开，切片与页码天然对齐。
            starts_page = parse_page_anchor(line) is not None
            if buffer and (size + len(line) > MAX_CHUNK_CHARS or (starts_page and size > 0)):
                out.append(_slice_chunk(chunk, piece, buffer))
                piece += 1
                buffer, size = [], 0
            buffer.append(line)
            size += len(line) + 1
        if buffer:
            out.append(_slice_chunk(chunk, piece, buffer))
    return out


def build_chunks(text: str, *, file_name: str, tag: str | None) -> list[dict[str, Any]]:
    """把一份底稿切成带页锚的 chunk。

    优先用 ``build_doc_structure`` 的章节结构；**认不出结构时不退化成 0 chunk 或单个巨
    chunk**，而是整份当一个 chunk 交给 :func:`split_oversized_chunks` 按页级 + 定长切开。

    Args:
        text: 底稿全文（可含 ``【第N页】`` 页锚）。
        file_name: 索引内的 file 标识（两层必须不同）。
        tag: 投标侧传固定标签；招标侧传 ``None`` 表示沿用 docstructure 的语义标签。

    Returns:
        chunk 列表；空文本返回空列表。
    """
    if not (text or "").strip():
        return []
    structure = build_doc_structure(text, file_name=file_name)
    chunks: list[dict[str, Any]] = []
    if structure["chapters"]:
        conn = sqlite3.connect(":memory:")
        try:
            index_document(structure, text, conn=conn)
            chunks = [
                dict(row) for row in conn.execute(f"SELECT * FROM {rag_store.SCAN_TABLE_NAME}")
            ]
        except ValueError:
            # structure/body 不匹配（docstructure 与正文标题行对不上）——退回整份切分，
            # 而不是让整层索引失败：没有索引等于该层证据全灭。
            logger.warning("tender_evidence_structure_mismatch", extra={"file": file_name})
            chunks = []
        finally:
            conn.close()
    if not chunks:
        chunks = [
            {
                "chunk_id": f"{file_name}#0",
                "file": file_name,
                "chapter_path": file_name,
                "chapter_title": file_name,
                "tag": tag,
                "page_start": _page_at(text.splitlines()),
                "page_end": None,
                "page_artifact": ARTIFACT_ORIGINAL,
                "chunk_text": text,
            }
        ]
    for chunk in chunks:
        chunk["file"] = file_name
        if tag is not None:
            chunk["tag"] = tag
    return split_oversized_chunks(chunks)
