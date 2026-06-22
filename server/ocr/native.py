"""原生直读：Excel / 文本型 Word / 纯文本 / 文本层 PDF → 结构化 dict。

数字文件直读：零 OCR 误差、保留行列/合并/公式。第三方依赖在函数内导入，缺失时抛
`OcrDependencyError`，便于无依赖环境也能 import 本模块做单测。
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path

from server.ocr import OcrDependencyError
from server.ocr.locks import FITZ_LOCK

logger = logging.getLogger(__name__)

EXCEL_EXT = {".xlsx", ".xlsm", ".xls"}
WORD_EXT = {".docx"}
PDF_EXT = {".pdf"}

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


def read_word(path: Path) -> dict:
    docx = _require("docx", "python-docx")
    document = docx.Document(str(path))
    blocks = [p.text for p in document.paragraphs if p.text.strip()]
    tables = [
        {"rows": [[cell.text for cell in row.cells] for row in table.rows]}
        for table in document.tables
    ]
    return {"kind": "word", "blocks": blocks, "tables": tables}


def read_pdf_text(path: Path) -> dict:
    """文本层 PDF 直读：pymupdf 阅读顺序文本 + ``find_tables`` 抽表。

    比 pypdf 的 ``extract_text``（按 PDF 流顺序拼字符）强在**阅读顺序 / 多栏 / 表格**——
    发票、合同、招标评分表的命门正在这里（pypdf 把表格揉碎、多栏错序）。

    fitz 非线程安全，并行 OCR 时经【共享】``FITZ_LOCK`` 串行化（与 engine 渲染共用同一把锁，
    见 server/ocr/locks.py）。
    """
    fitz = _require("fitz", "pymupdf")
    blocks: list[str] = []
    tables: list[dict] = []
    with FITZ_LOCK, fitz.open(str(path)) as document:
        # 超大 PDF（如数千页 BOQ）跳过逐页 find_tables（成本爆炸、收益边际，见模块注释）。
        run_find_tables = document.page_count <= _find_tables_max_pages()
        if not run_find_tables:
            logger.info(
                "find_tables_skipped_large_pdf",
                extra={"pages": document.page_count, "path": str(path)},
            )
        for page in document:
            blocks.append(page.get_text("text", sort=True) or "")
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
                    tables.append({"rows": rows})
    return {"kind": "pdf_text", "blocks": blocks, "tables": tables}


def read_text(path: Path) -> dict:
    return {"kind": "text", "blocks": [path.read_text(encoding="utf-8", errors="ignore")]}


def native_read(path: Path) -> dict:
    """按扩展名分派到对应直读器。"""
    ext = path.suffix.lower()
    if ext in EXCEL_EXT:
        return read_excel(path)
    if ext in WORD_EXT:
        return read_word(path)
    if ext in PDF_EXT:
        return read_pdf_text(path)
    return read_text(path)
