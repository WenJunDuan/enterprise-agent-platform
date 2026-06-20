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


# ═════════════════════════════════════════════════════════════════════════════
# P1：pymupdf read_pdf_text + _render_body 同时渲染 blocks 和 tables
# ═════════════════════════════════════════════════════════════════════════════


def test_render_body_pdf_text_renders_both_blocks_and_tables():
    # 回归锁：pdf_text/word 同时有正文+表时，旧逻辑 tables 分支吃掉 blocks 丢正文（发票命门）。
    results = [
        {
            "path": "inv.pdf",
            "kind": "pdf_text",
            "route": "native",
            "blocks": ["发票正文说明"],
            "tables": [{"rows": [["项目", "金额"], ["住宿", "1200"]]}],
        }
    ]
    block = build_extraction_block(results)
    assert "发票正文说明" in block  # 正文不再被丢
    assert "项目" in block and "1200" in block  # 表也在


def test_read_pdf_text_uses_pymupdf(tmp_path):
    import fitz  # pymupdf

    from server.ocr.native import read_pdf_text

    pdf = tmp_path / "hello.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "发票号码 12345")
    doc.save(str(pdf))
    doc.close()

    result = read_pdf_text(pdf)
    assert result["kind"] == "pdf_text"
    assert any("12345" in b for b in result["blocks"])
    assert "tables" in result  # find_tables 字段存在（本例无表 → 空列表）


# ═════════════════════════════════════════════════════════════════════════════
# P2：file_clarity 置信度信号 + 底稿清晰度标注
# ═════════════════════════════════════════════════════════════════════════════


def test_file_clarity_native_is_clear():
    from server.ocr.pipeline import file_clarity

    assert file_clarity({"kind": "pdf_text", "route": "native", "blocks": ["x"]}) == "clear"


def test_file_clarity_error_is_failed():
    from server.ocr.pipeline import file_clarity

    assert file_clarity({"kind": "error", "error": "boom"}) == "failed"


def test_file_clarity_ocr_low_below_threshold():
    from server.ocr.pipeline import file_clarity

    result = {"kind": "ocr", "pages": [{"markdown": "糊", "confidence": 0.3}]}
    assert file_clarity(result, threshold=0.6) == "low"


def test_file_clarity_ocr_clear_above_threshold():
    from server.ocr.pipeline import file_clarity

    result = {"kind": "ocr", "pages": [{"markdown": "清", "confidence": 0.95}]}
    assert file_clarity(result, threshold=0.6) == "clear"


def test_file_clarity_ocr_unknown_without_confidence():
    # VLM 端点路径 pages 无 confidence → unknown（无法评估，不能当 clear 蒙混）。
    from server.ocr.pipeline import file_clarity

    result = {"kind": "ocr", "pages": [{"markdown": "x", "layout": []}]}
    assert file_clarity(result) == "unknown"


def test_build_block_marks_low_clarity():
    results = [
        {
            "path": "scan.pdf",
            "kind": "ocr",
            "route": "ocr",
            "pages": [{"markdown": "糊文本", "confidence": 0.2}],
        }
    ]
    block = build_extraction_block(results)
    assert "清晰度低" in block
    assert "needs_review" in block


def test_build_block_no_clarity_note_for_clear_native():
    results = [{"path": "n.txt", "kind": "text", "route": "native", "blocks": ["清晰"]}]
    block = build_extraction_block(results)
    assert "清晰度低" not in block
    assert "清晰度未知" not in block


def test_page_confidence_takes_min_block_score():
    from server.ocr.engine import _page_confidence

    assert _page_confidence([{"score": 0.9}, {"score": 0.4}, {"score": 0.8}]) == 0.4


def test_page_confidence_none_without_scores():
    from server.ocr.engine import _page_confidence

    assert _page_confidence([]) is None
    assert _page_confidence([{"text": "x"}]) is None
