"""H2 页锚溯源 · 表格带锚（KD4，AC3）。

旧行为：``read_pdf_text`` 收集 tables 时丢掉页号，``_render_body`` 把表格文本无锚拼在底稿**末尾**
→ 模型按"最近锚点"把任意页的表格引成最后一页，且回查闸判 confirmed（错页畅通进结论）。

本机无 pymupdf（OCR extra 未装）→ 用**假 fitz 模块**驱动 ``read_pdf_text`` 的真实循环逻辑，
被测对象是"页号有没有被保留并挂到所属页锚下"，不是 pymupdf 本身。
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from server.ocr import native, pipeline


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def extract(self):
        return self._rows


class _FakeFound:
    def __init__(self, tables):
        self.tables = tables


class _FakePage:
    def __init__(self, text, tables):
        self._text = text
        self._tables = tables

    def get_text(self, _mode, sort=True):
        return self._text

    def find_tables(self):
        return _FakeFound([_FakeTable(rows) for rows in self._tables])


class _FakeDocument:
    def __init__(self, pages):
        self._pages = pages
        self.page_count = len(pages)

    def __iter__(self):
        return iter(self._pages)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


@pytest.fixture
def fake_fitz(monkeypatch):
    """注入假 fitz 模块；页文本与页内表格由测试指定。"""

    def _install(pages: list[tuple[str, list]]):
        document = _FakeDocument([_FakePage(text, tables) for text, tables in pages])
        module = types.ModuleType("fitz")
        module.open = lambda _path: document  # noqa: A003 - 对齐 fitz 真实 API 名
        monkeypatch.setitem(sys.modules, "fitz", module)
        return document

    return _install


@contextmanager
def _no_lock():
    yield


def test_read_pdf_text_keeps_table_page_numbers(tmp_path, fake_fitz, monkeypatch):
    fake_fitz(
        [
            ("第一页正文", []),
            ("第二页正文", [[["项目", "金额"], ["路基工程", "1,200.00"]]]),
            ("第三页正文", []),
        ]
    )
    monkeypatch.setattr(native, "FITZ_LOCK", _no_lock())
    result = native.read_pdf_text(tmp_path / "a.pdf")

    assert [table["page"] for table in result["tables"]] == [2]


def test_table_text_renders_under_its_own_page_anchor(tmp_path, fake_fitz, monkeypatch):
    """AC3：中部页表格出现在所属页锚之下，底稿末尾无游离无锚表格段。"""
    fake_fitz(
        [
            ("第一页正文", []),
            ("第二页正文", [[["项目", "金额"], ["路基工程", "1,200.00"]]]),
            ("第三页正文", []),
        ]
    )
    monkeypatch.setattr(native, "FITZ_LOCK", _no_lock())
    result = {"kind": "pdf_text", "route": "native", **native.read_pdf_text(tmp_path / "a.pdf")}

    body = pipeline._render_body(result)
    second = body.index("【第 2 页】")
    third = body.index("【第 3 页】")
    assert second < body.index("路基工程") < third
    # 末尾不再有游离表格段：最后一个锚之后只有第三页正文
    assert body[third:].strip().endswith("第三页正文")


def test_table_on_blank_scan_page_still_gets_its_anchor(tmp_path, fake_fitz, monkeypatch):
    """纯表格页（正文为空）也要出锚，否则表格会挂到上一页。"""
    fake_fitz(
        [
            ("第一页正文", []),
            ("", [[["规费", "300.00"]]]),
        ]
    )
    monkeypatch.setattr(native, "FITZ_LOCK", _no_lock())
    result = {"kind": "pdf_text", "route": "native", **native.read_pdf_text(tmp_path / "a.pdf")}

    body = pipeline._render_body(result)
    assert "【第 2 页】\n规费\t300.00" in body


def test_converted_pdf_tables_use_converted_anchor(tmp_path, fake_fitz, monkeypatch):
    fake_fitz([("正文", []), ("", [[["合计", "9.00"]]])])
    monkeypatch.setattr(native, "FITZ_LOCK", _no_lock())
    result = {"kind": "pdf_text", "route": "convert", **native.read_pdf_text(tmp_path / "a.pdf")}

    body = pipeline._render_body(result)
    assert "【转换稿第 2 页】\n合计\t9.00" in body


def test_tables_without_page_still_render_at_tail(tmp_path):
    """word/excel 等无页结构的表格（table 无 page 键）仍拼尾，行为不变。"""
    body = pipeline._render_body(
        {
            "kind": "word",
            "route": "native",
            "blocks": ["段落一"],
            "tables": [{"rows": [["甲", "乙"]]}],
        }
    )
    assert body == "段落一\n\n甲\t乙"


def test_boq_summary_reads_table_amount_at_its_real_page(tmp_path, fake_fitz, monkeypatch):
    """回归：表格金额进 BOQ 摘要时带的是所属页，不是末页（page-carry 不再吃无锚尾段）。"""
    fake_fitz(
        [
            ("投标总价（小写）：1,234,567.89", []),
            ("", [[["分部分项合计", "1,000,000.00"]]]),
            ("投标人：某某公司", []),
        ]
    )
    monkeypatch.setattr(native, "FITZ_LOCK", _no_lock())
    result = {"kind": "pdf_text", "route": "native", **native.read_pdf_text(tmp_path / "a.pdf")}

    from server.ocr.boq import extract_boq_summary

    summary = extract_boq_summary("已标价工程量清单.pdf", pipeline._render_body(result))
    assert summary is not None
    assert "【第 2 页】" in summary
