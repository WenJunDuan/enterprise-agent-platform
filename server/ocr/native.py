"""原生直读：Excel / 文本型 Word / 纯文本 / 文本层 PDF → 结构化 dict。

数字文件直读：零 OCR 误差、保留行列/合并/公式。第三方依赖在函数内导入，缺失时抛
`OcrDependencyError`，便于无依赖环境也能 import 本模块做单测。
"""

from __future__ import annotations

import importlib
from pathlib import Path

from server.ocr import OcrDependencyError

EXCEL_EXT = {".xlsx", ".xlsm", ".xls"}
WORD_EXT = {".docx"}
PDF_EXT = {".pdf"}

# 单 sheet 安全上限，防超大表撑爆下游上下文
MAX_EXCEL_ROWS = 5000


def _require(module: str, package: str):
    """按需导入第三方模块；缺失时抛 OcrDependencyError（带安装提示）。"""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise OcrDependencyError(f"缺少依赖 {package}：uv add {package}") from exc


def read_excel(path: Path) -> dict:
    openpyxl = _require("openpyxl", "openpyxl")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for worksheet in workbook.worksheets:
        rows = []
        for index, row in enumerate(worksheet.iter_rows(values_only=True)):
            if index >= MAX_EXCEL_ROWS:
                break
            rows.append(["" if cell is None else str(cell) for cell in row])
        sheets.append({"name": worksheet.title, "rows": rows})
    workbook.close()
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
    pypdf = _require("pypdf", "pypdf")
    reader = pypdf.PdfReader(str(path))
    return {"kind": "pdf_text", "blocks": [(page.extract_text() or "") for page in reader.pages]}


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
