"""D9 streaming-ocr T1：pipeline 回调接缝单测。

覆盖 design.md/plan.md T1 验收：
- 默认 on_unit_complete=None 现行为不变（存量测试零改动全绿，见 test_ocr_pipeline*.py 不变）。
- 页级透出：native 多页 PDF → N 个页级单元，页号连续真实（页锚保真）。
- 回调锁外触发：native buffer-then-fire 回调内 FITZ_LOCK.locked()==False。
- 引擎侧 buffer-then-fire（paddle pipeline，PADDLE_LOCK）与直接触发（openai-compatible VLM）。
- 缓存命中触发一次文件级事件（from_cache=True），F3：不能因命中漏事件。
- 文件级回退：无页循环的路径（excel/word/text/OCR 失败）至少触发一次文件级事件。
- G1：units.jsonl 边车加入排除名单，重跑 extract_dir 不计入 results/单元事件。
- 并发：extract_dir 多文件并行时回调仍被正确调用（用自身锁的收集器验证）。
- F1/F2（review pass1）：native→OCR 回退路径的页级单元不重复、不过期——font-only 扫描 PDF
  回退、混合 PDF 子集增强成功、混合 PDF 子集失败回退整份 OCR 三个场景各自复现并守卫。
"""

from __future__ import annotations

import threading

import pytest

from server.ocr import OcrDependencyError
from server.ocr.locks import FITZ_LOCK, PADDLE_LOCK
from server.ocr.native import read_pdf_text
from server.ocr.pipeline import _iter_files, extract_dir, extract_one


@pytest.fixture(autouse=True)
def _disable_ocr_cache(monkeypatch):
    """默认禁用 OCR 缓存，避免测试写 data/ocr-cache；缓存专项测试自行 monkeypatch 启用。"""
    import server.ocr.cache as cache

    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", False)


class _LockedCollector:
    """线程安全的单元事件收集器（T1 并发注意：回调本身线程安全是调用方责任，这里自带锁）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.units: list[dict] = []

    def __call__(self, unit: dict) -> None:
        with self._lock:
            self.units.append(unit)


def _make_multipage_pdf(tmp_path, texts: list[str]):
    import pymupdf as fitz

    pdf = tmp_path / "multipage.pdf"
    doc = fitz.open()
    for text in texts:
        doc.new_page().insert_text((72, 72), text)
    doc.save(str(pdf))
    doc.close()
    return pdf


# ── 默认 None：现行为不变（补充性烟雾测试；存量测试文件零改动是主证据）───────


def test_extract_one_default_none_matches_extract_one_without_kwarg(tmp_path):
    note_a = tmp_path / "a.txt"
    note_a.write_text("内容A", encoding="utf-8")
    note_b = tmp_path / "b.txt"
    note_b.write_text("内容A", encoding="utf-8")

    without_kwarg = extract_one(note_a)
    with_explicit_none = extract_one(note_b, on_unit_complete=None)
    assert without_kwarg["kind"] == with_explicit_none["kind"] == "text"


# ── native 多页 PDF：页级单元，页号连续真实，回调锁外触发 ────────────────────


def test_read_pdf_text_on_page_fires_after_lock_released(tmp_path):
    pdf = _make_multipage_pdf(tmp_path, ["第一页文本 AAA", "第二页文本 BBB", "第三页文本 CCC"])
    collected: list[tuple[int, dict]] = []
    lock_states: list[bool] = []

    def on_page(page_no: int, payload: dict) -> None:
        lock_states.append(FITZ_LOCK.locked())
        collected.append((page_no, payload))

    result = read_pdf_text(pdf, on_page=on_page)

    assert result["kind"] == "pdf_text"
    assert [pn for pn, _ in collected] == [1, 2, 3]  # 页号连续真实
    assert "AAA" in collected[0][1]["text"]
    assert "BBB" in collected[1][1]["text"]
    assert "CCC" in collected[2][1]["text"]
    assert all(state is False for state in lock_states)  # 回调绝不在持有 FITZ_LOCK 时触发


def test_extract_one_native_pdf_emits_page_level_units_with_real_page_anchors(tmp_path):
    # ASCII 标记（而非中文）：默认 fitz 字体不含 CJK 字形，中文会渲染为占位符导致断言失真；
    # 页号连续性/真实性才是本测试要验的东西，标记只需在提取文本里可靠区分页。
    pdf = _make_multipage_pdf(tmp_path, ["PAGE-ONE-MARK", "PAGE-TWO-MARK"])
    collector = _LockedCollector()

    result = extract_one(pdf, on_unit_complete=collector)

    assert result["kind"] == "pdf_text"
    assert len(collector.units) == 2  # 页级单元，非退化为单一文件级
    pages = [unit["page"] for unit in collector.units]
    assert pages == [1, 2]  # 页号连续真实，不臆造
    for unit in collector.units:
        assert unit["file"] == str(pdf)
        assert unit["status"] == "ok"
        assert unit["from_cache"] is False
        assert isinstance(unit["payload"], dict)
    assert "PAGE-ONE-MARK" in collector.units[0]["payload"]["text"]
    assert "PAGE-TWO-MARK" in collector.units[1]["payload"]["text"]


# ── 引擎侧：paddle pipeline buffer-then-fire / openai-compatible 直接触发 ────


def test_paddle_pipeline_on_page_fires_after_paddle_lock_released(monkeypatch):
    import server.ocr.engine as engine_mod
    from pathlib import Path as _Path

    class _FakeResult:
        def __init__(self, markdown: str) -> None:
            self.json = {"parsing_res_list": []}
            self._markdown = {"markdown_texts": markdown}

        @property
        def markdown(self):
            return self._markdown

    monkeypatch.setattr(
        engine_mod,
        "_build_vl_pipeline",
        lambda: type("P", (), {"predict": lambda self, p: [_FakeResult("甲"), _FakeResult("乙")]})(),
    )
    collected: list[tuple[int, dict]] = []
    lock_states: list[bool] = []

    def on_page(page_no: int, payload: dict) -> None:
        lock_states.append(PADDLE_LOCK.locked())
        collected.append((page_no, payload))

    result = engine_mod._recognize_via_paddle_pipeline(_Path("x.pdf"), on_page=on_page)

    assert result["kind"] == "ocr"
    assert [pn for pn, _ in collected] == [1, 2]
    assert collected[0][1]["markdown"] == "甲"
    assert collected[1][1]["markdown"] == "乙"
    assert all(state is False for state in lock_states)  # 回调绝不在持有 PADDLE_LOCK 时触发


def test_openai_compatible_on_page_fires_per_page_directly(monkeypatch, tmp_path):
    import server.ocr.engine as engine_mod

    monkeypatch.setattr(engine_mod, "OCR_VL_SERVER_URL", "http://ocr.local")
    monkeypatch.setattr(engine_mod, "OCR_VL_MODEL_NAME", "paddle-vl")
    monkeypatch.setattr(
        engine_mod,
        "_render_pdf_pages",
        lambda p: [
            {"page_number": 1, "mime_type": "image/png", "content": b"1"},
            {"page_number": 2, "mime_type": "image/png", "content": b"2"},
        ],
    )
    monkeypatch.setattr(
        engine_mod,
        "_call_openai_compatible_vlm",
        lambda *, data_url, prompt: f"识别-{prompt[-1]}",
    )
    collected: list[tuple[int, dict]] = []
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-fake")

    result = engine_mod._recognize_via_openai_compatible(
        pdf, on_page=lambda page_no, payload: collected.append((page_no, payload))
    )

    assert result["kind"] == "ocr"
    assert [pn for pn, _ in collected] == [1, 2]  # 逐页直接触发，页号真实
    assert collected[0][1]["markdown"] and collected[1][1]["markdown"]


# ── 缓存命中：一次文件级事件，from_cache=True（F3）─────────────────────────


def test_extract_one_cache_hit_emits_single_file_level_event(tmp_path, monkeypatch):
    import server.ocr.cache as cache

    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)
    note = tmp_path / "note.txt"
    note.write_text("识别内容 XYZ", encoding="utf-8")

    extract_one(note)  # 预热缓存（首次未命中，miss 路径不受本测试断言约束）

    collector = _LockedCollector()
    result = extract_one(note, on_unit_complete=collector)

    assert result["kind"] == "text"
    assert len(collector.units) == 1  # 命中不能漏事件，也不能重复
    unit = collector.units[0]
    assert unit["from_cache"] is True
    assert unit["page"] is None  # 文件级单元
    assert unit["file"] == str(note)
    assert unit["status"] == "ok"


# ── 文件级回退：无页循环路径至少触发一次文件级事件 ──────────────────────────


def test_extract_one_non_page_native_falls_back_to_single_file_unit(tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("纯文本，无页循环", encoding="utf-8")
    collector = _LockedCollector()

    result = extract_one(note, on_unit_complete=collector)

    assert result["kind"] == "text"
    assert len(collector.units) == 1  # excel/word/text 无页级透出 → 退化为一次文件级
    unit = collector.units[0]
    assert unit["page"] is None
    assert unit["status"] == "ok"
    assert unit["from_cache"] is False
    assert unit["payload"] is result


def test_extract_one_error_path_emits_single_error_unit(tmp_path, monkeypatch):
    """损坏 / 不可读文件走 per-file 隔离 → 单一文件级 error 单元，不是静默丢事件。"""
    import server.ocr.pipeline as pipeline_mod

    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF broken")
    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda path: {
            "path": str(path),
            "container": "pdf",
            "route": "native",
            "handler": "pdf_text",
        },
    )
    monkeypatch.setattr(pipeline_mod, "native_read", lambda _path: (_ for _ in ()).throw(ValueError("bad pdf")))
    collector = _LockedCollector()

    result = extract_one(broken, on_unit_complete=collector)

    assert result["kind"] == "error"
    assert len(collector.units) == 1
    assert collector.units[0]["status"] == "error"
    assert collector.units[0]["payload"] is result


def test_partial_pages_then_fallback_failure_emits_terminal_error_unit(tmp_path, monkeypatch):
    """已发成功页后后续 OCR 失败，必须再发文件级 terminal error。"""
    import server.ocr.pipeline as pipeline_mod

    document = tmp_path / "scan.pdf"
    document.write_bytes(b"%PDF")
    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda path: {
            "path": str(path),
            "container": "pdf",
            "route": "ocr",
            "handler": "pdf_scan",
        },
    )

    def fail_after_first_page(path, *, purpose=None, on_page=None):
        assert on_page is not None
        on_page(1, {"markdown": "vlm-page-1"})
        raise OcrDependencyError("Tesseract failed on page 2")

    monkeypatch.setattr(pipeline_mod, "recognize", fail_after_first_page)
    units = []

    result = pipeline_mod.extract_one(document, on_unit_complete=units.append)

    assert result["kind"] == "error"
    assert [(unit["page"], unit["status"]) for unit in units] == [(1, "ok"), (None, "error")]
    assert "Tesseract failed on page 2" in units[-1]["payload"]["error"]


# ── G1：units.jsonl 边车排除，重扫不计入 results/单元计数 ───────────────────


def test_iter_files_excludes_units_jsonl_sidecar(tmp_path):
    (tmp_path / "units.jsonl").write_text('{"file": "a.txt"}\n', encoding="utf-8")
    (tmp_path / "doc.txt").write_text("正文", encoding="utf-8")

    files = _iter_files(str(tmp_path))

    names = {p.name for p in files}
    assert "units.jsonl" not in names
    assert "doc.txt" in names


def test_extract_dir_rerun_over_units_jsonl_sidecar_excludes_it(tmp_path):
    (tmp_path / "units.jsonl").write_text('{"file": "a.txt"}\n', encoding="utf-8")
    (tmp_path / "doc.txt").write_text("正文内容", encoding="utf-8")
    collector = _LockedCollector()

    results = extract_dir(str(tmp_path), on_unit_complete=collector)

    result_names = {r.get("path", "").split("/")[-1] for r in results}
    assert "units.jsonl" not in result_names
    assert "doc.txt" in result_names
    unit_files = {unit["file"].split("/")[-1] for unit in collector.units}
    assert "units.jsonl" not in unit_files


# ── 并发：extract_dir 多文件并行时回调仍被正确调用（自身锁收集器）──────────


# ── F1/F2（review pass1）：native→OCR 回退路径页级单元不重复、不过期 ────────────


def test_font_only_fallback_emits_only_ocr_content_no_duplicate_pages(monkeypatch, tmp_path):
    """font-only 扫描 PDF：native 抽不到文本回退 OCR。修复前 native 先发 2 个空白页事件，
    OCR 再对同页发真实内容 → 4 条重复；修复后每页仅 1 条，内容来自 OCR。"""
    import server.ocr.pipeline as pipeline_mod

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-fake")

    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda path: {"route": "native", "handler": "pdf_text", "mixed_pdf": False},
    )
    def fake_native_read(path, *, on_page=None):
        # 模拟 read_pdf_text 真实行为：on_page 非 None 时逐页触发（buffer-then-fire，
        # 但对调用方可见效果等价于返回前已发完）——复现"native 先发空白页"的 bug 前提。
        blocks = ["", ""]
        if on_page is not None:
            for page_no, block in enumerate(blocks, start=1):
                on_page(page_no, {"text": block})
        return {"kind": "pdf_text", "blocks": blocks, "tables": []}

    monkeypatch.setattr(pipeline_mod, "native_read", fake_native_read)

    def fake_recognize(path, *, purpose=None, on_page=None):
        pages = [
            {"page_number": 1, "markdown": "真实内容-页1"},
            {"page_number": 2, "markdown": "真实内容-页2"},
        ]
        if on_page is not None:
            for page in pages:
                on_page(page["page_number"], {"markdown": page["markdown"]})
        return {"kind": "ocr", "pages": pages}

    monkeypatch.setattr(pipeline_mod, "recognize", fake_recognize)

    collector = _LockedCollector()
    result = extract_one(pdf, on_unit_complete=collector)

    assert result["kind"] == "ocr"
    pages = [unit["page"] for unit in collector.units]
    assert pages == [1, 2]  # 每页仅一条，不因先空后真而重复
    assert collector.units[0]["payload"]["markdown"] == "真实内容-页1"
    assert collector.units[1]["payload"]["markdown"] == "真实内容-页2"


def test_mixed_pdf_subset_augment_success_emits_corrected_content_not_blank_native(
    monkeypatch, tmp_path
):
    """混合 PDF 子集增强成功：扫描页最终事件内容须是 augmented 修正后的内容，而非
    native 抽出的空白版（修复前 augment 分支未传 on_page，扫描页内容永不推流）。"""
    import server.ocr.pipeline as pipeline_mod

    pdf = tmp_path / "mixed.pdf"
    pdf.write_bytes(b"%PDF-fake")
    subset_marker = tmp_path / "subset.pdf"
    subset_marker.write_bytes(b"%PDF-fake-subset")

    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda path: {"route": "native", "handler": "pdf_text", "mixed_pdf": True},
    )
    # block0 须 >=MAX_BLANK_CHARS(20) 非空白字符，才不被 _blank_page_count 判成空白页
    # （否则会被子集 OCR 覆盖，混淆"保原生直读"的断言意图）。
    native_blocks = ["这是原生数字页的完整文本内容，用于验证保留原生直读不被子集OCR覆盖测试用文本", "", ""]

    def fake_native_read(path, *, on_page=None):
        if on_page is not None:
            for page_no, block in enumerate(native_blocks, start=1):
                on_page(page_no, {"text": block})
        return {"kind": "pdf_text", "blocks": list(native_blocks), "tables": []}

    monkeypatch.setattr(pipeline_mod, "native_read", fake_native_read)
    monkeypatch.setattr(
        pipeline_mod, "extract_pdf_subset", lambda path, indices: subset_marker
    )

    def fake_subset_recognize(path, *, purpose=None, on_page=None):
        return {
            "kind": "ocr",
            "pages": [
                {"page_number": 1, "markdown": "修正后-页2内容"},
                {"page_number": 2, "markdown": "修正后-页3内容"},
            ],
        }

    monkeypatch.setattr(pipeline_mod, "recognize", fake_subset_recognize)

    collector = _LockedCollector()
    result = extract_one(pdf, on_unit_complete=collector)

    assert result["kind"] == "pdf_text"
    pages = [unit["page"] for unit in collector.units]
    assert pages == [1, 2, 3]  # 页号真实、无重复
    assert collector.units[0]["payload"]["text"] == native_blocks[0]  # 数字页保原生
    assert collector.units[1]["payload"]["text"] == "修正后-页2内容"  # 非空白 native 版
    assert collector.units[2]["payload"]["text"] == "修正后-页3内容"


def test_mixed_pdf_subset_failure_falls_back_to_full_ocr_no_duplicate_pages(
    monkeypatch, tmp_path
):
    """混合 PDF 子集抽页失败（如 fitz 缺失）：回退整份云 OCR。同页号仅一条，来自整份 OCR，
    无 native 空白页重复。"""
    import server.ocr.pipeline as pipeline_mod

    pdf = tmp_path / "mixed2.pdf"
    pdf.write_bytes(b"%PDF-fake")

    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda path: {"route": "native", "handler": "pdf_text", "mixed_pdf": True},
    )
    def fake_native_read(path, *, on_page=None):
        blocks = ["数字页正文这里补足到二十字符以上防止被误判", "", ""]
        if on_page is not None:
            for page_no, block in enumerate(blocks, start=1):
                on_page(page_no, {"text": block})
        return {"kind": "pdf_text", "blocks": blocks, "tables": []}

    monkeypatch.setattr(pipeline_mod, "native_read", fake_native_read)
    monkeypatch.setattr(
        pipeline_mod, "extract_pdf_subset", lambda path, indices: None
    )  # ① 本地抽页失败 → 回退整份云 OCR

    def fake_full_recognize(path, *, purpose=None, on_page=None):
        pages = [
            {"page_number": 1, "markdown": "整份OCR-页1"},
            {"page_number": 2, "markdown": "整份OCR-页2"},
            {"page_number": 3, "markdown": "整份OCR-页3"},
        ]
        if on_page is not None:
            for page in pages:
                on_page(page["page_number"], {"markdown": page["markdown"]})
        return {"kind": "ocr", "pages": pages}

    monkeypatch.setattr(pipeline_mod, "recognize", fake_full_recognize)

    collector = _LockedCollector()
    result = extract_one(pdf, on_unit_complete=collector)

    assert result["kind"] == "ocr"
    pages = [unit["page"] for unit in collector.units]
    assert pages == [1, 2, 3]  # 同页号仅一条
    assert collector.units[0]["payload"]["markdown"] == "整份OCR-页1"


def test_extract_dir_parallel_callback_receives_one_event_per_file(tmp_path):
    for i in range(5):
        (tmp_path / f"doc{i}.txt").write_text(f"内容{i}", encoding="utf-8")
    collector = _LockedCollector()

    results = extract_dir(str(tmp_path), on_unit_complete=collector)

    assert len(results) == 5
    assert len(collector.units) == 5  # 每文件恰好一次文件级事件（text 无页循环）
    files_seen = {unit["file"] for unit in collector.units}
    assert files_seen == {str(tmp_path / f"doc{i}.txt") for i in range(5)}
