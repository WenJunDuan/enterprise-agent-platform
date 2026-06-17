"""server.ocr.pipeline 组装单测：识别底稿渲染对 pages 两种语义的处理。

回归锁：native 文件产物带 page_count(int)，不能被当成 OCR 的 pages(list) 迭代。
"""

from __future__ import annotations

import json

import jsonschema

from server.ocr.pipeline import build_extraction_block, extract_one
from server.platform.paths import PROJECT_ROOT

_EXTRACT_RESULT_SCHEMA = json.loads(
    (PROJECT_ROOT / ".claude" / "contracts" / "ocr" / "extract-result.schema.json").read_text(
        encoding="utf-8"
    )
)


def test_build_block_native_pdf_with_page_count_does_not_crash():
    # native PDF 产物含 page_count(int)；旧代码误把它当 OCR 的 pages(list) 迭代 → TypeError。
    results = [
        {
            "path": "a.pdf",
            "kind": "pdf_text",
            "route": "native",
            "page_count": 2,
            "blocks": ["文本层内容"],
        }
    ]
    block = build_extraction_block(results)
    assert "文本层内容" in block
    assert "a.pdf" in block


def test_build_block_renders_ocr_pages_list():
    results = [
        {
            "path": "b.pdf",
            "kind": "ocr",
            "route": "ocr",
            "page_count": 1,
            "pages": [{"markdown": "第一页内容"}],
        }
    ]
    block = build_extraction_block(results)
    assert "第一页内容" in block


def test_build_block_renders_excel_tables():
    results = [
        {
            "path": "c.xlsx",
            "kind": "excel",
            "route": "native",
            "tables": [{"name": "Sheet1", "rows": [["列A", "列B"], ["1", "2"]]}],
        }
    ]
    block = build_extraction_block(results)
    assert "列A" in block
    assert "Sheet1" in block


def test_build_block_marks_error_item():
    results = [{"path": "d.pdf", "kind": "error", "route": "manual", "error": "缺少 paddleocr"}]
    block = build_extraction_block(results)
    assert "识别失败" in block
    assert "缺少 paddleocr" in block


def test_native_text_item_conforms_to_extract_result_schema(tmp_path):
    # 回归锁：真实 pipeline 产物（含分诊字段 container/handler/page_count/...）必须符合契约。
    path = tmp_path / "note.txt"
    path.write_text("识别内容", encoding="utf-8")
    item = extract_one(path)
    jsonschema.validate(item, _EXTRACT_RESULT_SCHEMA)


def test_manual_kind_item_conforms_to_extract_result_schema(tmp_path):
    # kind=manual/error 也必须在 schema enum 内（历史 schema 漏了这两个值）。
    path = tmp_path / "blob.bin"
    path.write_bytes(b"opaque")
    item = extract_one(path)
    assert item["kind"] == "manual"
    jsonschema.validate(item, _EXTRACT_RESULT_SCHEMA)


def test_build_block_marks_truncation(monkeypatch):
    # 超长 body 截断时必须显式标记（不静默丢尾部，防砸合同付款节点硬指标）。
    import server.ocr.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "MAX_FILE_BLOCK_CHARS", 50)
    results = [{"path": "big.txt", "kind": "text", "route": "native", "blocks": ["x" * 300]}]
    block = pipeline_mod.build_extraction_block(results)
    assert "已截断" in block
    assert "needs_review" in block


def test_build_block_no_truncation_marker_when_short():
    results = [{"path": "s.txt", "kind": "text", "route": "native", "blocks": ["短内容"]}]
    block = build_extraction_block(results)
    assert "已截断" not in block


def test_extract_one_font_only_pdf_falls_back_to_ocr(tmp_path, monkeypatch):
    # codex round 3：font-only 扫描 PDF（有字体但 native 抽空）应回退 OCR，而非返回空 native。
    import server.ocr.pipeline as pipeline_mod
    from server.ocr import OcrError

    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda p: {
            "path": str(p),
            "route": "native",
            "handler": "pdf_text",
            "kind": "pdf_text",
            "container": "pdf",
        },
    )
    monkeypatch.setattr(pipeline_mod, "native_read", lambda p: {"kind": "pdf_text", "blocks": ["", "   "]})
    state = {"recognize_called": False}

    def fake_recognize(p):
        state["recognize_called"] = True
        raise OcrError("no engine")

    monkeypatch.setattr(pipeline_mod, "recognize", fake_recognize)

    result = pipeline_mod.extract_one(tmp_path / "x.pdf")
    assert state["recognize_called"]  # native 抽空确实回退到 OCR
    assert result["kind"] == "error"  # 本机无引擎 → 归一 error（per-file 隔离）
