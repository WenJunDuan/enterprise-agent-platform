"""底稿渲染：结构化识别产物 → 带页锚点的内联文本块（H2 page-provenance KD1/KD2/KD4）。

从 ``server.ocr.pipeline`` 拆出：pipeline 是"目录→分类→直读/OCR"的编排入口，而"页号属于哪个
artifact 坐标系、表格挂在哪一页、超长怎么按锚切"是自成一档的渲染规则；且 pipeline 基线 791 行
已越 SRP 300 线，本 sprint 的渲染增量不得再压上去。

页溯源核心不变量（KD1）：
- ``original``（pdf 直读 / 图片 / 逐页渲染）：页号 = 用户可直接回查的原文档页号 → ``【第 N 页】``。
- ``converted``（Office→PDF 转换稿）：LibreOffice 分页 ≠ Word 分页，原文档页号**不可知** →
  ``【转换稿第 M 页】``，绝不冒充原文档页。

纯函数，无 IO / 无模型调用。
"""

from __future__ import annotations

import os

from server.common.corpus import (
    ARTIFACT_CONVERTED,
    ARTIFACT_ORIGINAL,
    page_anchor_text,
    split_head_tail_on_anchors,
    text_has_page_anchor,
)

# 识别失败标记前缀：识别失败时 render_body 以此前缀打头该文件正文。
OCR_ERROR_PREFIX = "[识别失败]"

# 转换稿文件头声明：让模型/前端/人工都知道页号属于一个已销毁的临时渲染物，而非原 docx 的页。
CONVERTED_HEADER_NOTE = ", 已转换为PDF识别, 页号为转换稿页号"

# 云 OCR 页数守卫命中时的文件头标注（KD1 cloud_seq；回查闸据此把该文件证据整体标 page_unverified）。
_PAGE_UNRELIABLE_NOTE = " [⚠页号存疑：云 OCR 返回 {got} 页、文档 {expected} 页，页码仅供参考]"


def result_artifact(result: dict) -> str:
    """该识别产物的页号属于哪个 artifact 坐标系（route=convert → 转换稿）。"""
    return ARTIFACT_CONVERTED if result.get("route") == "convert" else ARTIFACT_ORIGINAL


def page_anchor(page_no: int, artifact: str = ARTIFACT_ORIGINAL) -> str:
    """页锚点行（含换行）：让模型 evidence/basis 能引到底稿页（G2 证据定位准确性）。"""
    return page_anchor_text(page_no, artifact=artifact) + "\n"


def converted_header_note(result: dict) -> str:
    """文件头里的转换声明（非 convert 路由 → 空串）。"""
    return CONVERTED_HEADER_NOTE if result_artifact(result) == ARTIFACT_CONVERTED else ""


def page_confidence_note(result: dict) -> str:
    """文件头里的页号存疑标注（云 OCR 页数守卫命中 → 非空）。"""
    if result.get("page_confidence") != "low":
        return ""
    return _PAGE_UNRELIABLE_NOTE.format(
        got=result.get("page_count_returned"), expected=result.get("page_count_expected")
    )


def render_tables(tables: list[dict]) -> str:
    lines: list[str] = []
    for table in tables:
        if table.get("name"):
            lines.append(f"[表: {table['name']}]")
        for row in table.get("rows", []):
            lines.append("\t".join(str(cell) for cell in row))
    return "\n".join(lines)


def _render_ocr_pages(pages: list[dict], artifact: str) -> str:
    """OCR 产物逐页渲染。page_number 缺/None 才回退序号（不用 ``or``，免 page_number=0 被吞）。"""
    return "\n\n".join(
        page_anchor(pn if (pn := page.get("page_number")) is not None else idx, artifact)
        + (page.get("markdown") or "")
        for idx, page in enumerate(pages, start=1)
    )


def render_body(result: dict) -> str:
    """把单文件识别产物渲染成底稿正文（页锚点 + 正文 + 表格）。

    Args:
        result: ``extract_one`` 产物（native blocks/tables 或 OCR pages）。

    Returns:
        底稿正文字符串；识别失败返回 ``[识别失败] …``。
    """
    if result.get("error"):
        return f"{OCR_ERROR_PREFIX} {result['error']}"
    artifact = result_artifact(result)
    # pages 仅指 OCR 引擎产物（list[每页 {markdown}]）；native 文件的页数在 page_count，
    # 不在此。isinstance 守卫防止把页数整数误当列表迭代。
    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        return _render_ocr_pages(pages, artifact)
    # native：blocks(正文) 与 tables(表) 可并存（pdf_text/word 两者都有）→ **都渲染**。
    # 旧逻辑 tables 分支吃掉 blocks 会丢正文；P1 给 pdf_text 加了 find_tables 后更明显，故合并。
    segments: list[str] = []
    blocks = result.get("blocks")
    tables = result.get("tables") or []
    if blocks and result.get("kind") == "pdf_text":
        segments.append(_render_paged_blocks(blocks, tables, artifact))
        # 已挂到页锚下的表格不再重复拼尾；无页号的（旧产物）仍走尾部兜底。
        tables = [table for table in tables if table.get("page") is None]
    elif blocks:
        segments.append("\n".join(blocks))
    if tables:
        segments.append(render_tables(tables))
    return "\n\n".join(seg for seg in segments if seg.strip())


def _render_paged_blocks(blocks: list, tables: list[dict], artifact: str) -> str:
    """pdf_text 的 blocks 一页一项（read_pdf_text 逐页 append）→ 按页打锚点。

    KD4：带页号的 tables 渲染进**所属页锚之下**（与该页正文相邻），不再统一拼尾——统一拼尾会让
    模型按"最近锚点"把任意页的表格引成最后一页，且回查闸判 confirmed（错页畅通进结论）。
    空白页跳过但保留页号，让模型能引真实页（G2）。
    """
    tables_by_page: dict[int, list[dict]] = {}
    for table in tables:
        page = table.get("page")
        if isinstance(page, int):
            tables_by_page.setdefault(page, []).append(table)
    parts: list[str] = []
    for page_no, block in enumerate(blocks, start=1):
        page_tables = tables_by_page.get(page_no, [])
        has_text = isinstance(block, str) and block.strip()
        if not has_text and not page_tables:
            continue
        body = block if has_text else ""
        if page_tables:
            table_text = render_tables(page_tables)
            body = f"{body}\n{table_text}" if body else table_text
        parts.append(page_anchor(page_no, artifact) + body)
    return "\n\n".join(parts)


# R2：通用截断「从头切」是否改「首尾切」（保尾部，如合同付款节点/落款）。**默认关**——
# expense/audit 关键字段多在头部，贸然减头部预算会回归；tender 大非 BOQ 文件需保尾可经 env 开。
def _truncate_head_tail_enabled() -> bool:
    return os.getenv("OCR_TRUNCATE_HEAD_TAIL", "0").lower() in {"1", "true", "yes"}


def truncate_body(full_body: str, max_chars: int) -> str:
    """大文件截断：默认头截（向后兼容）；OCR_TRUNCATE_HEAD_TAIL=1 则首尾截（保尾）。

    KD3：首尾截的切点吸附到页锚行边界，且尾段开头**重放所属页锚**——否则尾段内容在模型视角归属
    head 末锚（早得多的页），是"证据页码对不上"的主链路成因之一。

    截断标记本身**不含页锚字样**——免破 evidence-resolution 的 parse_corpus 页索引（R1 协同）。
    """
    n = len(full_body)
    if not _truncate_head_tail_enabled():
        return full_body[:max_chars] + (
            f"\n\n...[内容已截断：本文件共 {n} 字符，仅保留前 {max_chars}；"
            f"尾部信息（如合同付款节点）可能丢失，相关字段请标 low_confidence / needs_review]"
        )
    head_n = int(max_chars * 0.7)
    head, tail, replay = split_head_tail_on_anchors(full_body, head_n, max_chars - head_n)
    note = "" if text_has_page_anchor(full_body) else "；本文件无页锚，按字符切"
    marker = (
        f"\n\n...[内容已截断：本文件共 {n} 字符，保留首 {len(head)} + 尾 {len(tail)}，"
        f"中间省略{note}；相关字段请标 low_confidence / needs_review]\n\n"
    )
    return head + marker + (f"{replay}\n" if replay else "") + tail
