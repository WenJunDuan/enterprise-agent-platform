from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import smoke_document_formats as smoke
from server.ocr.formats import ALL_SUPPORTED_SUFFIXES
from server.routes.upload_helpers import validate_document_upload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_FIXTURES = PROJECT_ROOT / "scripts" / "document_format_fixtures"


def test_discover_fixtures_requires_exactly_one_file_per_suffix(tmp_path):
    for suffix in ALL_SUPPORTED_SUFFIXES:
        (tmp_path / f"fixture{suffix}").write_bytes(b"placeholder")

    fixtures = smoke.discover_fixture_paths(tmp_path)
    assert set(fixtures) == ALL_SUPPORTED_SUFFIXES

    (tmp_path / "fixture.pdf").unlink()
    with pytest.raises(smoke.SmokeFailure, match="missing fixtures: .pdf"):
        smoke.discover_fixture_paths(tmp_path)


def test_run_smoke_requires_nonempty_nonmanual_results(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture.txt"
    fixture.write_text("有效底稿", encoding="utf-8")
    monkeypatch.setattr(smoke, "validate_document_upload", lambda *_args: None)
    def extract_native(*_args, **kwargs):
        kwargs["on_unit_complete"](
            {"file": str(fixture), "page": None, "status": "ok", "payload": {}, "from_cache": False}
        )
        return {"route": "native", "kind": "text", "blocks": ["有效底稿"]}

    monkeypatch.setattr(smoke, "extract_one", extract_native)

    reports = smoke.run_smoke({".txt": fixture})
    assert reports == [
        {
            "suffix": ".txt",
            "route": "native",
            "kind": "text",
            "status": "ok",
            "from_cache": False,
        }
    ]

    monkeypatch.setattr(
        smoke,
        "extract_one",
        lambda *_args, **_kwargs: {"route": "manual", "kind": "error", "error": "failed"},
    )
    with pytest.raises(smoke.SmokeFailure, match="fixture.txt"):
        smoke.run_smoke({".txt": fixture})


def test_run_smoke_rejects_ocr_pages_containing_only_page_anchors(tmp_path, monkeypatch):
    fixture = tmp_path / "scan.png"
    fixture.write_bytes(b"png")
    monkeypatch.setattr(smoke, "validate_document_upload", lambda *_args: None)

    def extract_blank(*_args, **kwargs):
        kwargs["on_unit_complete"](
            {
                "file": str(fixture),
                "page": 1,
                "status": "ok",
                "payload": {},
                "from_cache": False,
            }
        )
        return {
            "route": "ocr",
            "kind": "ocr",
            "engine": "tesseract",
            "degraded": True,
            "pages": [{"page_number": 1, "markdown": "   "}],
        }

    monkeypatch.setattr(smoke, "extract_one", extract_blank)

    with pytest.raises(smoke.SmokeFailure, match="empty extraction draft"):
        smoke.run_smoke({".png": fixture})


def test_run_smoke_disables_cache_and_rejects_cache_hits(tmp_path, monkeypatch):
    fixture = tmp_path / "scan.png"
    fixture.write_bytes(b"png")
    monkeypatch.setattr(smoke, "validate_document_upload", lambda *_args: None)
    observed_cache_states = []

    def extract(*_args, **kwargs):
        observed_cache_states.append(smoke.ocr_cache.OCR_CACHE_ENABLED)
        kwargs["on_unit_complete"](
            {"file": str(fixture), "page": None, "status": "ok", "payload": {}, "from_cache": True}
        )
        return {
            "route": "ocr",
            "kind": "ocr",
            "engine": "openai-compatible-vlm",
            "pages": [{"markdown": "识别结果"}],
        }

    monkeypatch.setattr(smoke, "extract_one", extract)
    monkeypatch.setattr(smoke.ocr_cache, "OCR_CACHE_ENABLED", True)

    with pytest.raises(smoke.SmokeFailure, match="cache hit"):
        smoke.run_smoke({".png": fixture})

    assert observed_cache_states == [False]
    assert smoke.ocr_cache.OCR_CACHE_ENABLED is True


@pytest.mark.parametrize(
    ("actual_engine", "actual_degraded", "expected_engine", "expected_degraded"),
    [
        ("tesseract", True, "openai-compatible-vlm", False),
        ("openai-compatible-vlm", False, "tesseract", True),
    ],
)
def test_run_smoke_hard_gates_required_ocr_suffix_engine_and_degraded(
    tmp_path,
    monkeypatch,
    actual_engine,
    actual_degraded,
    expected_engine,
    expected_degraded,
):
    fixture = tmp_path / "scan.png"
    fixture.write_bytes(b"png")
    monkeypatch.setattr(smoke, "validate_document_upload", lambda *_args: None)

    def extract(*_args, **kwargs):
        kwargs["on_unit_complete"](
            {"file": str(fixture), "page": 1, "status": "ok", "payload": {}, "from_cache": False}
        )
        return {
            "route": "ocr",
            "kind": "ocr",
            "engine": actual_engine,
            "degraded": actual_degraded,
            "pages": [{"markdown": "识别结果"}],
        }

    monkeypatch.setattr(smoke, "extract_one", extract)

    with pytest.raises(smoke.SmokeFailure, match=r"\.png.*engine|\.png.*degraded"):
        smoke.run_smoke(
            {".png": fixture},
            required_ocr_suffixes={".png"},
            expected_engine=expected_engine,
            expected_degraded=expected_degraded,
        )


def test_run_smoke_records_machine_assertable_ocr_expectation(tmp_path, monkeypatch):
    fixture = tmp_path / "scan.png"
    fixture.write_bytes(b"png")
    monkeypatch.setattr(smoke, "validate_document_upload", lambda *_args: None)

    def extract(*_args, **kwargs):
        kwargs["on_unit_complete"](
            {"file": str(fixture), "page": 1, "status": "ok", "payload": {}, "from_cache": False}
        )
        return {
            "route": "ocr",
            "kind": "ocr",
            "engine": "tesseract",
            "degraded": True,
            "clarity": "unknown",
            "pages": [{"markdown": "识别结果"}],
        }

    monkeypatch.setattr(smoke, "extract_one", extract)

    reports = smoke.run_smoke(
        {".png": fixture},
        required_ocr_suffixes={".png"},
        expected_engine="tesseract",
        expected_degraded=True,
        evidence_details=True,
    )

    assert reports[0]["from_cache"] is False
    assert reports[0]["engine"] == "tesseract"
    assert reports[0]["degraded"] is True
    assert reports[0]["ocr_expectation"] == "matched"


def test_committed_real_fixtures_cover_and_validate_every_canonical_suffix():
    fixtures = smoke.discover_fixture_paths(REAL_FIXTURES)

    assert set(fixtures) == ALL_SUPPORTED_SUFFIXES
    for suffix, path in fixtures.items():
        assert path.stat().st_size > 0, suffix
        validate_document_upload(path.name, path.read_bytes())


def test_xlsb_fixture_records_immutable_upstream_source_and_license():
    provenance = json.loads((REAL_FIXTURES / "SOURCES.json").read_text(encoding="utf-8"))
    xlsb = provenance["fixtures"]["sample.xlsb"]

    assert xlsb["url"].startswith(
        "https://raw.githubusercontent.com/willtrnr/pyxlsb/a59b6ddcadd89cf96e478152b7c4fb051588a747/"
    )
    assert xlsb["license"] == "LGPL-3.0"
    assert len(xlsb["sha256"]) == 64


def test_execution_scope_describes_the_current_runtime(monkeypatch):
    monkeypatch.setattr(smoke.platform, "system", lambda: "Linux")
    monkeypatch.setattr(smoke.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(smoke.shutil, "which", lambda _name: None)

    context = smoke._execution_context()

    assert context["execution_scope"] == "current runtime: Linux aarch64"
    assert context["host"] == {"system": "Linux", "architecture": "aarch64"}
