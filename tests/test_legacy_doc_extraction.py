"""旧版 ``.doc`` 抽取阶梯回归（2026-08-15 事故）。

事故：真 OLE2 ``.doc`` 招标文件在部署机上抽出 0 字节底稿 → criteria=0 → 评标产出
看似正常的 manual_review。根因两条：① `read_legacy_word` 从不尝试 LibreOffice，而
catdoc/antiword 对该文件皆产不出内容（LibreOffice 实测成功）；② 硬写 ``tables: []``，
而招标文件的评分标准正在 Word 表格里。

这些用例锁住修复后的阶梯：LibreOffice(带表格) → 文本转换器 → 二进制兜底 → 可见错误。
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from server.ocr import OcrDependencyError, OcrError, native


def _fake_docx_conversion(payload: dict):
    """替身：让 convert_office_to_pdf 成功并让读取器返回 payload。

    2026-08-17 更新：主路径已改为**先转 PDF**——`read_pdf_text` 自带 `find_tables`，
    同样拿得到表格，还多拿到证据链必需的真实页号（转 docx 拿不到页号，实测底稿 0 页锚）。
    故不再断言 target=="docx"；本替身对两种目标都放行，read_pdf_text/read_word 都返回同一
    payload，以便复用既有断言检验"表格必须透传"这一意图。
    """

    @contextlib.contextmanager
    def _convert(path: Path, *, target: str = "pdf"):
        yield path

    return _convert, lambda _path, **_kw: payload


def test_legacy_doc_prefers_libreoffice_and_keeps_tables(monkeypatch, tmp_path):
    """LibreOffice 路径可用时优先走它，且表格必须保留（评分标准就在表里）。"""
    payload = {
        "kind": "word",
        "blocks": ["第四章 评审方法和程序"],
        "tables": [{"rows": [["评审因素", "分值"], ["报价", "30"]]}],
    }
    convert, read_word = _fake_docx_conversion(payload)
    monkeypatch.setattr(native, "convert_office_to_pdf", convert)
    monkeypatch.setattr(native, "read_word", read_word)
    monkeypatch.setattr(native, "read_pdf_text", read_word)
    called: list[list[str]] = []
    monkeypatch.setattr(native, "_run_text_converter", lambda argv: called.append(argv) or None)

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    result = native.read_legacy_word(doc)

    assert result["tables"] == payload["tables"], "表格必须透传，不能像修复前那样丢成 []"
    assert result["blocks"] == payload["blocks"]
    assert called == [], "LibreOffice 成功时不应再调 catdoc/antiword"


def test_legacy_doc_falls_back_to_text_converters_when_libreoffice_unavailable(
    monkeypatch, tmp_path
):
    """LibreOffice 缺失/失败时降级链仍在——防御纵深，不做减法。"""

    @contextlib.contextmanager
    def _no_office(path: Path, *, target: str = "pdf"):
        raise OcrDependencyError("LibreOffice command is not installed")
        yield path  # pragma: no cover - 契约占位

    monkeypatch.setattr(native, "convert_office_to_pdf", _no_office)
    monkeypatch.setattr(native, "_run_text_converter", lambda argv: "catdoc 抽出的正文")

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    result = native.read_legacy_word(doc)

    assert result["blocks"] == ["catdoc 抽出的正文"]
    assert result["tables"] == [], "纯文本转换器本就拿不到表格，如实为空"


def test_legacy_doc_ignores_empty_libreoffice_result(monkeypatch, tmp_path):
    """LibreOffice 转换成功但产物无内容时，必须继续降级而不是返回空。"""
    convert, _ = _fake_docx_conversion({"kind": "word", "blocks": [], "tables": []})
    monkeypatch.setattr(native, "convert_office_to_pdf", convert)
    empty = lambda _p, **_kw: {"kind": "word", "blocks": [], "tables": []}  # noqa: E731
    monkeypatch.setattr(native, "read_word", empty)
    monkeypatch.setattr(native, "read_pdf_text", empty)  # 主路径先转 PDF，同样要空产物
    monkeypatch.setattr(native, "_run_text_converter", lambda argv: "兜底正文")

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    assert native.read_legacy_word(doc)["blocks"] == ["兜底正文"]


def test_legacy_doc_all_paths_empty_raises_instead_of_silent_empty(monkeypatch, tmp_path):
    """全阶梯失败必须显式报错——静默空底稿会让评标在空输入上产出 manual_review。"""

    @contextlib.contextmanager
    def _no_office(path: Path, *, target: str = "pdf"):
        raise OcrDependencyError("LibreOffice command is not installed")
        yield path  # pragma: no cover - 契约占位

    monkeypatch.setattr(native, "convert_office_to_pdf", _no_office)
    monkeypatch.setattr(native, "_run_text_converter", lambda argv: None)
    monkeypatch.setattr(native, "_read_legacy_word_utf16_fallback", lambda _p: "")

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    with pytest.raises(OcrError, match="produced no text"):
        native.read_legacy_word(doc)
