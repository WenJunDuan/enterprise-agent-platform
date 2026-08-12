"""原生直读：Excel / 文本型 Word / 纯文本 / 文本层 PDF → 结构化 dict。

数字文件直读：零 OCR 误差、保留行列/合并/公式。第三方依赖在函数内导入，缺失时抛
`OcrDependencyError`，便于无依赖环境也能 import 本模块做单测。
"""

from __future__ import annotations

import importlib
import logging
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

from server.ocr import OcrDependencyError
from server.ocr.formats import suffixes
from server.ocr.locks import FITZ_LOCK

logger = logging.getLogger(__name__)

EXCEL_OOXML_EXT = suffixes("excel_ooxml")
EXCEL_XLS_EXT = suffixes("excel_xls")
EXCEL_XLSB_EXT = suffixes("excel_xlsb")
WORD_EXT = suffixes("word_native")
LEGACY_WORD_EXT = suffixes("word_legacy")
PRESENTATION_EXT = suffixes("presentation_native")
PDF_EXT = suffixes("pdf")

# 单 sheet 安全上限，防超大表撑爆下游上下文
MAX_EXCEL_ROWS = 5000


# 逐页 find_tables 在超大 PDF 上成本爆炸：实测 8417 页 BOQ 耗 324s + 产 17970 冗余表使 full_body
# 膨胀到 39.9M（5× blocks）。收益边际——blocks 的 get_text(sort=True) 已含表格文本，R2 BOQ 摘要即
# 从 blocks 抽。故页数超此上限的 PDF **跳过 find_tables**（仅保留 blocks 文本），把 BOQ 首跑 OCR
# 从数百秒压到秒级。普通标书/发票/合同（≤ 上限）照常 find_tables。env OCR_FIND_TABLES_MAX_PAGES 可调。
def _find_tables_max_pages() -> int:
    try:
        return int(os.getenv("OCR_FIND_TABLES_MAX_PAGES", "500"))
    except (TypeError, ValueError):
        return 500


def _require(module: str, package: str):
    """按需导入第三方模块；缺失时抛 OcrDependencyError（带安装提示）。"""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise OcrDependencyError(f"缺少依赖 {package}：uv add {package}") from exc


def read_excel(path: Path) -> dict:
    """Read OOXML Excel only; binary formats have dedicated readers."""
    openpyxl = _require("openpyxl", "openpyxl")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = []
        for worksheet in workbook.worksheets:
            rows = []
            for index, row in enumerate(worksheet.iter_rows(values_only=True)):
                if index >= MAX_EXCEL_ROWS:
                    break
                rows.append(["" if cell is None else str(cell) for cell in row])
            sheets.append({"name": worksheet.title, "rows": rows})
    finally:
        workbook.close()  # 并行抽取下异常也释放文件句柄（codex P2-9）
    return {"kind": "excel", "tables": sheets}


def read_excel_xls(path: Path) -> dict:
    """Read historical binary .xls workbooks with xlrd."""
    xlrd = _require("xlrd", "xlrd")
    workbook = xlrd.open_workbook(filename=str(path), on_demand=True)
    try:
        tables = []
        for sheet in workbook.sheets():
            rows = [
                ["" if value is None else str(value) for value in sheet.row_values(index)]
                for index in range(min(sheet.nrows, MAX_EXCEL_ROWS))
            ]
            tables.append({"name": sheet.name, "rows": rows})
    finally:
        workbook.release_resources()
    return {"kind": "excel", "tables": tables}


def read_excel_xlsb(path: Path) -> dict:
    """Read binary .xlsb workbooks with pyxlsb."""
    pyxlsb = _require("pyxlsb", "pyxlsb")
    tables = []
    with pyxlsb.open_workbook(str(path)) as workbook:
        for sheet_name in workbook.sheets:
            rows = []
            with workbook.get_sheet(sheet_name) as sheet:
                for index, row in enumerate(sheet):
                    if index >= MAX_EXCEL_ROWS:
                        break
                    rows.append(["" if cell.v is None else str(cell.v) for cell in row])
            tables.append({"name": sheet_name, "rows": rows})
    return {"kind": "excel", "tables": tables}


def _iter_presentation_shapes(shapes, seen: set[int] | None = None):
    """Yield top-level and nested GroupShape children once in document order."""
    if seen is None:
        seen = set()
    for shape in shapes:
        marker = id(shape)
        if marker in seen:
            continue
        seen.add(marker)
        yield shape
        children = getattr(shape, "shapes", None)
        if children is not None:
            yield from _iter_presentation_shapes(children, seen)


def read_presentation(path: Path) -> dict:
    """Extract text boxes and tables from OOXML PowerPoint files."""
    pptx = _require("pptx", "python-pptx")
    presentation = pptx.Presentation(str(path))
    blocks: list[str] = []
    tables: list[dict] = []
    text_parts: list[str] = []
    image_count = 0
    for slide in presentation.slides:
        for shape in _iter_presentation_shapes(slide.shapes):
            if getattr(shape, "has_text_frame", False) and str(shape.text).strip():
                text = str(shape.text)
                blocks.append(text)
                text_parts.append(text)
            if getattr(shape, "has_table", False):
                rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
                tables.append({"rows": rows})
                text_parts.extend(str(cell) for row in rows for cell in row)
            # python-pptx's stable MSO_SHAPE_TYPE.PICTURE value is 13. Recording the signal here
            # lets the pipeline upgrade only scan-heavy decks instead of converting every PPTX.
            if getattr(shape, "shape_type", None) == 13:
                image_count += 1
    text_char_count = sum(len("".join(text.split())) for text in text_parts)
    return {
        "kind": "presentation",
        "blocks": blocks,
        "tables": tables,
        "image_count": image_count,
        "text_char_count": text_char_count,
    }


def read_word(path: Path) -> dict:
    docx = _require("docx", "python-docx")
    document = docx.Document(str(path))
    blocks = [p.text for p in document.paragraphs if p.text.strip()]
    tables = [
        {"rows": [[cell.text for cell in row.cells] for row in table.rows]}
        for table in document.tables
    ]
    return {"kind": "word", "blocks": blocks, "tables": tables}


def _clean_extracted_text(text: str) -> str:
    """Normalize command/fallback text into non-empty, readable lines."""
    text = text.replace("\x00", "")
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        normalized = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


def _run_text_converter(argv: list[str]) -> str | None:
    """Run an external legacy Word converter and return cleaned stdout when useful."""
    if not shutil.which(argv[0]):
        return None
    try:
        completed = subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    cleaned = _clean_extracted_text(completed.stdout)
    return cleaned or None


def _read_legacy_word_utf16_fallback(path: Path) -> str:
    """Best-effort fallback for old .doc files with an embedded UTF-16LE text layer."""
    raw = path.read_bytes()
    decoded = raw.decode("utf-16le", errors="ignore")
    chars: list[str] = []
    for ch in decoded:
        if ch in {"\n", "\r", "\t"}:
            chars.append(ch)
            continue
        category = unicodedata.category(ch)
        if category[0] == "C":
            chars.append("\n")
            continue
        if ch.isprintable():
            chars.append(ch)
    cleaned = _clean_extracted_text("".join(chars))
    # Keep only lines with enough signal to avoid dumping binary noise into the prompt.
    lines = [
        line
        for line in cleaned.splitlines()
        if len(re.sub(r"\W+", "", line, flags=re.UNICODE)) >= 2
    ]
    return "\n".join(lines)


def read_legacy_word(path: Path) -> dict:
    """Read legacy binary ``.doc`` files through native text extractors before OCR.

    Order matters for deployment:
    - macOS: ``textutil`` preserves enough Word text without extra packages.
    - Linux containers: ``catdoc`` first, then ``antiword``.
    - Final fallback: extract embedded UTF-16LE text runs from the binary.
    """
    commands: list[list[str]] = []
    if sys.platform == "darwin":
        commands.append(["textutil", "-convert", "txt", "-stdout", str(path)])
    commands.extend((["catdoc", str(path)], ["antiword", str(path)]))

    text = None
    for argv in commands:
        text = _run_text_converter(argv)
        if text:
            break
    if not text:
        text = _read_legacy_word_utf16_fallback(path)
    return {"kind": "word", "blocks": [text] if text else [], "tables": []}


def read_pdf_text(
    path: Path, *, on_page: Callable[[int, dict], None] | None = None
) -> dict:
    """文本层 PDF 直读：pymupdf 阅读顺序文本 + ``find_tables`` 抽表。

    比 pypdf 的 ``extract_text``（按 PDF 流顺序拼字符）强在**阅读顺序 / 多栏 / 表格**——
    发票、合同、招标评分表的命门正在这里（pypdf 把表格揉碎、多栏错序）。

    fitz 非线程安全，并行 OCR 时经【共享】``FITZ_LOCK`` 串行化（与 engine 渲染共用同一把锁，
    见 server/ocr/locks.py）。

    Args:
        path: PDF 文件路径。
        on_page: 可选页级完成回调 ``(page_no, {"text": str})``（1-based 真实页号）。**buffer-
            then-fire**：页文本先收集到本地 list，退出 ``with FITZ_LOCK`` 临界区后才逐条回放
            ——回调绝不在持有 ``FITZ_LOCK`` 时被调用（D9 streaming-ocr T1，防锁竞争放大）。
    """
    fitz = _require("fitz", "pymupdf")
    blocks: list[str] = []
    tables: list[dict] = []
    page_buffer: list[tuple[int, dict]] = []
    with FITZ_LOCK, fitz.open(str(path)) as document:
        # 超大 PDF（如数千页 BOQ）跳过逐页 find_tables（成本爆炸、收益边际，见模块注释）。
        run_find_tables = document.page_count <= _find_tables_max_pages()
        if not run_find_tables:
            logger.info(
                "find_tables_skipped_large_pdf",
                extra={"pages": document.page_count, "path": str(path)},
            )
        for page_no, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True) or ""
            blocks.append(text)
            if on_page is not None:
                page_buffer.append((page_no, {"text": text}))
            if not run_find_tables:
                continue
            try:
                found = page.find_tables()
            except Exception:  # 个别畸形页 find_tables 可能抛错，单页失败不毁整篇
                continue
            for table in getattr(found, "tables", []) or []:
                rows = [
                    ["" if cell is None else str(cell) for cell in row]
                    for row in table.extract()
                ]
                if any(any(cell.strip() for cell in row) for row in rows):
                    # 页号必须随表走（H2 KD4）：丢了它，_render_body 只能把表格无锚拼在底稿末尾，
                    # 模型按"最近锚点"把任意页的表格引成最后一页，且回查闸判 confirmed。
                    tables.append({"rows": rows, "page": page_no})
    if on_page is not None:  # 锁已释放，此时才回放（buffer-then-fire）
        for page_no, payload in page_buffer:
            on_page(page_no, payload)
    return {"kind": "pdf_text", "blocks": blocks, "tables": tables}


def read_text(path: Path) -> dict:
    return {"kind": "text", "blocks": [path.read_text(encoding="utf-8", errors="ignore")]}


def native_read(
    path: Path, *, on_page: Callable[[int, dict], None] | None = None
) -> dict:
    """按扩展名分派到对应直读器。

    ``on_page`` 只对 ``read_pdf_text``（逐页循环）生效；excel/word/text 无页循环，页级回调
    对它们不适用——调用方（``server.ocr.pipeline``）对这些格式退化为文件级单元（至少一次）。
    """
    ext = path.suffix.lower()
    if ext in EXCEL_OOXML_EXT:
        return read_excel(path)
    if ext in EXCEL_XLS_EXT:
        return read_excel_xls(path)
    if ext in EXCEL_XLSB_EXT:
        return read_excel_xlsb(path)
    if ext in WORD_EXT:
        return read_word(path)
    if ext in LEGACY_WORD_EXT:
        return read_legacy_word(path)
    if ext in PRESENTATION_EXT:
        return read_presentation(path)
    if ext in PDF_EXT:
        return read_pdf_text(path, on_page=on_page)
    return read_text(path)
