"""H3 KD2/KD6：目录级 OCR 明细（doc 层状态 + failed_files）与降级/部分底稿不进缓存。

``prewarm_and_report`` 是上传预热 OCR 的唯一入口：既返回底稿文本，也返回把"部分失败/降级"
显式暴露给状态机的 ``OcrDocReport``（此前部分失败对状态机完全不可见，低质底稿以 ready 永久落库）。
"""

from __future__ import annotations

from pathlib import Path

from server.ocr import cache, pipeline


def _ok(name: str, markdown: str = "正文内容") -> dict:
    return {
        "path": f"/case/{name}",
        "kind": "ocr",
        "route": "ocr",
        "pages": [{"markdown": markdown, "page_number": 1}],
    }


def _failed(name: str) -> dict:
    return {"path": f"/case/{name}", "kind": "error", "route": "manual", "error": "boom"}


def _degraded(name: str) -> dict:
    return {**_ok(name), "engine": "tesseract", "degraded": True, "clarity": "unknown"}


def _partial(name: str) -> dict:
    result = _ok(name)
    result["pages"].append({"markdown": "[第2页起识别失败: render timed out]", "page_number": 2})
    result["partial"] = True
    return result


def _report(monkeypatch, results: list[dict], tmp_path: Path):
    monkeypatch.setattr(pipeline, "extract_dir", lambda *_a, **_k: results)
    return pipeline.prewarm_and_report(str(tmp_path))


def test_all_files_ok_reports_ready(monkeypatch, tmp_path):
    text, report = _report(monkeypatch, [_ok("a.pdf"), _ok("b.pdf")], tmp_path)

    assert report.status == "ready"
    assert report.failed_files == ()
    assert report.degraded_files == ()
    assert "正文内容" in text


def test_two_of_ten_files_failed_reports_partial_with_named_files(monkeypatch, tmp_path):
    """AC3：10 文件 2 失败 → partial + failed_files 明细；8 个成功文件底稿完整。"""
    results = [_ok(f"ok-{i}.pdf", markdown=f"内容-{i}") for i in range(8)]
    results.insert(3, _failed("broken-1.pdf"))
    results.append(_failed("broken-2.pdf"))

    text, report = _report(monkeypatch, results, tmp_path)

    assert report.status == "partial"
    assert report.failed_files == ("broken-1.pdf", "broken-2.pdf")
    for i in range(8):
        assert f"内容-{i}" in text


def test_degraded_file_reports_degraded_not_ready(monkeypatch, tmp_path):
    """AC2：含 Tesseract 降级段的底稿不得以 ready 落库。"""
    _text, report = _report(monkeypatch, [_ok("a.pdf"), _degraded("scan.pdf")], tmp_path)

    assert report.status == "degraded"
    assert report.degraded_files == ("scan.pdf",)
    assert report.failed_files == ()


def test_partial_file_reports_partial(monkeypatch, tmp_path):
    """AC3：渲染中途失败的文件（KD6 partial 底稿）把 doc 状态拉到 partial。"""
    _text, report = _report(monkeypatch, [_ok("a.pdf"), _partial("half.pdf")], tmp_path)

    assert report.status == "partial"
    assert report.failed_files == ("half.pdf",)


def test_failed_and_degraded_together_prefers_partial(monkeypatch, tmp_path):
    _text, report = _report(monkeypatch, [_degraded("a.pdf"), _failed("b.pdf")], tmp_path)

    assert report.status == "partial"
    assert report.failed_files == ("b.pdf",)
    assert report.degraded_files == ("a.pdf",)


def test_all_files_failed_reports_failed(monkeypatch, tmp_path):
    _text, report = _report(monkeypatch, [_failed("a.pdf"), _failed("b.pdf")], tmp_path)

    assert report.status == "failed"
    assert report.failed_files == ("a.pdf", "b.pdf")


def test_empty_dir_reports_failed(monkeypatch, tmp_path):
    _text, report = _report(monkeypatch, [], tmp_path)

    assert report.status == "failed"


def test_report_status_is_always_a_declared_enum_value(monkeypatch, tmp_path):
    for results in ([_ok("a.pdf")], [_degraded("a.pdf")], [_partial("a.pdf")], [_failed("a.pdf")]):
        _text, report = _report(monkeypatch, results, tmp_path)
        assert report.status in pipeline.OCR_DOC_STATUSES


def test_partial_result_is_not_cached(tmp_path, monkeypatch):
    """AC2 同理扩展到 KD6：部分底稿不进文件缓存，下次预热才可能补齐。"""
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "cache")
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-partial")

    cache.put_cached(source, result={"kind": "ocr", "partial": True, "pages": []})

    assert cache.get_cached(source) is None


def test_degraded_result_is_not_cached(tmp_path, monkeypatch):
    """AC2：0730 "degraded 不落缓存"语义回归。"""
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "cache")
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-degraded")

    cache.put_cached(source, result={"kind": "ocr", "degraded": True, "pages": []})

    assert cache.get_cached(source) is None
