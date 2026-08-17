"""证据层的 chunk 成形：章节切分 + 超长二次切分 + 页锚保真（KD2）。

与 ``evidence_index`` 分家的理由是变更理由不同：本模块只回答"**一份底稿怎么切成带页锚的
chunk**"，索引写入与按项检索组装在 ``evidence_index``。S0-B 实测的形态约束都落在这里：

- chunk 字数 min 21 / 中位 212 / p90 3,453 / **max 26,107**，10 个超 8,000 → 二次切分必需；
- ``build_doc_structure`` 对投标能出 60 章节，但 OCR 认不出结构时会退化成单个巨 chunk。

页锚由 chunk 直接带出，证据链的 ``【第N页】`` 因此不靠模型从大段底稿自己数页码。
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

from server.common.corpus import ARTIFACT_ORIGINAL, parse_page_anchor
from server.ocr.docstructure import build_doc_structure, chapter_heading, normalize_body
from server.ocr.rag import StructureBodyMismatchError, index_document
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


# 十进制编号小节标题（``4.8.类似业绩`` / ``4.10.1.技术部分产品常规参数正负偏离表``）。
# ``docstructure.chapter_heading`` 只认「第X章」「一、」「（一）」三种形态，而投标文件的评分
# 应答几乎清一色用十进制编号——2026-08-17 实测因此让「十、雷击事故应急预案」一路吞到 p349，
# 4.7~4.10 全挂在它名下。**刻意只在本模块局部识别**：加进全局识别器会同时改变招标侧章节树、
# ``toc_line_indexes`` 的连续同级标题判定与 structure/body 行数不变量（高爆炸半径）。
#
# 编号部分**必须含小数点且以点收尾**：宁可漏认「4.7 企业综合实力」这种无尾点写法，也不能把
# 「21.5 寸液晶显示屏」「1 某直播间建设项目」这类量值与表格行认成标题——误认的代价是出处被
# 改错、且续接会在正文中途当成新小节而截断，比漏认严重。其余约束同样按标题形态收紧：无句末
# 标点（正文句子）、无制表符（表格行）、标题正文不以数字开头、整体够短。
_DECIMAL_HEADING_RE = re.compile(
    r"^\s*(?P<number>\d{1,2}(?:\.\d{1,3}){1,4})\.\s*(?P<title>[^\s\d][^\t。；;]{0,38})\s*$"
)


def slice_heading(lines: list[str]) -> str | None:
    """Return the section heading a split piece **starts with**, or ``None``.

    只看首个正文行（页锚行与空行跳过）：切片中段冒出来的标题属于下一节，用它当整片的标签
    会把前半段的出处也改错；而"本片是否另起一节"正是续接边界判定的依据。

    Args:
        lines: 切片自身的行。

    Returns:
        标题原文；首个正文行不是标题时返回 ``None``。
    """
    for line in lines:
        if not line.strip() or parse_page_anchor(line) is not None:
            continue
        formal = chapter_heading(line)
        if formal is not None:
            return formal[0]
        return line.strip() if _DECIMAL_HEADING_RE.match(line) else None
    return None


def heading_rank(heading: str) -> tuple[str, int] | None:
    """Return a heading's ``(编号族, 深度)``, or ``None`` when it isn't a heading.

    两个编号族**不可通约**，故族名是返回值的一部分：真实标书里 ``4.10.技术参数指标`` 的偏离表
    正文用 ``一、核心影像参数`` 分栏，若把「一、」的 level 2 与「4.10」的深度 2 放在一起比大小，
    续接会在偏离表第一行当场止步——那正好回到"25 分的项只有表头"这个要修的缺陷。
    """
    formal = chapter_heading(heading)
    if formal is not None:
        return ("formal", formal[1])
    decimal = _DECIMAL_HEADING_RE.match(heading)
    if decimal is not None:
        return ("decimal", decimal.group("number").count(".") + 1)
    return None


# 除页锚外还有没有文字。``[^\W\d_]`` = 字母/汉字，排除数字、下划线、标点与空白。
_TEXT_CHAR_RE = re.compile(r"[^\W\d_]")


def has_substance(text: str) -> bool:
    """Return whether ``text`` carries any real content besides its page anchors.

    实测：真实投标 p319–344 是合同扫描件，PDF 文本层只剩一个页码（整块 14 字），而每块进注入
    还要带一行出处抬头——**抬头比内容还长**。把它们当证据注入等于用噪音挤掉真证据。

    判据不设字数阈值（阈值要随标书体例调）：去掉页锚行后**一个文字都没有**即无实质内容。
    """
    for line in text.splitlines():
        if parse_page_anchor(line) is not None:
            continue
        if _TEXT_CHAR_RE.search(line):
            return True
    return False


def _relabel(chapter_path: str, heading: str) -> str:
    """Replace the trailing element of ``chapter_path`` with ``heading``."""
    ancestors = chapter_path.split(" > ")[:-1]
    return " > ".join([*ancestors, heading])


def _slice_chunk(chunk: dict[str, Any], index: int, lines: list[str]) -> dict[str, Any]:
    """Build one split piece, re-deriving its page anchor **and label** from its own lines.

    页锚**跟着内容走**：整片沿用原 chunk 的 page_start 会让后半部分的证据挂到更早的页，
    那正是"证据页码对不上"的老毛病。本片自己没有锚行时才回落原 chunk 的起始页。

    出处标签同理（KD6-a）：切片首个标题行是**直接观测到的事实**，而继承来的祖先链是结构
    解析的**推断**。推断失效时（投标用十进制编号 → 上级章节一路吞到几十页后）不该让它继续
    冒充出处——实测渲染出的是 `【…雷击事故应急预案】【第317页】` 而正文是业绩表，内容对、
    出处错，回查闸失去依据。识别不到自己的标题时才沿用继承路径。
    """
    own_page = _page_at(lines)
    heading = slice_heading(lines)
    chapter_path = chunk["chapter_path"]
    return {
        **chunk,
        "chunk_id": f"{chunk['chunk_id']}/{index}",
        "chapter_path": _relabel(chapter_path, heading) if heading else chapter_path,
        "chapter_title": heading or chunk["chapter_title"],
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


def dedupe_in_document_order(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一段正文只留一块，并按页码排成文档顺序（KD6-b）。

    ``rag._chunk_spans`` 对**每个树节点**各出一块，而父节点的 span 含其子孙正文；切片又在
    页锚处重新对齐，于是父与子从第二页起产出**逐字相同、仅 chunk_id 不同**的块。实测真实
    投标 645 chunk / 不同正文仅 509 / 冗余 61,790 字 = 20%。组装期按 ``chunk_id`` 去重看不
    见这种重复，放开取量后它会直接吃掉扩出来的额度。

    重复时保留 ``chapter_path`` 更具体（更长）的那个——父节点的副本因此让位给子节点的精确
    标签，与 :func:`_slice_chunk` 的重推同向。

    排序让 **rowid 等于文档顺序**：``scan_rows`` 一直按 rowid 取"文档顺序"，但 DFS 先序 +
    父子交错会让 rowid 与页码脱节，而按项检索的续接正依赖这条。无页锚的块排在后面并保持
    原有相对位置（稳定排序），整份无页锚时顺序不变。

    Args:
        chunks: 切分后的 chunk 列表。

    Returns:
        去重且按文档顺序排好的 chunk 列表。
    """
    best: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        previous = best.get(chunk["chunk_text"])
        if previous is None or len(chunk["chapter_path"]) > len(previous["chapter_path"]):
            best[chunk["chunk_text"]] = chunk
    return sorted(
        best.values(), key=lambda chunk: (chunk["page_start"] is None, chunk["page_start"] or 0)
    )


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
    # structure 与 body 必须同源：build_doc_structure 内部会拆开粘连的章标题（行数会变），
    # 而 index_document 要求 body 就是构建 structure 时那份文本，否则章节数对不上直接退化。
    text = normalize_body(text)
    structure = build_doc_structure(text, file_name=file_name)
    chunks: list[dict[str, Any]] = []
    if structure["chapters"]:
        conn = sqlite3.connect(":memory:")
        # row_factory 必须显式设置：默认返回 tuple，``dict(tuple)`` 会抛 ValueError，而下面
        # 的 except ValueError 会把它误当成"structure/body 不匹配"，于是**每一份文档都静默
        # 退化成整份单 chunk**——章节级切分形同虚设，且只在日志里留一行 warning。
        conn.row_factory = sqlite3.Row
        try:
            index_document(structure, text, conn=conn)
            chunks = [
                dict(row) for row in conn.execute(f"SELECT * FROM {rag_store.SCAN_TABLE_NAME}")
            ]
        except StructureBodyMismatchError:
            # 只捕这一种（F6）：docstructure 与正文标题行对不上时退回整份切分，而不是让整层
            # 索引失败（没有索引等于该层证据全灭）。**其余 ValueError 一律上抛**——旧的
            # `except ValueError` 罩住 index_document + dict(row) 全段，`dict(tuple)` 那次
            # 就被误当成"结构不匹配"，害得每一份文档都静默退化成整份单 chunk。
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
    return dedupe_in_document_order(split_oversized_chunks(chunks))
