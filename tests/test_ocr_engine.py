from __future__ import annotations

import io
import json
import urllib.error

import pytest

from server.ocr import OcrDependencyError
from server.ocr import engine


class _FakeResponse:
    def __init__(self, content: str = "识别文本"):
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps({"choices": [{"message": {"content": self._content}}]}).encode("utf-8")


def _enable_openai_compatible(monkeypatch):
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")


def test_openai_compatible_pdf_renders_pages_as_images(tmp_path, monkeypatch):
    _enable_openai_compatible(monkeypatch)
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr(
        engine,
        "_render_pdf_pages",
        lambda path: [
            {"page_number": 1, "mime_type": "image/png", "content": b"page-1"},
            {"page_number": 2, "mime_type": "image/png", "content": b"page-2"},
        ],
    )

    calls: list[dict] = []

    def fake_urlopen(request, timeout, context=None):
        calls.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse(f"第 {len(calls)} 页")

    monkeypatch.setattr(engine.urllib.request, "urlopen", fake_urlopen)

    result = engine._recognize_via_openai_compatible(pdf)

    assert [page["markdown"] for page in result["pages"]] == ["第 1 页", "第 2 页"]
    urls = [
        call["messages"][0]["content"][0]["image_url"]["url"]
        for call in calls
    ]
    assert len(urls) == 2
    assert all(url.startswith("data:image/png;base64,") for url in urls)
    assert all("application/pdf" not in url for url in urls)


def test_openai_compatible_image_keeps_image_mime_type(tmp_path, monkeypatch):
    _enable_openai_compatible(monkeypatch)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"jpg-bytes")
    calls: list[dict] = []

    def fake_urlopen(request, timeout, context=None):
        calls.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse()

    monkeypatch.setattr(engine.urllib.request, "urlopen", fake_urlopen)

    result = engine._recognize_via_openai_compatible(image)

    assert result["pages"][0]["markdown"] == "识别文本"
    url = calls[0]["messages"][0]["content"][0]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")


def test_openai_compatible_http_error_includes_response_body(tmp_path, monkeypatch):
    _enable_openai_compatible(monkeypatch)
    image = tmp_path / "photo.png"
    image.write_bytes(b"png-bytes")

    def fake_urlopen(request, timeout, context=None):
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"invalid image_url"}'),
        )

    monkeypatch.setattr(engine.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(OcrDependencyError) as exc:
        engine._recognize_via_openai_compatible(image)

    message = str(exc.value)
    assert "HTTP Error 400: Bad Request" in message
    assert "invalid image_url" in message
