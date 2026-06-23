"""server.ocr.classify 路由单测：覆盖扩展名分流 + PDF/DOCX 文本层探测。

零第三方依赖即可运行（classify 仅用标准库），验证"先分类再 OCR"的核心判定。
"""

from __future__ import annotations

import zipfile

from server.ocr.classify import classify


def test_excel_routes_native(tmp_path):
    path = tmp_path / "项目库.xlsx"
    path.write_bytes(b"placeholder")
    result = classify(path)
    assert result["route"] == "native"
    assert result["handler"] == "excel"


def test_text_routes_native(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hi", encoding="utf-8")
    assert classify(path)["route"] == "native"


def test_image_routes_ocr(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"placeholder")
    assert classify(path)["route"] == "ocr"


def test_unknown_routes_manual(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"placeholder")
    assert classify(path)["route"] == "manual"


def test_scanned_pdf_routes_ocr(tmp_path):
    # 无字体 + DCTDecode + 大体积 → 判扫描
    data = b"%PDF-1.4\n/Type /Page\n/XObject /Image /DCTDecode\n" + b"\x00" * 300_000
    path = tmp_path / "scan.pdf"
    path.write_bytes(data)
    result = classify(path)
    assert result["route"] == "ocr"
    assert result["handler"] == "pdf_scan"


def test_text_pdf_routes_native(tmp_path):
    # 有字体 + 小体积 + 无图像滤镜 → 判文本层
    data = b"%PDF-1.4\n/Type /Page\n/Font /Helvetica\nBT (hello) Tj ET\n"
    path = tmp_path / "text.pdf"
    path.write_bytes(data)
    result = classify(path)
    assert result["route"] == "native"
    assert result["handler"] == "pdf_text"


def test_text_pdf_with_large_embedded_image_routes_native(tmp_path):
    # 回归：有字体（文本层）但单页大 + 含图（电子证照 / 盖章场景）→ 必须判 native。
    # 历史 bug：kb/page > 200 阈值会把这类可直读电子文档误判成扫描件、白送 OCR。
    data = (
        b"%PDF-1.4\n/Type /Page\n/Font /Helvetica\nBT (filing) Tj ET\n/DCTDecode\n"
        + b"\x00" * 300_000
    )
    path = tmp_path / "filing.pdf"
    path.write_bytes(data)
    result = classify(path)
    assert result["route"] == "native"
    assert result["handler"] == "pdf_text"


def test_mixed_pdf_flagged_but_routes_native(tmp_path):
    # 有字体(文本层) + 含图像滤镜(扫描/盖章页) → 整体判 native pdf_text，但标记 mixed_pdf=True，
    # 供 pipeline 据空白页计数决定是否整份转云 OCR 补回扫描页（张謇 400 页投标画像）。
    data = (
        b"%PDF-1.4\n/Type /Page\n/Font /Helvetica\nBT (text) Tj ET\n/DCTDecode\n" + b"\x00" * 5000
    )
    path = tmp_path / "mixed.pdf"
    path.write_bytes(data)
    result = classify(path)
    assert result["route"] == "native"
    assert result["handler"] == "pdf_text"
    assert result["mixed_pdf"] is True


def test_pure_text_pdf_not_mixed(tmp_path):
    # 有字体 + 无图像滤镜 → mixed_pdf=False（纯数字 PDF，无扫描页可补）。
    data = b"%PDF-1.4\n/Type /Page\n/Font /Helvetica\nBT (hello) Tj ET\n"
    path = tmp_path / "text.pdf"
    path.write_bytes(data)
    result = classify(path)
    assert result["mixed_pdf"] is False


def test_text_docx_routes_native(tmp_path):
    # 正文文字充足、无嵌入图 → 文本型
    path = tmp_path / "text.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<w:p>" + "合同付款条款" * 50 + "</w:p>")
    result = classify(path)
    assert result["route"] == "native"
    assert result["handler"] == "word"


def test_scanned_docx_routes_ocr(tmp_path):
    # 正文近空 + 含嵌入图 → 图片/扫描型
    path = tmp_path / "scan.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<w:p></w:p>")
        archive.writestr("word/media/image1.png", b"\x89PNG")
    result = classify(path)
    assert result["route"] == "ocr"
    assert result["handler"] == "word_scan"
