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
"""

from __future__ import annotations

import threading

import pytest

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
    import fitz

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


def test_extract_one_error_path_emits_single_error_unit(tmp_path):
    """损坏 / 不可读文件走 per-file 隔离 → 单一文件级 error 单元，不是静默丢事件。"""
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a real xlsx")  # 触发 read_excel 内部异常 → 归一 error
    collector = _LockedCollector()

    result = extract_one(broken, on_unit_complete=collector)

    assert result["kind"] == "error"
    assert len(collector.units) == 1
    assert collector.units[0]["status"] == "error"
    assert collector.units[0]["payload"] is result


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


def test_extract_dir_parallel_callback_receives_one_event_per_file(tmp_path):
    for i in range(5):
        (tmp_path / f"doc{i}.txt").write_text(f"内容{i}", encoding="utf-8")
    collector = _LockedCollector()

    results = extract_dir(str(tmp_path), on_unit_complete=collector)

    assert len(results) == 5
    assert len(collector.units) == 5  # 每文件恰好一次文件级事件（text 无页循环）
    files_seen = {unit["file"] for unit in collector.units}
    assert files_seen == {str(tmp_path / f"doc{i}.txt") for i in range(5)}
