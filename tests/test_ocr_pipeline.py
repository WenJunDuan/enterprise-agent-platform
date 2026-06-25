"""server.ocr.pipeline 组装单测：识别底稿渲染对 pages 两种语义的处理。

回归锁：native 文件产物带 page_count(int)，不能被当成 OCR 的 pages(list) 迭代。
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from server.ocr.pipeline import build_extraction_block, extract_one
from server.platform.paths import PROJECT_ROOT

_EXTRACT_RESULT_SCHEMA = json.loads(
    (PROJECT_ROOT / ".claude" / "contracts" / "ocr" / "extract-result.schema.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(autouse=True)
def _disable_ocr_cache(monkeypatch):
    """默认禁用 OCR 缓存，避免测试写 data/ocr-cache；缓存专项测试自行 monkeypatch 启用。"""
    import server.ocr.cache as cache

    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", False)


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


def test_render_body_adds_page_anchors_ocr():
    """G2：OCR 页底稿带页锚点【第N页】，模型可据此精确引页。"""
    from server.ocr.pipeline import _render_body

    body = _render_body(
        {"kind": "ocr", "pages": [{"markdown": "甲页"}, {"markdown": "乙页", "page_number": 2}]}
    )
    assert "【第 1 页】" in body and "甲页" in body
    assert "【第 2 页】" in body and "乙页" in body


def test_render_body_adds_page_anchors_pdf_text():
    """G2：native pdf_text blocks 一页一项 → 按页打锚点，跳空页保留页号。"""
    from server.ocr.pipeline import _render_body

    body = _render_body({"kind": "pdf_text", "blocks": ["首页正文", "   ", "第三页正文"]})
    assert "【第 1 页】\n首页正文" in body
    assert "【第 2 页】" not in body  # 空白页跳过
    assert "【第 3 页】\n第三页正文" in body  # 页号仍对应真实页


def test_render_body_no_anchors_for_word_blocks():
    """word/text 的 blocks 非页结构 → 不打页锚点（避免误导页号）。"""
    from server.ocr.pipeline import _render_body

    body = _render_body({"kind": "word", "blocks": ["段落一", "段落二"]})
    assert "【第" not in body
    assert "段落一" in body and "段落二" in body


def test_read_legacy_word_utf16_fallback_extracts_text(tmp_path, monkeypatch):
    import server.ocr.native as native_mod

    monkeypatch.setattr(native_mod, "_run_text_converter", lambda argv: None)
    path = tmp_path / "公开招标文件.doc"
    path.write_bytes(
        b"\xd0\xcf\x11\xe0"
        + "张謇企业家学院网络学院直播间建设项目\n评分点名称\n价格分：30分".encode(
            "utf-16le"
        )
    )

    result = native_mod.read_legacy_word(path)
    text = "\n".join(result["blocks"])
    assert result["kind"] == "word"
    assert "评分点名称" in text
    assert "价格分：30分" in text


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


# ── OCR 目的性（block3）：评标场景注入 purpose，audit 通用路径不受污染 ─────────


def test_ocr_purpose_injected_into_openai_prompt(monkeypatch, tmp_path):
    """评标 OCR 目的注入：purpose 追加进 OpenAI-compatible 识别 prompt（治"OCR 无目的性"）。"""
    import server.ocr.engine as eng

    monkeypatch.setattr(eng, "OCR_VL_SERVER_URL", "http://ocr.local")
    monkeypatch.setattr(eng, "OCR_VL_MODEL_NAME", "paddle-vl")
    captured: dict = {}

    def fake_call(*, data_url, prompt):
        captured["prompt"] = prompt
        return "识别markdown"

    monkeypatch.setattr(eng, "_call_openai_compatible_vlm", fake_call)
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    eng._recognize_via_openai_compatible(img, purpose="完整还原扣分细则表格")
    assert "完整还原扣分细则表格" in captured["prompt"]
    assert "Extract all visible document text" in captured["prompt"]  # 通用指令保留


def test_audit_ocr_path_has_no_tender_purpose(monkeypatch, tmp_path):
    """无 purpose（audit/通用路径）→ prompt 不含评标文案，防域污染（critic F2）。"""
    import server.ocr.engine as eng

    monkeypatch.setattr(eng, "OCR_VL_SERVER_URL", "http://ocr.local")
    monkeypatch.setattr(eng, "OCR_VL_MODEL_NAME", "paddle-vl")
    captured: dict = {}

    def fake_call(*, data_url, prompt):
        captured["prompt"] = prompt
        return "识别markdown"

    monkeypatch.setattr(eng, "_call_openai_compatible_vlm", fake_call)
    img = tmp_path / "invoice.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    eng._recognize_via_openai_compatible(img)  # 无 purpose（audit/通用路径）
    assert captured["prompt"] == "Extract all visible document text. Return concise markdown only."
    assert "评标" not in captured["prompt"] and "招投标" not in captured["prompt"]


# ── P1 OCR 结果缓存（按文件内容 sha256，格式无关，重评/重试不重复识别）─────────


def test_ocr_cache_roundtrip(tmp_path, monkeypatch):
    """put 后同文件+同 purpose get 命中；不同 purpose / 内容变 → 不命中。"""
    import server.ocr.cache as cache

    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "ocr-cache")
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-fake-content")
    result = {"kind": "ocr", "pages": [{"markdown": "识别内容"}]}

    assert cache.get_cached(doc, purpose="评标") is None  # 未命中
    cache.put_cached(doc, purpose="评标", result=result)
    hit = cache.get_cached(doc, purpose="评标")
    assert hit is not None and hit["pages"][0]["markdown"] == "识别内容"  # 命中
    assert cache.get_cached(doc, purpose="别的目的") is None  # 不同 purpose 不复用
    doc.write_bytes(b"%PDF-changed")
    assert cache.get_cached(doc, purpose="评标") is None  # 内容变 → 失效


def test_extract_one_hits_cache_second_time(tmp_path, monkeypatch):
    """extract_one 第二次同文件走缓存，不再调底层识别。"""
    import server.ocr.cache as cache
    import server.ocr.pipeline as pipeline_mod

    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "c")
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)
    calls = {"n": 0}
    real_raw = pipeline_mod._extract_one_raw

    def counting_raw(path, **kwargs):
        calls["n"] += 1
        return real_raw(path, **kwargs)

    monkeypatch.setattr(pipeline_mod, "_extract_one_raw", counting_raw)
    note = tmp_path / "note.txt"
    note.write_text("内容", encoding="utf-8")
    r1 = pipeline_mod.extract_one(note)
    r2 = pipeline_mod.extract_one(note)
    assert calls["n"] == 1  # 第二次命中缓存，不再调底层识别
    assert r1["kind"] == r2["kind"] == "text"


def test_ocr_cache_write_failure_does_not_abort(tmp_path, monkeypatch):
    """缓存写失败（如 Paddle layout 非 JSON 对象）不向上抛，extract_one 仍返回识别结果（codex P1-3）。"""
    import server.ocr.cache as cache
    import server.ocr.pipeline as pipeline_mod

    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "c")
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)

    def boom(*_args, **_kwargs):
        raise TypeError("not JSON serializable")

    monkeypatch.setattr(cache.json, "dump", boom)  # 模拟 json.dump 抛 TypeError
    note = tmp_path / "n.txt"
    note.write_text("内容", encoding="utf-8")
    result = pipeline_mod.extract_one(note)  # 不应抛（put_cached 吞掉写错误）
    assert result["kind"] == "text"


def test_ocr_cache_run_seal_key_separation(tmp_path, monkeypatch):
    """run_seal 不同 → 缓存键不同，不复用（codex P2-10）。"""
    import server.ocr.cache as cache

    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "c")
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)
    doc = tmp_path / "d.pdf"
    doc.write_bytes(b"%PDF-x")
    cache.put_cached(doc, run_seal=False, result={"kind": "ocr"})
    assert cache.get_cached(doc, run_seal=False) is not None
    assert cache.get_cached(doc, run_seal=True) is None  # run_seal 不同不复用


def test_ocr_max_workers_clamps_invalid(monkeypatch):
    """OCR_MAX_WORKERS 非法/0/负 → 回退默认或 clamp ≥1（codex P2-5）。"""
    import server.ocr.pipeline as pipeline_mod

    monkeypatch.setenv("OCR_MAX_WORKERS", "0")
    assert pipeline_mod._ocr_max_workers() == 1
    monkeypatch.setenv("OCR_MAX_WORKERS", "-3")
    assert pipeline_mod._ocr_max_workers() == 1
    monkeypatch.setenv("OCR_MAX_WORKERS", "abc")
    assert pipeline_mod._ocr_max_workers() == 6  # R4-B：默认 4→6
    monkeypatch.setenv("OCR_MAX_WORKERS", "8")
    assert pipeline_mod._ocr_max_workers() == 8


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

    def fake_recognize(p, *, purpose=None):
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


def test_read_pdf_text_skips_find_tables_for_large_pdf(tmp_path, monkeypatch):
    # R3-perf：超大 PDF（页数 > 上限）跳过逐页 find_tables（治 8417 页 BOQ 324s 瓶颈），
    # 仍保留 blocks 文本。用 page.find_tables 被 patch 计数验证"未调用"。
    import fitz

    import server.ocr.native as native_mod
    from server.ocr.native import read_pdf_text

    pdf = tmp_path / "big.pdf"
    doc = fitz.open()
    for _ in range(4):
        doc.new_page().insert_text((72, 72), "投标总价 123456.00")
    doc.save(str(pdf))
    doc.close()

    monkeypatch.setattr(native_mod, "_find_tables_max_pages", lambda: 2)  # 4 页 > 2 → 跳过
    calls = {"n": 0}
    orig = fitz.Page.find_tables

    def _counting(self, *a, **k):
        calls["n"] += 1
        return orig(self, *a, **k)

    monkeypatch.setattr(fitz.Page, "find_tables", _counting)
    result = read_pdf_text(pdf)
    assert calls["n"] == 0  # 大 PDF 完全不调 find_tables
    assert result["tables"] == []
    assert any("123456.00" in b for b in result["blocks"])  # blocks 文本仍在


def test_read_pdf_text_runs_find_tables_for_small_pdf(tmp_path, monkeypatch):
    # 普通小 PDF（≤ 上限）照常 find_tables（不退化）。
    import fitz

    import server.ocr.native as native_mod
    from server.ocr.native import read_pdf_text

    pdf = tmp_path / "small.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "发票 999")
    doc.save(str(pdf))
    doc.close()

    monkeypatch.setattr(native_mod, "_find_tables_max_pages", lambda: 500)
    calls = {"n": 0}
    orig = fitz.Page.find_tables

    def _counting(self, *a, **k):
        calls["n"] += 1
        return orig(self, *a, **k)

    monkeypatch.setattr(fitz.Page, "find_tables", _counting)
    read_pdf_text(pdf)
    assert calls["n"] == 1  # 1 页 → find_tables 调用 1 次


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


# ═════════════════════════════════════════════════════════════════════════════
# 线上 PaddleOCR-VL 云路径（OCR_CLOUD=1）：jsonl 解析 + 协议路由
# ═════════════════════════════════════════════════════════════════════════════


def test_parse_cloud_jsonl_extracts_text_and_min_confidence():
    from server.ocr.engine import _parse_cloud_jsonl

    jsonl = json.dumps(
        {
            "result": {
                "layoutParsingResults": [
                    {
                        "markdown": {"text": "发票抬头 XX公司"},
                        "prunedResult": [{"score": 0.97}, {"score": 0.55}],
                    }
                ]
            }
        }
    )
    pages = _parse_cloud_jsonl(jsonl)
    assert len(pages) == 1
    assert "XX公司" in pages[0]["markdown"]
    assert pages[0]["confidence"] == 0.55  # 取最低块 → 喂 file_clarity


def test_parse_cloud_jsonl_skips_blank_and_handles_no_score():
    from server.ocr.engine import _parse_cloud_jsonl

    jsonl = "\n".join(
        [
            "",
            json.dumps({"result": {"layoutParsingResults": [{"markdown": {"text": "无版面"}}]}}),
        ]
    )
    pages = _parse_cloud_jsonl(jsonl)
    assert len(pages) == 1
    assert pages[0]["confidence"] is None  # 无 score → None → file_clarity=unknown


def test_recognize_routes_to_cloud_when_ocr_cloud(monkeypatch):
    from pathlib import Path as _Path

    import server.ocr.engine as engine_mod

    calls = {}
    monkeypatch.setattr(engine_mod, "OCR_CLOUD", True)
    monkeypatch.setattr(
        engine_mod,
        "_recognize_via_paddle_cloud",
        lambda p, *, purpose=None: calls.setdefault("cloud", True) or {"kind": "ocr", "pages": []},
    )
    engine_mod.recognize(_Path("x.pdf"))
    assert calls.get("cloud")


# ═════════════════════════════════════════════════════════════════════════════
# P4：OCR 预处理底稿注入 audit / tender
# ═════════════════════════════════════════════════════════════════════════════


def test_ocr_preprocess_block_returns_draft(tmp_path):
    from server.ocr.pipeline import ocr_preprocess_block

    (tmp_path / "note.txt").write_text("发票号 INV-001 金额 1200", encoding="utf-8")
    block = ocr_preprocess_block(str(tmp_path))
    assert block and "INV-001" in block


def test_ocr_preprocess_block_disabled_returns_none(tmp_path, monkeypatch):
    import server.ocr.pipeline as pipe

    monkeypatch.setattr(pipe, "OCR_PREPROCESS", False)
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    assert pipe.ocr_preprocess_block(str(tmp_path)) is None


def test_ocr_preprocess_block_skip_filters_file(tmp_path):
    from server.ocr.pipeline import ocr_preprocess_block

    (tmp_path / "audit-request.json").write_text('{"a":1}', encoding="utf-8")
    (tmp_path / "inv.txt").write_text("INV-XYZ", encoding="utf-8")
    block = ocr_preprocess_block(str(tmp_path), skip={"audit-request.json"})
    assert block and "INV-XYZ" in block and "audit-request.json" not in block


def test_ocr_preprocess_block_failure_returns_none(tmp_path, monkeypatch):
    # 降级铁律：OCR 失败绝不拖垮审核/评标 → None（回落模型自己 Read）。
    import server.ocr.pipeline as pipe

    def boom(_d):
        raise RuntimeError("engine down")

    monkeypatch.setattr(pipe, "extract_dir", boom)
    assert pipe.ocr_preprocess_block(str(tmp_path)) is None


def test_build_command_prompt_appends_context():
    from server.common.command_adapter import build_command_prompt

    p = build_command_prompt("tender-evaluate", "data/x", context="底稿内容")
    assert p.startswith("/tender-evaluate data/x")
    assert "底稿内容" in p


def test_build_command_prompt_no_context_unchanged():
    from server.common.command_adapter import build_command_prompt

    assert build_command_prompt("tender-evaluate", "data/x") == "/tender-evaluate data/x"


def test_build_inline_audit_prompt_injects_ocr_block(tmp_path):
    from server.audit.runner import build_inline_audit_prompt

    p = build_inline_audit_prompt(str(tmp_path), ocr_block="发票OCR底稿XYZ")
    assert "发票OCR底稿XYZ" in p
    assert "OCR/直读底稿" in p


def test_build_inline_audit_prompt_no_ocr_block_omits_section(tmp_path):
    from server.audit.runner import build_inline_audit_prompt

    assert "OCR/直读底稿" not in build_inline_audit_prompt(str(tmp_path))


# ── R2: BOQ 感知抽取 + 截断策略 ────────────────────────────────────────────────


def _big_boq_blocks(n_filler_pages: int = 80) -> list[str]:
    """合成大 BOQ：扉页(总价) + 多页填充行项，逐页一 block（_render_body 按页加锚点）。"""
    cover = (
        "1. 扉页\n投标总价(小写):\n381574199.97\n(大写):\n"
        "叁亿捌仟壹佰伍拾柒万肆仟壹佰玖拾玖元玖角柒分\n投标人:\n二建"
    )
    filler = [
        f"序号\n项目编码\n04050100{i:04d}\n项目名称\n塑料管\n综合单价\n258.56\n合价\n69358.72\n"
        + ("某项目特征描述很长 " * 50)
        for i in range(n_filler_pages)
    ]
    tail = "分部分项合计\n3012424.9\n单价措施合计\n17765.51\n合计\n3030190.41"
    return [cover, *filler, tail]


def test_build_block_boq_emits_summary(monkeypatch):
    import server.ocr.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "MAX_FILE_BLOCK_CHARS", 5000)
    results = [
        {
            "path": "1.05 已标价工程量清单.pdf",
            "kind": "pdf_text",
            "route": "native",
            "blocks": _big_boq_blocks(),
        }
    ]
    block = pipeline_mod.build_extraction_block(results)
    assert "BOQ 结构化摘要" in block
    assert "投标总价: 381574199.97" in block  # 总价提升为结构化字段，非淹没/被截
    assert "已截断" not in block  # 走摘要而非截断
    assert len(block) < 30000  # 远小于原始全量


def test_build_block_large_non_boq_default_head_truncate(monkeypatch):
    import server.ocr.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "MAX_FILE_BLOCK_CHARS", 100)
    monkeypatch.delenv("OCR_TRUNCATE_HEAD_TAIL", raising=False)
    body = "HEAD_" + ("a" * 300) + "_TAILMARKER"
    results = [{"path": "长合同.txt", "kind": "text", "route": "native", "blocks": [body]}]
    block = pipeline_mod.build_extraction_block(results)
    assert "已截断" in block
    assert "HEAD_" in block
    assert "_TAILMARKER" not in block  # 默认头截 → 尾部丢（与现状一致）


def test_build_block_large_non_boq_head_tail_when_enabled(monkeypatch):
    import server.ocr.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "MAX_FILE_BLOCK_CHARS", 100)
    monkeypatch.setenv("OCR_TRUNCATE_HEAD_TAIL", "1")
    body = "HEAD_" + ("a" * 300) + "_TAILMARKER"
    results = [{"path": "长合同.txt", "kind": "text", "route": "native", "blocks": [body]}]
    block = pipeline_mod.build_extraction_block(results)
    assert "已截断" in block
    assert "HEAD_" in block
    assert "_TAILMARKER" in block  # 首尾截 → 尾部保留


def test_build_block_boq_summary_resolvable_by_r1(monkeypatch):
    # R1×R2 协同：BOQ 摘要经 build_extraction_block 包裹后，R1 parse_corpus 解析页号 + 总价 resolved
    import server.ocr.pipeline as pipeline_mod
    from server.common.evidence_resolution import (
        CorpusIndex,
        existence_ratio,
        normalize_text,
        parse_corpus,
    )

    monkeypatch.setattr(pipeline_mod, "MAX_FILE_BLOCK_CHARS", 5000)
    results = [
        {
            "path": "1.05 已标价工程量清单.pdf",
            "kind": "pdf_text",
            "route": "native",
            "blocks": _big_boq_blocks(),
        }
    ]
    block = pipeline_mod.build_extraction_block(results)
    segs = parse_corpus(block)
    assert any(seg["page"] is not None for seg in segs)
    idx = CorpusIndex(segs)
    assert existence_ratio(normalize_text("投标总价381,574,199.97"), idx.whole_corpus) == 1.0
