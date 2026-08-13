"""H2 页锚溯源 · 转换稿语义贯通 + 页单元 provenance（KD1/KD2，AC1）。

核心断言：Office→PDF 转换稿的页号**不再冒充原文档页**——底稿文件头显式声明、页锚渲染成
``【转换稿第 M 页】``、页级单元带 ``artifact``/``artifact_page``/``source_file`` 且 ``page=None``。
原件路径（pdf/图片，无表格）输出与改动前逐字节一致，由 golden 文件锁死（防无关回归）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.ocr import draft_render, pipeline
from server.platform.paths import PROJECT_ROOT

_GOLDEN = PROJECT_ROOT / "tests" / "golden" / "extraction_block_original_no_tables.txt"

# golden 输入：**不含 tables**（含表格文件的输出按 KD4 有意变化，另测不入 golden，Round1-P2）。
GOLDEN_RESULTS = [
    {
        "path": "/case/招标文件.pdf",
        "kind": "pdf_text",
        "route": "native",
        "page_count": 3,
        "blocks": ["第一页正文", "   ", "第三页正文"],
    },
    {
        "path": "/case/扫描件.jpg",
        "kind": "ocr",
        "route": "ocr",
        "pages": [
            {"page_number": 1, "markdown": "扫描第一页", "confidence": 0.9},
            {"page_number": 2, "markdown": "扫描第二页", "confidence": 0.9},
        ],
    },
]


@pytest.fixture(autouse=True)
def _disable_ocr_cache(monkeypatch):
    from server.ocr import cache

    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", False)


def test_original_path_extraction_block_is_byte_identical_to_golden():
    """AC1 防回归闸：原件路径（无表格）底稿输出逐字节不变。"""
    assert pipeline.build_extraction_block(GOLDEN_RESULTS) == _GOLDEN.read_text(encoding="utf-8")


# ── KD2 转换稿语义贯通 ────────────────────────────────────────────────────────


def _converted_result() -> dict:
    """convert 路由产物：原件是 docx，下游按转换稿 PDF 直读（页号属转换稿）。"""
    return {
        "path": "/case/投标文件.docx",
        "kind": "pdf_text",
        "route": "convert",
        "downstream_route": "native",
        "converted_from": ".docx",
        "page_count": 2,
        "blocks": ["拟派项目负责人张三", "业绩一览表"],
    }


def test_converted_file_header_declares_conversion():
    block = pipeline.build_extraction_block([_converted_result()])
    header = block.splitlines()[0]
    assert "投标文件.docx" in header
    assert "route=convert" in header
    assert "已转换为PDF识别" in header
    assert "页号为转换稿页号" in header


def test_converted_body_uses_converted_page_anchor_only():
    body = draft_render.render_body(_converted_result())
    assert "【转换稿第 1 页】\n拟派项目负责人张三" in body
    assert "【转换稿第 2 页】\n业绩一览表" in body
    assert "【第 1 页】" not in body


def test_converted_ocr_pages_also_use_converted_anchor():
    """convert → 下游走 OCR（扫描版 docx 转 PDF）时锚同样是转换稿坐标。"""
    body = draft_render.render_body(
        {
            "path": "/case/投标文件.doc",
            "kind": "ocr",
            "route": "convert",
            "downstream_route": "ocr",
            "converted_from": ".doc",
            "pages": [{"page_number": 1, "markdown": "扫描正文"}],
        }
    )
    assert body.startswith("【转换稿第 1 页】")


def test_converted_block_round_trips_into_corpus_without_original_page():
    """底稿 → parse_corpus：转换稿段的可回查原文档页为 None，页号只在 artifact 坐标系。"""
    from server.common.corpus import parse_corpus

    block = pipeline.build_extraction_block([_converted_result()])
    segments = [s for s in parse_corpus(block) if s["text"].startswith("拟派")]
    assert len(segments) == 1
    assert segments[0]["artifact"] == "converted"
    assert segments[0]["artifact_page"] == 1
    assert segments[0]["page"] is None


# ── KD1 页级单元 provenance ───────────────────────────────────────────────────


def _stub_convert(monkeypatch, tmp_path: Path) -> None:
    """把 LibreOffice 转换替换成"产出一个 pdf 路径"的桩（本机无 soffice；被测的是溯源透传）。"""
    import contextlib

    converted = tmp_path / "converted.pdf"
    converted.write_bytes(b"%PDF-1.4 stub")

    @contextlib.contextmanager
    def _fake_convert(_path: Path):
        yield converted

    monkeypatch.setattr(pipeline, "convert_office_to_pdf", _fake_convert)
    monkeypatch.setattr(
        pipeline,
        "classify",
        lambda path: (
            {"route": "convert", "container": "word", "handler": "word", "page_count": None}
            if path.suffix.lower() == ".docx"
            else {"route": "native", "handler": "pdf_text", "container": "pdf", "page_count": 2}
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "native_read",
        lambda path, **_kw: {"kind": "pdf_text", "blocks": ["转换稿第一页正文", "转换稿第二页正文"]},
    )


def test_converted_units_carry_provenance_and_null_original_page(tmp_path, monkeypatch):
    """AC1/KD1：转换稿页单元 page=None、artifact=converted、artifact_page=转换稿页号。

    provenance 的 source_file 维度由既有 unit 键 ``file`` 承载（不新增同值键，DRY）。
    """
    _stub_convert(monkeypatch, tmp_path)
    source = tmp_path / "投标文件.docx"
    source.write_bytes(b"PK stub docx")

    units: list[dict] = []
    pipeline.extract_one(source, on_unit_complete=units.append)

    page_units = [u for u in units if u["artifact_page"] is not None]
    assert len(page_units) == 2
    for unit in page_units:
        assert unit["artifact"] == "converted"
        assert unit["page"] is None
        assert unit["file"] == str(source)
    assert [u["artifact_page"] for u in page_units] == [1, 2]


def test_native_pdf_units_keep_original_page_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "classify",
        lambda path: {"route": "native", "handler": "pdf_text", "container": "pdf", "page_count": 2},
    )
    monkeypatch.setattr(
        pipeline,
        "native_read",
        lambda path, **_kw: {"kind": "pdf_text", "blocks": ["第一页", "第二页"]},
    )
    source = tmp_path / "投标文件.pdf"
    source.write_bytes(b"%PDF-1.4 stub")

    units: list[dict] = []
    pipeline.extract_one(source, on_unit_complete=units.append)

    page_units = [u for u in units if u["artifact_page"] is not None]
    assert [(u["page"], u["artifact_page"], u["artifact"]) for u in page_units] == [
        (1, 1, "original"),
        (2, 2, "original"),
    ]
    assert all(u["file"] == str(source) for u in page_units)


def test_file_level_unit_carries_source_file_and_null_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "classify",
        lambda path: {"route": "native", "handler": "word", "container": "word", "page_count": None},
    )
    monkeypatch.setattr(
        pipeline, "native_read", lambda path, **_kw: {"kind": "word", "blocks": ["整份文本"]}
    )
    source = tmp_path / "说明.docx"
    source.write_bytes(b"PK stub")

    units: list[dict] = []
    pipeline.extract_one(source, on_unit_complete=units.append)

    assert len(units) == 1
    assert units[0]["page"] is None
    assert units[0]["artifact_page"] is None
    assert units[0]["artifact"] == "original"
    assert units[0]["file"] == str(source)


# ── KD1 cloud_seq 守卫 ────────────────────────────────────────────────────────


def test_cloud_page_count_mismatch_marks_page_confidence_low(tmp_path, monkeypatch):
    """云返回页数 ≠ classify 页数 → 整份 page_confidence=low（页号按序钉但降级处理）。"""
    monkeypatch.setattr(
        pipeline,
        "classify",
        lambda path: {"route": "ocr", "handler": "pdf_scan", "container": "pdf", "page_count": 5},
    )
    monkeypatch.setattr(
        pipeline,
        "_call_recognize_with_seal",
        lambda *_a, **_kw: {
            "kind": "ocr",
            "route": "ocr",
            "engine": "paddleocr-cloud",
            "page_artifact": "cloud_seq",
            "pages": [{"page_number": 1, "markdown": "只回了一页"}],
        },
    )
    source = tmp_path / "扫描件.pdf"
    source.write_bytes(b"%PDF-1.4 stub")

    result = pipeline.extract_one(source)
    assert result["page_confidence"] == "low"

    block = pipeline.build_extraction_block([result])
    assert "页号存疑" in block.splitlines()[0]


def test_cloud_page_count_match_keeps_page_confidence_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "classify",
        lambda path: {"route": "ocr", "handler": "pdf_scan", "container": "pdf", "page_count": 2},
    )
    monkeypatch.setattr(
        pipeline,
        "_call_recognize_with_seal",
        lambda *_a, **_kw: {
            "kind": "ocr",
            "route": "ocr",
            "engine": "paddleocr-cloud",
            "page_artifact": "cloud_seq",
            "pages": [
                {"page_number": 1, "markdown": "第一页"},
                {"page_number": 2, "markdown": "第二页"},
            ],
        },
    )
    source = tmp_path / "扫描件.pdf"
    source.write_bytes(b"%PDF-1.4 stub")

    result = pipeline.extract_one(source)
    assert result.get("page_confidence") is None
    assert "页号存疑" not in pipeline.build_extraction_block([result])


def test_corpus_parses_page_confidence_from_file_header():
    from server.common.corpus import CorpusIndex, parse_corpus

    block = (
        "### 文件: 扫描件.pdf (kind=ocr, route=ocr)"
        " [⚠页号存疑：云 OCR 返回 1 页，文档 5 页，页码不可靠]\n"
        "【第 1 页】\n正文内容\n"
    )
    index = CorpusIndex(parse_corpus(block))
    assert index.page_unreliable_files() == ["扫描件.pdf"]
