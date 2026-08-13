"""Deterministic document-level structure extraction for OCR text."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from server.common.corpus import ARTIFACT_ORIGINAL, parse_page_anchor
from server.common.corpus import PAGE_ANCHOR_LINE_RE as _PAGE_RE
from server.ocr.boq import _AMOUNT_STRICT, _PAGE_CARRY_LINES

_FILE_HEADER_RE = re.compile(r"^\s*###\s*文件:\s*(.*?)\s+\(kind=")
_MARKDOWN_TITLE_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
_CHAPTER_TITLE_RE = re.compile(r"^\s*第[一二三四五六七八九十百千0-9]+[章节篇部分]\s*.*$")
_SECTION_TITLE_RE = re.compile(r"^\s*[一二三四五六七八九十]+、\s*.+$")
_SUBSECTION_TITLE_RE = re.compile(r"^\s*（[一二三四五六七八九十0-9]+）\s*.+$")
_DATE_RE = re.compile(
    r"(?P<year>\d{4})\s*[-/年]\s*"
    r"(?P<month>\d{1,2})\s*[-/月]\s*(?P<day>\d{1,2})\s*日?"
)
_CERT_RE = re.compile(
    r"(?:证书|资质|注册)\s*编号\s*[:：]?\s*"
    r"(?P<value>[一-龥A-Za-z0-9][一-龥A-Za-z0-9\-]{5,})"
)
_PERSON_RE = re.compile(
    r"(?:项目经理|项目负责人|技术负责人|法定代表人)\s*[:：]?\s*"
    r"(?P<value>[一-龥]{2,4})"
)
_TABLE_HEADER_RE = re.compile(r"^\s*\[表:\s*(.*?)\]\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$")

_TAG_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("evaluation_method", ("评标办法", "评分标准", "评分细则", "评审办法")),
    (
        "qualification_review",
        ("资格审查", "资格评审", "资格要求", "初步评审", "符合性审查", "响应性审查"),
    ),
    ("performance", ("业绩", "类似项目", "类似工程")),
    ("bid_form", ("投标函", "投标报价", "开标一览")),
    ("commercial", ("商务", "合同条款", "付款")),
    ("technical", ("技术方案", "技术标", "施工组织")),
)


def scan_page_context(lines: Sequence[str]) -> tuple[list[int | None], set[int]]:
    """Return the page visible at each line and all page numbers in anchors."""
    page_of: list[int | None] = []
    pages: set[int] = set()
    current: int | None = None
    distance = 0
    for raw in lines:
        anchor = parse_page_anchor(raw)
        if anchor is not None:
            current = anchor[0]
            pages.add(current)
            distance = 0
            page_of.append(current)
            continue
        distance += 1
        page_of.append(current if current is not None and distance <= _PAGE_CARRY_LINES else None)
    return page_of, pages


def chapter_heading(raw: str) -> tuple[str, int] | None:
    """Recognize a conservative chapter heading and return its title and level."""
    markdown = _MARKDOWN_TITLE_RE.match(raw)
    if markdown:
        return markdown.group(2).strip(), min(len(markdown.group(1)), 3)
    if _CHAPTER_TITLE_RE.match(raw):
        return raw.strip(), 1
    if _SECTION_TITLE_RE.match(raw):
        return raw.strip(), 2
    if _SUBSECTION_TITLE_RE.match(raw):
        return raw.strip(), 3
    return None


def tag_chapter(title: str) -> str | None:
    """Assign a deterministic semantic tag from chapter-title keywords."""
    if not title.strip():
        return None
    for tag, keywords in _TAG_KEYWORDS:
        if any(keyword in title for keyword in keywords):
            return tag
    return "general"


def parse_chapters(
    lines: Sequence[str], page_of: Sequence[int | None] | None = None
) -> list[dict[str, Any]]:
    """Parse formal headings into a nested chapter tree."""
    contexts = page_of if page_of is not None else scan_page_context(lines)[0]
    roots: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    for index, raw in enumerate(lines):
        if raw.strip().startswith("### 文件:"):
            continue
        heading = chapter_heading(raw)
        if heading is None:
            continue
        title, level = heading
        node: dict[str, Any] = {
            "title": title,
            "level": level,
            "page": contexts[index] if index < len(contexts) else None,
            "tag": tag_chapter(title),
            "children": [],
        }
        while stack and stack[-1]["level"] >= level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _source_line(raw: str) -> str:
    """Normalize one source line and cap it for compact provenance."""
    return " ".join(raw.split())[:120]


def extract_entities(
    lines: Sequence[str], page_of: Sequence[int | None] | None = None
) -> list[dict[str, Any]]:
    """Extract labeled amounts, dates, certificate numbers, and people."""
    contexts = page_of if page_of is not None else scan_page_context(lines)[0]
    found: list[tuple[int, int, dict[str, Any]]] = []
    seen: set[tuple[str, str, int | None]] = set()
    for index, raw in enumerate(lines):
        if _PAGE_RE.match(raw) or raw.strip().startswith("### 文件:"):
            continue
        page = contexts[index] if index < len(contexts) else None
        source = _source_line(raw)

        def add(entity_type: str, value: str, position: int) -> None:
            key = (entity_type, value, page)
            if key in seen:
                return
            seen.add(key)
            found.append(
                (
                    index,
                    position,
                    {"type": entity_type, "value": value, "page": page, "source": source},
                )
            )

        for match in _AMOUNT_STRICT.finditer(raw):
            add("amount", match.group().replace(",", ""), match.start())
        for match in _DATE_RE.finditer(raw):
            value = "{year}-{month:02d}-{day:02d}".format(
                year=int(match.group("year")),
                month=int(match.group("month")),
                day=int(match.group("day")),
            )
            add("date", value, match.start())
        for match in _CERT_RE.finditer(raw):
            add("cert_no", match.group("value"), match.start())
        for match in _PERSON_RE.finditer(raw):
            add("person", match.group("value"), match.start())
    found.sort(key=lambda item: (item[0], item[1]))
    return [entity for _, _, entity in found]


def _table_row(raw: str) -> list[str] | None:
    """Parse one tab-separated or markdown table row."""
    stripped = raw.strip()
    if "\t" in raw:
        cells = [cell.strip() for cell in raw.split("\t")]
        return cells if len(cells) >= 2 and any(cells) else None
    if "|" not in stripped:
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return cells if len(cells) >= 2 and any(cells) else None


def _is_table_separator(raw: str) -> bool:
    """Return whether a markdown separator row is present."""
    return bool(_TABLE_SEPARATOR_RE.match(raw))


def _table_segment(
    name: str | None,
    rows: list[list[str]],
    start: int,
    end: int,
    page_of: Sequence[int | None],
    has_header: bool,
) -> dict[str, Any]:
    """Create an internal table segment used by ``merge_tables``."""
    columns = rows[0] if rows and has_header else (rows[0] if rows else [])
    data_rows = rows[1:] if has_header and rows else rows
    pages = [page_of[i] for i in range(start, end + 1) if page_of[i] is not None]
    return {
        "name": name or "",
        "columns": columns,
        "row_count": len(data_rows),
        "start_page": pages[0] if pages else None,
        "end_page": pages[-1] if pages else None,
        "merged_from_pages": list(dict.fromkeys(pages)),
        "_start": start,
        "_end": end,
        "_has_header": has_header,
    }


def _table_gap_is_single_anchor(
    lines: Sequence[str], previous: dict[str, Any], current: dict[str, Any]
) -> bool:
    """Check that two table segments touch across exactly one page anchor."""
    gap = lines[previous["_end"] + 1 : current["_start"]]
    anchors = [line for line in gap if _PAGE_RE.match(line)]
    return len(anchors) == 1 and all(not line.strip() or _PAGE_RE.match(line) for line in gap)


def _public_table(segment: dict[str, Any]) -> dict[str, Any]:
    """Remove internal segment bookkeeping from a table result."""
    return {
        key: segment[key]
        for key in ("name", "start_page", "end_page", "columns", "row_count", "merged_from_pages")
    }


def merge_tables(
    lines: Sequence[str], page_of: Sequence[int | None] | None = None
) -> list[dict[str, Any]]:
    """Find conservative table segments and merge compatible cross-page continuations."""
    contexts = page_of if page_of is not None else scan_page_context(lines)[0]
    segments: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        header = _TABLE_HEADER_RE.match(lines[index])
        first_row = _table_row(lines[index])
        if header:
            name = header.group(1).strip()
            start = index
            rows: list[list[str]] = []
            index += 1
            while index < len(lines):
                if _PAGE_RE.match(lines[index]) or _TABLE_HEADER_RE.match(lines[index]):
                    break
                row = _table_row(lines[index])
                if row is None:
                    if lines[index].strip():
                        break
                    index += 1
                    continue
                if not _is_table_separator(lines[index]):
                    rows.append(row)
                index += 1
            end = index - 1 if rows else start
            segments.append(_table_segment(name, rows, start, end, contexts, bool(rows)))
            continue
        if first_row is not None:
            start = index
            rows = []
            while index < len(lines):
                if _PAGE_RE.match(lines[index]) or _TABLE_HEADER_RE.match(lines[index]):
                    break
                row = _table_row(lines[index])
                if row is None:
                    if lines[index].strip():
                        break
                    index += 1
                    continue
                if not _is_table_separator(lines[index]):
                    rows.append(row)
                index += 1
            end = index - 1
            has_header = len(rows) >= 2 and _is_table_separator(lines[start + 1])
            segments.append(_table_segment(None, rows, start, end, contexts, has_header))
            continue
        index += 1

    merged: list[dict[str, Any]] = []
    for segment in segments:
        if merged:
            previous = merged[-1]
            compatible_name = not segment["name"] or segment["name"] == previous["name"]
            compatible_columns = segment["_has_header"] is False or len(segment["columns"]) == len(
                previous["columns"]
            )
            if (
                _table_gap_is_single_anchor(lines, previous, segment)
                and compatible_name
                and compatible_columns
            ):
                previous["row_count"] += segment["row_count"]
                previous["end_page"] = segment["end_page"] or previous["end_page"]
                previous["merged_from_pages"] = list(
                    dict.fromkeys(previous["merged_from_pages"] + segment["merged_from_pages"])
                )
                previous["_end"] = segment["_end"]
                continue
        merged.append(segment)
    return [_public_table(segment) for segment in merged]


def find_chapters_by_tag(structure: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    """Return all chapter nodes with ``tag`` in depth-first order."""
    matches: list[dict[str, Any]] = []

    def visit(chapters: Sequence[dict[str, Any]]) -> None:
        for chapter in chapters:
            if chapter.get("tag") == tag:
                matches.append(chapter)
            visit(chapter.get("children", []))

    visit(structure.get("chapters", []))
    return matches


def _file_name(block: str, explicit: str | None) -> str:
    """Extract the first pipeline file name unless an explicit name was supplied."""
    if explicit is not None:
        return explicit
    for raw in block.splitlines():
        match = _FILE_HEADER_RE.match(raw)
        if match:
            return match.group(1).strip()
        if raw.strip().startswith("### 文件:"):
            return raw.split(":", 1)[1].strip()
    return ""


def _page_artifact(lines: Sequence[str]) -> str:
    """本文档页号所属坐标系：出现过转换稿锚即 ``converted``，否则 ``original``。"""
    for raw in lines:
        anchor = parse_page_anchor(raw)
        if anchor is not None and anchor[1] != ARTIFACT_ORIGINAL:
            return anchor[1]
    return ARTIFACT_ORIGINAL


def build_doc_structure(block_or_body: str, *, file_name: str | None = None) -> dict[str, Any]:
    """Build a schema-shaped document structure from a pipeline extraction block."""
    lines = (block_or_body or "").splitlines()
    page_of, pages = scan_page_context(lines)
    return {
        "file": _file_name(block_or_body or "", file_name),
        "page_count": max(pages) if pages else None,
        # 页号所属坐标系（H2 pass1 F3）：一份文档整体属同一 artifact，下游 RAG chunk 据此
        # 渲染锚点，避免转换稿页号在检索链路上再次冒充原文档页。
        "page_artifact": _page_artifact(lines),
        "chapters": parse_chapters(lines, page_of),
        "entities": extract_entities(lines, page_of),
        "tables": merge_tables(lines, page_of),
    }
