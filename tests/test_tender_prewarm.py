"""Tests for prewarm_and_report in server/ocr/pipeline.py.

TDD: tests written before implementation. prewarm_and_report runs extract_dir
(with content-sha256 cache) and returns build_extraction_block result.
"""

from __future__ import annotations


def test_prewarm_and_report_calls_extract_dir_and_builds_block(monkeypatch, tmp_path):
    """prewarm_and_report calls extract_dir then build_extraction_block and returns text."""
    from server.ocr import pipeline

    fake_results = [{"path": str(tmp_path / "a.pdf"), "kind": "pdf_text", "route": "native",
                     "blocks": ["page1 content"]}]

    calls: dict = {}

    def fake_extract_dir(case_dir: str, *, run_seal: bool = False,
                         purpose: str | None = None) -> list[dict]:
        calls["case_dir"] = case_dir
        calls["purpose"] = purpose
        return fake_results

    monkeypatch.setattr(pipeline, "extract_dir", fake_extract_dir)

    result, _report = pipeline.prewarm_and_report(str(tmp_path))

    assert calls["case_dir"] == str(tmp_path)
    # Result must equal what build_extraction_block returns for fake_results
    expected = pipeline.build_extraction_block(fake_results)
    assert result == expected
    assert "a.pdf" in result


def test_prewarm_and_report_passes_purpose(monkeypatch, tmp_path):
    """purpose kwarg is forwarded to extract_dir."""
    from server.ocr import pipeline

    calls: dict = {}

    def fake_extract_dir(case_dir: str, *, run_seal: bool = False,
                         purpose: str | None = None) -> list[dict]:
        calls["purpose"] = purpose
        return []

    monkeypatch.setattr(pipeline, "extract_dir", fake_extract_dir)

    pipeline.prewarm_and_report(str(tmp_path), purpose="tender-ocr")
    assert calls["purpose"] == "tender-ocr"


def test_prewarm_and_report_empty_dir_returns_no_content(monkeypatch, tmp_path):
    """Empty directory: extract_dir returns [], build_extraction_block yields placeholder."""
    from server.ocr import pipeline

    monkeypatch.setattr(pipeline, "extract_dir", lambda *a, **kw: [])

    result, report = pipeline.prewarm_and_report(str(tmp_path))
    assert result == "（无识别内容）"
    assert report.status == "failed"


def test_prewarm_and_report_returns_str(monkeypatch, tmp_path):
    """Return type is always str."""
    from server.ocr import pipeline

    monkeypatch.setattr(pipeline, "extract_dir", lambda *a, **kw: [])
    result, _report = pipeline.prewarm_and_report(str(tmp_path))
    assert isinstance(result, str)
