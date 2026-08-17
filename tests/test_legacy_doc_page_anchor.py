"""旧版 .doc 底稿必须带页锚（2026-08-17 第二轮实跑发现）。

实跑实测：招标底稿 39,056 字、**0 个页锚**，于是证据检索返回的 `page_anchor` 全是
「页码未知」——评标要求逐条证据带 `【第N页】` 出处，回查闸也据此核验，native 直读的
`.doc` 根本满足不了。

对比：`kind=pdf_text` 走 `_render_paged_blocks`，实测 399 个页锚（`read_pdf_text` 逐页
append，页号=索引+1）。缺的只是 `.doc` 这条——它的 blocks 是段落列表，拿不到页号。
`.doc` 本来就要经 LibreOffice 转换，转 PDF 即可同时拿到**真实页号**与表格。
"""

from __future__ import annotations

from server.common.corpus import parse_page_anchor


def _anchor_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if parse_page_anchor(line))


def test_legacy_doc_result_carries_page_bearing_kind(monkeypatch, tmp_path):
    """经 LibreOffice 的 .doc 必须产出可渲染页锚的形态（kind=pdf_text + 逐页 blocks）。"""
    import contextlib

    from server.ocr import native

    pdf = tmp_path / "converted.pdf"
    pdf.write_bytes(b"%PDF-fake")

    @contextlib.contextmanager
    def _convert(path, *, target="pdf"):
        assert target == "pdf", "要拿真实页号必须转 PDF（转 docx 拿不到页号）"
        yield pdf

    monkeypatch.setattr(native, "convert_office_to_pdf", _convert)
    monkeypatch.setattr(
        native,
        "read_pdf_text",
        lambda _p, **_kw: {"kind": "pdf_text", "blocks": ["第一页正文", "第二页正文"], "tables": []},
    )

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    result = native.read_legacy_word(doc)

    assert result["kind"] == "pdf_text", "kind 决定渲染分支——word 分支不打页锚"
    assert len(result["blocks"]) == 2, "blocks 必须一页一项，渲染层据此打页号"


def test_rendered_legacy_doc_draft_has_page_anchors(monkeypatch, tmp_path):
    """端到端：渲染出的底稿真的带 【第N页】，而不只是结构上像。"""
    import contextlib

    from server.ocr import native
    from server.ocr.draft_render import render_body

    pdf = tmp_path / "converted.pdf"
    pdf.write_bytes(b"%PDF-fake")

    @contextlib.contextmanager
    def _convert(path, *, target="pdf"):
        yield pdf

    monkeypatch.setattr(native, "convert_office_to_pdf", _convert)
    monkeypatch.setattr(
        native,
        "read_pdf_text",
        lambda _p, **_kw: {"kind": "pdf_text", "blocks": ["评分标准正文", "合同条款正文"], "tables": []},
    )

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    draft = render_body(native.read_legacy_word(doc))

    assert _anchor_count(draft) == 2, f"每页一个锚点，实际渲染：{draft[:200]}"


def test_fallback_chain_still_works_without_libreoffice(monkeypatch, tmp_path):
    """LibreOffice 不可用时降级链不变——页锚是增强，不能变成新的失败点。"""
    import contextlib

    from server.ocr import OcrDependencyError, native

    @contextlib.contextmanager
    def _no_office(path, *, target="pdf"):
        raise OcrDependencyError("LibreOffice command is not installed")
        yield path  # pragma: no cover

    monkeypatch.setattr(native, "convert_office_to_pdf", _no_office)
    monkeypatch.setattr(native, "_run_text_converter", lambda _argv: "catdoc 抽出的正文")

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    result = native.read_legacy_word(doc)

    assert result["blocks"] == ["catdoc 抽出的正文"]
    assert result["kind"] == "word"
