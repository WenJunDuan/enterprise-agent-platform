"""L1 容器分诊：判定文档类型 + 是否含文本层，决定 native / ocr / manual。

零第三方依赖（仅标准库），可在任何环境先跑分诊与单测。判定"原生直读 vs OCR"，
避免把数字文件(Excel/文本)送进 OCR 造成慢且有损。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

EXCEL_EXT = {".xlsx", ".xlsm", ".xls"}
TEXT_EXT = {".txt", ".csv", ".md", ".json", ".tsv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
WORD_EXT = {".docx"}
PDF_EXT = {".pdf"}

# DOCX 判文本型：正文字符数低于此值且含嵌入图 → 视为图片/扫描型
DOCX_MIN_TEXT_CHARS = 200
# 扫描 PDF 经验阈值：单页字节 > 200KB 且无字体 → 图像页
PDF_SCANNED_KB_PER_PAGE = 200


def _probe_pdf(data: bytes) -> dict:
    """字节级探测 PDF：是否含文本层（字体）vs 扫描图像。"""
    pages = max(1, len(re.findall(rb"/Type\s*/Page[^s]", data)))
    fonts = len(re.findall(rb"/Font", data))
    image_filters = len(re.findall(rb"/DCTDecode|/JPXDecode|/CCITTFaxDecode", data))
    kb_per_page = len(data) / pages / 1024
    has_text = fonts > 0 and kb_per_page < PDF_SCANNED_KB_PER_PAGE
    return {
        "pages": pages,
        "has_text_layer": has_text,
        "scanned": image_filters > 0 and not has_text,
    }


def _probe_docx(path: Path) -> dict:
    """探测 DOCX：正文文字量 vs 嵌入图片，判文本型 vs 图片型。"""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            media = [n for n in names if n.startswith("word/media/")]
            xml = (
                archive.read("word/document.xml").decode("utf-8", "ignore")
                if "word/document.xml" in names
                else ""
            )
    except (zipfile.BadZipFile, KeyError, OSError):
        return {"has_text_layer": False, "scanned": True}
    text_len = len(re.sub(r"<[^>]+>", "", xml))
    has_text = text_len >= DOCX_MIN_TEXT_CHARS
    return {"has_text_layer": has_text, "scanned": bool(media) and not has_text}


def _route(container, route, handler, has_text, reason, pages=None) -> dict:
    return {
        "container": container,
        "route": route,
        "handler": handler,
        "has_text_layer": has_text,
        "pages": pages,
        "reason": reason,
    }


def classify(path: Path) -> dict:
    """返回路由决策 dict：container / route(native|ocr|manual) / handler / has_text_layer / pages / reason / path。"""
    ext = path.suffix.lower()
    if ext in EXCEL_EXT:
        result = _route("excel", "native", "excel", True, "Excel 直读，绝不 OCR")
    elif ext in TEXT_EXT:
        result = _route("text", "native", "text", True, "纯文本直读")
    elif ext in IMAGE_EXT:
        result = _route("image", "ocr", "image", False, "图片只能 OCR")
    elif ext in WORD_EXT:
        probe = _probe_docx(path)
        result = (
            _route("word", "native", "word", True, "文本型 Word，python-docx 直读")
            if probe["has_text_layer"]
            else _route("word", "ocr", "word_scan", False, "图片/扫描型 Word，转 OCR")
        )
    elif ext in PDF_EXT:
        probe = _probe_pdf(path.read_bytes())
        result = (
            _route("pdf", "native", "pdf_text", True, "PDF 含文本层，直抽", probe["pages"])
            if probe["has_text_layer"]
            else _route("pdf", "ocr", "pdf_scan", False, "扫描 PDF，转 OCR", probe["pages"])
        )
    else:
        result = _route(ext or "unknown", "manual", "unknown", False, "类型不在白名单，转人工")
    result["path"] = str(path)
    return result
