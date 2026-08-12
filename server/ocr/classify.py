"""L1 容器分诊：判定文档类型 + 是否含文本层，决定 native / ocr / manual。

零第三方依赖（仅标准库），可在任何环境先跑分诊与单测。判定"原生直读 vs OCR"，
避免把数字文件(Excel/文本)送进 OCR 造成慢且有损。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from server.ocr.formats import suffixes

EXCEL_OOXML_EXT = suffixes("excel_ooxml")
EXCEL_XLS_EXT = suffixes("excel_xls")
EXCEL_XLSB_EXT = suffixes("excel_xlsb")
TEXT_EXT = suffixes("text")
IMAGE_EXT = suffixes("images")
WORD_EXT = suffixes("word_native")
LEGACY_WORD_EXT = suffixes("word_legacy")
PRESENTATION_EXT = suffixes("presentation_native")
OFFICE_CONVERT_EXT = suffixes("office_convert")
PDF_EXT = suffixes("pdf")

# DOCX 判文本型：正文字符数低于此值且含嵌入图 → 视为图片/扫描型
DOCX_MIN_TEXT_CHARS = 200


def _probe_pdf(data: bytes) -> dict:
    """字节级探测 PDF 是否含文本层。

    判据用 `fonts > 0`：PDF 渲染文本必须嵌入/引用字体，纯扫描件（整页图像）通常 0 字体。
    不用字节大小做判据——电子文档可含大图（印章 / 图表）但仍有文本层；曾用 kb/page 阈值
    把可直读的电子证照（如备案证，单页 ~378KB 但有字体、可抽 570 字符）误判成扫描件、
    白送 OCR（慢且有损）。
    """
    pages = max(1, len(re.findall(rb"/Type\s*/Page[^s]", data)))
    fonts = len(re.findall(rb"/Font", data))
    image_filters = len(re.findall(rb"/DCTDecode|/JPXDecode|/CCITTFaxDecode", data))
    has_text = fonts > 0
    return {
        "pages": pages,
        "has_text_layer": has_text,
        "scanned": image_filters > 0 and not has_text,
        # 混合 PDF：既有文本层(fonts>0)又含图像编码页(扫描/盖章页)。整体仍判 native（多数页可
        # 直读），但 pipeline 据此 + 空白页计数决定是否对扫描页做子集云 OCR 补回——native 直读对
        # 扫描页抽出空串被静默丢失（张謇 400 页投标含 ~59 页扫描证书）。纯数字 PDF 的空白页是
        # 真空页(无扫描内容可补)，故必须用 image_filters>0 区分"空因扫描"vs"空因无内容"。
        # 注：image_filters 含正文嵌图/电子章/Logo 会假阳性置 mixed_pdf=True，但无害——下游还要过
        # 空白页计数/比例阈值，且对真空页 OCR 出空文本不回填（pipeline text.strip() 守卫）。
        "mixed_pdf": image_filters > 0 and has_text,
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
    text_len = len(re.sub(r"<[^>]+>", "", xml).strip())
    has_text = text_len > 0 and (not media or text_len >= DOCX_MIN_TEXT_CHARS)
    return {"has_text_layer": has_text, "scanned": bool(media) and not has_text}


def _route(container, route, handler, has_text, reason, page_count=None, mixed_pdf=False) -> dict:
    return {
        "container": container,
        "route": route,
        "handler": handler,
        "has_text_layer": has_text,
        # 页数（int）。刻意命名 page_count 而非 pages —— OCR 引擎产物里的 pages 是
        # list[每页内容]，同名会让下游 draft_render.render_body 把整数当列表迭代而崩。
        "page_count": page_count,
        # 混合 PDF 标记（仅 PDF 有意义；其余容器恒 False）。供 pipeline gate 整份转云 OCR。
        "mixed_pdf": mixed_pdf,
        "reason": reason,
    }


def classify(path: Path) -> dict:
    """返回路由决策 dict：container / route(native|ocr|manual) / handler / has_text_layer / pages / reason / path。"""
    ext = path.suffix.lower()
    if ext in EXCEL_OOXML_EXT:
        result = _route("excel", "native", "excel_ooxml", True, "OOXML Excel 原生直读")
    elif ext in EXCEL_XLS_EXT:
        result = _route("excel", "native", "excel_xls", True, "旧版 Excel 由 xlrd 原生直读")
    elif ext in EXCEL_XLSB_EXT:
        result = _route("excel", "native", "excel_xlsb", True, "二进制 Excel 由 pyxlsb 原生直读")
    elif ext in TEXT_EXT:
        result = _route("text", "native", "text", True, "纯文本直读")
    elif ext in IMAGE_EXT:
        result = _route("image", "ocr", "image", False, "图片只能 OCR")
    elif ext in WORD_EXT:
        probe = _probe_docx(path)
        result = (
            _route("word", "native", "word", True, "文本型 Word，python-docx 直读")
            if probe["has_text_layer"]
            else _route("word", "convert", "office_convert", False, "扫描型 Word 先转 PDF")
        )
    elif ext in LEGACY_WORD_EXT:
        result = _route("word", "native", "legacy_word", True, "老 Word .doc 原生文本抽取")
    elif ext in PRESENTATION_EXT:
        result = _route("presentation", "native", "presentation", True, "PowerPoint 原生直读")
    elif ext in OFFICE_CONVERT_EXT:
        result = _route("office", "convert", "office_convert", False, "Office 先转 PDF")
    elif ext in PDF_EXT:
        probe = _probe_pdf(path.read_bytes())
        result = (
            _route(
                "pdf",
                "native",
                "pdf_text",
                True,
                "PDF 含文本层，直抽",
                probe["pages"],
                mixed_pdf=probe["mixed_pdf"],
            )
            if probe["has_text_layer"]
            else _route("pdf", "ocr", "pdf_scan", False, "扫描 PDF，转 OCR", probe["pages"])
        )
    else:
        result = _route(ext or "unknown", "manual", "unknown", False, "类型不在白名单，转人工")
    result["path"] = str(path)
    return result
