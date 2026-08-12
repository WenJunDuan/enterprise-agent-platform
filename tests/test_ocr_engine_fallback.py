from __future__ import annotations

import http.client
import json
import ssl
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest

from server.ocr import OcrDependencyError
from server.ocr import cache, engine
from server.ocr import page_render_worker


class _VlmResponse:
    def __init__(self, body: bytes | BaseException):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        if isinstance(self.body, BaseException):
            raise self.body
        return self.body


@pytest.mark.parametrize(
    "content",
    [None, ["not-a-string"], {"text": "not-a-string"}, 42, "", "   "],
)
def test_openai_compatible_invalid_content_is_dependency_failure(monkeypatch, content):
    payload = {"choices": [{"message": {"content": content}}]}
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _VlmResponse(json.dumps(payload).encode()),
    )

    with pytest.raises(OcrDependencyError, match="返回结构异常"):
        engine._call_openai_compatible_vlm(data_url="data:image/png;base64,eA==", prompt="ocr")


@pytest.mark.parametrize(
    "body",
    [b"\xff", http.client.IncompleteRead(b'{\"choices\":')],
)
def test_openai_compatible_decode_and_protocol_failures_are_dependency_failures(
    monkeypatch, body
):
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _VlmResponse(body),
    )

    with pytest.raises(OcrDependencyError, match="远端调用失败"):
        engine._call_openai_compatible_vlm(data_url="data:image/png;base64,eA==", prompt="ocr")


@pytest.mark.parametrize(
    "recoverable",
    [OSError("response read failed"), ConnectionResetError("response reset")],
)
def test_openai_compatible_success_response_read_io_failure_is_dependency_failure(
    monkeypatch, recoverable
):
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _VlmResponse(recoverable),
    )

    with pytest.raises(OcrDependencyError, match="远端调用失败"):
        engine._call_openai_compatible_vlm(data_url="data:image/png;base64,eA==", prompt="ocr")


@pytest.mark.parametrize("fatal", [MemoryError("oom"), KeyboardInterrupt(), SystemExit(2)])
def test_openai_compatible_success_response_read_does_not_swallow_fatal_errors(
    monkeypatch, fatal
):
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _VlmResponse(fatal),
    )

    with pytest.raises(type(fatal)):
        engine._call_openai_compatible_vlm(data_url="data:image/png;base64,eA==", prompt="ocr")


def test_success_response_read_connection_reset_falls_back_to_tesseract(
    tmp_path, monkeypatch
):
    image = tmp_path / "scan.png"
    _write_test_image(image)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _VlmResponse(ConnectionResetError("response reset")),
    )
    monkeypatch.setattr(
        engine,
        "_recognize_tesseract_page",
        lambda *_args, **_kwargs: "本地降级文本",
    )

    result = engine._recognize_via_openai_compatible(image)

    assert result["engine"] == "tesseract"
    assert result["degraded"] is True
    assert result["pages"][0]["markdown"] == "本地降级文本"


@pytest.mark.parametrize("fatal", [KeyboardInterrupt(), MemoryError("out of memory")])
def test_openai_compatible_does_not_swallow_cancellation_or_resource_errors(
    monkeypatch, fatal
):
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")

    @contextmanager
    def fail_request(*_args, **_kwargs):
        raise fatal
        yield

    monkeypatch.setattr(engine.urllib.request, "urlopen", fail_request)

    with pytest.raises(type(fatal)):
        engine._call_openai_compatible_vlm(data_url="data:image/png;base64,eA==", prompt="ocr")


@pytest.mark.parametrize(
    "fatal",
    [MemoryError("out of memory while reading error response"), KeyboardInterrupt(), SystemExit(2)],
)
def test_openai_compatible_http_error_detail_does_not_swallow_fatal_errors(
    monkeypatch, fatal
):
    class ExhaustedResponse:
        def read(self):
            raise fatal

        def close(self):
            pass

    http_error = engine.urllib.error.HTTPError(
        "http://litellm.test/v1/chat/completions",
        502,
        "Bad Gateway",
        {},
        ExhaustedResponse(),
    )
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(http_error),
    )

    with pytest.raises(type(fatal)):
        engine._call_openai_compatible_vlm(data_url="data:image/png;base64,eA==", prompt="ocr")


@pytest.mark.parametrize(
    "recoverable",
    [
        TimeoutError("detail timed out"),
        engine.urllib.error.URLError("detail connection reset"),
        ssl.SSLError("detail TLS failed"),
        OSError("detail read failed"),
    ],
)
def test_openai_compatible_http_error_detail_io_failure_is_dependency_failure(
    monkeypatch, recoverable
):
    class BrokenErrorResponse:
        def read(self):
            raise recoverable

        def close(self):
            pass

    http_error = engine.urllib.error.HTTPError(
        "http://litellm.test/v1/chat/completions",
        502,
        "Bad Gateway",
        {},
        BrokenErrorResponse(),
    )
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(http_error),
    )

    with pytest.raises(OcrDependencyError, match="HTTP Error 502"):
        engine._call_openai_compatible_vlm(data_url="data:image/png;base64,eA==", prompt="ocr")


@pytest.mark.parametrize("stdout", [None, b"", b" \n\t", "  \n"])
def test_tesseract_blank_stdout_is_dependency_failure(monkeypatch, stdout):
    completed = subprocess.CompletedProcess(
        ["tesseract"],
        0,
        stdout=stdout,
        stderr=b"" if isinstance(stdout, bytes) else "",
    )
    monkeypatch.setattr(engine.shutil, "which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr(engine.subprocess, "run", lambda *_args, **_kwargs: completed)

    with pytest.raises(OcrDependencyError, match="no text.*page 7"):
        engine._recognize_tesseract_page(b"png", page_number=7, mime_type="image/png")


def test_vlm_failure_from_page_n_falls_back_without_duplicate_pages(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF")
    pages = [
        {"page_number": number, "mime_type": "image/png", "content": f"page-{number}".encode()}
        for number in range(1, 5)
    ]
    monkeypatch.setattr(engine, "_iter_pdf_pages", lambda _path: iter(pages))
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    # H3 KD1：单页可恢复失败先重试 1 次再降级，故页 2 的 VLM 调用记两次（退避置 0 免测试墙钟膨胀）。
    monkeypatch.setattr(engine, "_VLM_RETRY_BACKOFF_SEC", 0.0)
    vlm_calls: list[int] = []
    tess_calls: list[int] = []

    # **_kwargs：H3 KD1 重试会额外传 budget_sec（剩余页预算）。
    def fake_vlm(*, data_url, prompt, **_kwargs):
        page_no = int(prompt.split("page ")[1].split(" ")[0])
        vlm_calls.append(page_no)
        if page_no == 2:
            raise OcrDependencyError("gateway down")
        return f"vlm-{page_no}"

    def fake_tesseract(content, *, page_number, mime_type):
        tess_calls.append(page_number)
        assert engine.FITZ_LOCK.locked() is False
        return f"tess-{page_number}"

    callbacks: list[int] = []
    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", fake_vlm)
    monkeypatch.setattr(engine, "_recognize_tesseract_page", fake_tesseract)

    result = engine._recognize_via_openai_compatible(
        pdf,
        on_page=lambda page_no, payload: (
            callbacks.append(page_no),
            pytest.fail("callback under FITZ_LOCK") if engine.FITZ_LOCK.locked() else None,
        ),
    )

    assert vlm_calls == [1, 2, 2]
    assert tess_calls == [2, 3, 4]
    assert callbacks == [1, 2, 3, 4]
    assert [page["page_number"] for page in result["pages"]] == [1, 2, 3, 4]
    assert [page["markdown"] for page in result["pages"]] == ["vlm-1", "tess-2", "tess-3", "tess-4"]
    assert result["engine"] == "tesseract"
    assert result["degraded"] is True
    assert result["clarity"] == "unknown"


def test_vlm_success_page_then_tesseract_failure_keeps_partial_callback(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF")
    pages = [
        {"page_number": number, "mime_type": "image/png", "content": b"png"}
        for number in (1, 2)
    ]
    monkeypatch.setattr(engine, "_iter_pdf_pages", lambda _path: iter(pages))
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")

    # **_kwargs：H3 KD1 重试会额外传 budget_sec（剩余页预算）。
    def vlm(*, data_url, prompt, **_kwargs):
        if "page 2" in prompt:
            raise OcrDependencyError("gateway down")
        assert engine.FITZ_LOCK.locked() is False
        return "page-one"

    def tesseract(*args, **kwargs):
        assert engine.FITZ_LOCK.locked() is False
        raise OcrDependencyError("tesseract crashed")

    callbacks = []
    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", vlm)
    monkeypatch.setattr(engine, "_recognize_tesseract_page", tesseract)

    with pytest.raises(OcrDependencyError, match="gateway down.*tesseract crashed"):
        engine._recognize_via_openai_compatible(
            pdf,
            on_page=lambda page, payload: callbacks.append((page, payload["markdown"])),
        )

    assert callbacks == [(1, "page-one")]


def test_degraded_result_is_not_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", True)
    document = tmp_path / "scan.pdf"
    document.write_bytes(b"%PDF")

    cache.put_cached(document, result={"kind": "ocr", "degraded": True, "pages": []})

    assert cache.get_cached(document) is None
    assert list((tmp_path / "cache").glob("*.json")) == []


def test_tesseract_cli_uses_stdin_and_language_pack(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="识别结果\n", stderr="")

    monkeypatch.setattr(engine.shutil, "which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr(engine.subprocess, "run", fake_run)

    text = engine._recognize_tesseract_page(b"png", page_number=3, mime_type="image/png")

    assert text == "识别结果"
    assert captured["argv"][:3] == ["/usr/bin/tesseract", "stdin", "stdout"]
    assert "chi_sim+eng" in captured["argv"]
    assert captured["input"] == b"png"
    assert captured["timeout"] == engine.OCR_PAGE_TIMEOUT_SEC


def _make_pdf(path, page_count: int):
    import fitz

    document = fitz.open()
    for _ in range(page_count):
        document.new_page()
    document.save(path)
    document.close()


def _write_test_image(path) -> None:
    import fitz

    pixmap = fitz.Pixmap(fitz.csRGB, (0, 0, 10, 10), False)
    pixmap.clear_with(255)
    pixmap.save(path)


def test_pdf_iterator_rejects_page_count_limit_and_closes_document(tmp_path, monkeypatch):
    pdf = tmp_path / "many.pdf"
    _make_pdf(pdf, 2)
    monkeypatch.setattr(engine, "OCR_MAX_PDF_PAGES", 1)

    with pytest.raises(OcrDependencyError, match="page count"):
        list(engine._render_pdf_pages(pdf))

    import fitz

    with fitz.open(pdf) as reopened:
        assert reopened.page_count == 2


def test_pdf_iterator_rejects_page_pixel_limit(tmp_path, monkeypatch):
    pdf = tmp_path / "large-page.pdf"
    _make_pdf(pdf, 1)
    monkeypatch.setattr(engine, "OCR_MAX_PAGE_PIXELS", 1)

    with pytest.raises(OcrDependencyError, match="pixel limit"):
        list(engine._render_pdf_pages(pdf))


def test_pdf_iterator_rejects_cumulative_rendered_bytes(tmp_path, monkeypatch):
    pdf = tmp_path / "bytes.pdf"
    _make_pdf(pdf, 1)
    monkeypatch.setattr(engine, "OCR_MAX_TEMP_BYTES", 1)

    with pytest.raises(OcrDependencyError, match="temporary byte limit"):
        list(engine._render_pdf_pages(pdf))


def test_pdf_iterator_is_lazy_and_closes_on_cancel(monkeypatch):
    script = (
        "import json,sys,time; "
        "print(json.dumps({'type':'meta','page_count':3}), flush=True); "
        "print(json.dumps({'type':'page','page_number':1,'length':3}), flush=True); "
        "sys.stdout.buffer.write(b'png'); sys.stdout.buffer.flush(); time.sleep(30)"
    )
    processes = []
    real_popen = engine.subprocess.Popen

    def capture_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(engine, "_render_worker_argv", lambda path: [sys.executable, "-c", script])
    monkeypatch.setattr(engine.subprocess, "Popen", capture_popen)

    iterator = engine._render_pdf_pages(__import__("pathlib").Path("fake.pdf"))
    assert next(iterator)["page_number"] == 1
    assert processes[0].poll() is None
    iterator.close()
    assert processes[0].poll() is not None


def test_valid_image_pixel_limit_is_checked_before_network(tmp_path, monkeypatch):
    import fitz

    pdf = fitz.open()
    pdf.new_page(width=100, height=100)
    pixmap = fitz.Pixmap(fitz.csRGB, (0, 0, 100, 100), False)
    pixmap.clear_with(255)
    image = tmp_path / "large.png"
    pixmap.save(image)
    pdf.close()
    monkeypatch.setattr(engine, "OCR_MAX_PAGE_PIXELS", 10)

    with pytest.raises(OcrDependencyError, match="pixel limit"):
        engine._validate_image_resource_limits(image, image.read_bytes())


def test_image_vlm_failure_uses_tesseract_and_marks_degraded(tmp_path, monkeypatch):
    image = tmp_path / "scan.png"
    _write_test_image(image)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine,
        "_call_openai_compatible_vlm",
        lambda **kwargs: (_ for _ in ()).throw(OcrDependencyError("gateway down")),
    )
    monkeypatch.setattr(
        engine,
        "_recognize_tesseract_page",
        lambda content, **kwargs: "本地识别",
    )

    result = engine._recognize_via_openai_compatible(image)

    assert result["pages"][0]["markdown"] == "本地识别"
    assert result["engine"] == "tesseract"
    assert result["degraded"] is True


def test_default_remote_path_never_builds_local_paddle(tmp_path, monkeypatch):
    image = tmp_path / "scan.png"
    _write_test_image(image)
    original_content = image.read_bytes()
    reads = []
    captured = {}

    def read_once(self):
        reads.append(self)
        if len(reads) > 1:
            pytest.fail("validated remote image must not be read a second time")
        return original_content

    def fake_remote(path, *, purpose=None, on_page=None, content=None):
        captured["content"] = content
        return {"kind": "ocr", "engine": "remote", "pages": []}

    monkeypatch.setattr(type(image), "read_bytes", read_once)
    monkeypatch.setattr(engine, "OCR_CLOUD", False)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(engine, "OCR_VL_USE_PADDLE_PIPELINE", False)
    monkeypatch.setattr(
        engine,
        "_recognize_via_openai_compatible",
        fake_remote,
    )
    monkeypatch.setattr(
        engine,
        "_recognize_via_paddle_pipeline",
        lambda *args, **kwargs: pytest.fail("local Paddle must stay disabled"),
    )

    assert engine.recognize(image)["engine"] == "remote"
    assert reads == [image]
    assert captured["content"] is original_content


def test_page_text_is_truncated_to_configured_limit(tmp_path, monkeypatch):
    image = tmp_path / "scan.png"
    _write_test_image(image)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(engine, "OCR_MAX_TEXT_CHARS_PER_PAGE", 5)
    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", lambda **kwargs: "123456789")

    result = engine._recognize_via_openai_compatible(image)

    assert result["pages"][0]["markdown"] == "12345"


def test_blocked_page_renderer_hits_hard_timeout(tmp_path, monkeypatch):
    pdf = tmp_path / "blocked.pdf"
    pdf.write_bytes(b"%PDF")
    script = (
        "import json,time; "
        "print(json.dumps({'type':'meta','page_count':1}), flush=True); "
        "time.sleep(30)"
    )
    monkeypatch.setattr(
        engine,
        "_render_worker_argv",
        lambda path: [sys.executable, "-c", script],
    )
    monkeypatch.setattr(engine, "OCR_PAGE_TIMEOUT_SEC", 1)
    started = time.monotonic()

    with pytest.raises(OcrDependencyError, match="page 1 render timed out"):
        list(engine._render_pdf_pages(pdf))

    assert time.monotonic() - started < 5


def test_single_page_renderer_exception_is_structured(tmp_path, monkeypatch):
    pdf = tmp_path / "broken-page.pdf"
    pdf.write_bytes(b"%PDF")
    script = (
        "import json,sys; "
        "print(json.dumps({'type':'meta','page_count':1}), flush=True); "
        "print('page decoder exploded', file=sys.stderr, flush=True); raise SystemExit(2)"
    )
    monkeypatch.setattr(
        engine,
        "_render_worker_argv",
        lambda path: [sys.executable, "-c", script],
    )

    with pytest.raises(OcrDependencyError, match="page 1 render failed.*decoder exploded"):
        list(engine._render_pdf_pages(pdf))


def test_degraded_first_result_is_not_cached_and_remote_recovery_retries(tmp_path, monkeypatch):
    import server.ocr.cache as cache_mod
    import server.ocr.pipeline as pipeline_mod

    image = tmp_path / "scan.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache_mod, "OCR_CACHE_ENABLED", True)
    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda path: {
            "path": str(path),
            "container": "image",
            "route": "ocr",
            "handler": "image",
        },
    )
    calls = []

    def recovering_recognize(path, *, purpose=None):
        calls.append(path)
        if len(calls) == 1:
            return {"kind": "ocr", "degraded": True, "pages": [{"markdown": "fallback"}]}
        return {"kind": "ocr", "engine": "vlm", "pages": [{"markdown": "remote"}]}

    monkeypatch.setattr(pipeline_mod, "recognize", recovering_recognize)

    first = pipeline_mod.extract_one(image)
    second = pipeline_mod.extract_one(image)

    assert first["degraded"] is True
    assert second["engine"] == "vlm"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("width", "height", "message"),
    [
        (10_000, 10_000, "pixel limit"),
        (float("nan"), 100, "invalid page dimensions"),
        (float("inf"), 100, "invalid page dimensions"),
        (0, 100, "invalid page dimensions"),
        (-1, 100, "invalid page dimensions"),
    ],
)
def test_render_worker_preflights_page_rect_before_pixmap(
    monkeypatch, width, height, message
):
    pixmap_calls = []

    class Page:
        rect = type("Rect", (), {"width": width, "height": height})()

        def get_pixmap(self, **kwargs):
            pixmap_calls.append(kwargs)
            pytest.fail("oversized or invalid page must not call get_pixmap")

    class Document:
        page_count = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def load_page(self, index):
            assert index == 0
            return Page()

    fake_fitz = type(
        "FakeFitz",
        (),
        {
            "open": staticmethod(lambda _path: Document()),
            "Matrix": staticmethod(lambda *_args: object()),
        },
    )
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    monkeypatch.setattr(page_render_worker, "_write_header", lambda payload: None)

    with pytest.raises(RuntimeError, match=message):
        page_render_worker.render(__import__("pathlib").Path("fake.pdf"), 2.0, 1_000_000)

    assert pixmap_calls == []


class _FrameStream:
    def fileno(self):
        return 0

    def close(self):
        pass


class _FrameProcess:
    pid = 111
    returncode = 0
    stdout = _FrameStream()
    stderr = _FrameStream()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class _FrameReader:
    def __init__(self, stream):
        self.read_lengths = []

    def read_exact(self, length, deadline):
        self.read_lengths.append(length)
        return b"x" * length


@pytest.mark.parametrize(
    ("bad_header", "message"),
    [
        ({"type": "not-page", "page_number": 1, "length": 3}, "invalid page frame"),
        ({"type": "page", "page_number": 1, "length": 0}, "invalid page frame"),
        ({"type": "page", "page_number": 1, "length": -1}, "invalid page frame"),
        ({"type": "page", "page_number": 1, "length": 11}, "temporary byte limit"),
    ],
)
def test_invalid_page_frame_rejected_before_read_exact(monkeypatch, bad_header, message):
    reader = _FrameReader(None)
    headers = iter([{"type": "meta", "page_count": 1}, bad_header])
    monkeypatch.setattr(engine.subprocess, "Popen", lambda *args, **kwargs: _FrameProcess())
    monkeypatch.setattr(engine, "_TimedPipeReader", lambda stream: reader)
    monkeypatch.setattr(engine, "_read_render_header", lambda *args: next(headers))
    monkeypatch.setattr(engine, "OCR_MAX_TEMP_BYTES", 10)

    with pytest.raises(OcrDependencyError, match=message):
        list(engine._render_pdf_pages(__import__("pathlib").Path("fake.pdf")))

    assert reader.read_lengths == []


def test_page_frame_length_respects_remaining_document_budget_before_read(monkeypatch):
    reader = _FrameReader(None)
    headers = iter(
        [
            {"type": "meta", "page_count": 2},
            {"type": "page", "page_number": 1, "length": 6},
            {"type": "page", "page_number": 2, "length": 5},
        ]
    )
    monkeypatch.setattr(engine.subprocess, "Popen", lambda *args, **kwargs: _FrameProcess())
    monkeypatch.setattr(engine, "_TimedPipeReader", lambda stream: reader)
    monkeypatch.setattr(engine, "_read_render_header", lambda *args: next(headers))
    monkeypatch.setattr(engine, "OCR_MAX_TEMP_BYTES", 10)

    with pytest.raises(OcrDependencyError, match="temporary byte limit"):
        list(engine._render_pdf_pages(__import__("pathlib").Path("fake.pdf")))

    assert reader.read_lengths == [6]


def test_oversized_image_stat_fails_before_read_base64_or_network(tmp_path, monkeypatch):
    image = tmp_path / "large.png"
    image.write_bytes(b"x" * 32)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(engine, "OCR_MAX_IMAGE_BYTES", 16, raising=False)
    monkeypatch.setattr(
        type(image),
        "read_bytes",
        lambda self: pytest.fail("oversized image must not be read into memory"),
    )
    monkeypatch.setattr(
        engine,
        "_image_data_url",
        lambda *args, **kwargs: pytest.fail("oversized image must not be base64 encoded"),
    )
    monkeypatch.setattr(
        engine,
        "_call_openai_compatible_vlm",
        lambda **kwargs: pytest.fail("oversized image must not reach network"),
    )

    with pytest.raises(OcrDependencyError, match="image byte limit"):
        engine._recognize_via_openai_compatible(image)


def test_image_parser_exception_is_structured_and_never_networks(tmp_path, monkeypatch):
    image = tmp_path / "broken.png"
    image.write_bytes(b"not-an-image")
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine,
        "_call_openai_compatible_vlm",
        lambda **kwargs: pytest.fail("parser failure must not reach network"),
    )

    with pytest.raises(OcrDependencyError, match="image dimension validation failed"):
        engine._recognize_via_openai_compatible(image)


def test_legal_image_passes_byte_and_pixel_gates(tmp_path, monkeypatch):
    import fitz

    pixmap = fitz.Pixmap(fitz.csRGB, (0, 0, 10, 10), False)
    pixmap.clear_with(255)
    image = tmp_path / "legal.png"
    pixmap.save(image)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(engine, "OCR_MAX_IMAGE_BYTES", image.stat().st_size + 1, raising=False)
    monkeypatch.setattr(engine, "OCR_MAX_PAGE_PIXELS", 101)
    calls = []
    monkeypatch.setattr(
        engine,
        "_call_openai_compatible_vlm",
        lambda **kwargs: calls.append(kwargs) or "ok",
    )

    result = engine._recognize_via_openai_compatible(image)

    assert result["pages"][0]["markdown"] == "ok"
    assert len(calls) == 1


def test_legal_webp_passes_resource_gates_and_reaches_vlm(tmp_path, monkeypatch):
    from PIL import Image

    image = tmp_path / "legal.webp"
    Image.new("RGB", (10, 10), "white").save(image, format="WEBP")
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    calls = []
    monkeypatch.setattr(
        engine,
        "_call_openai_compatible_vlm",
        lambda **kwargs: calls.append(kwargs) or "webp-ok",
    )

    result = engine._recognize_via_openai_compatible(image)

    assert result["pages"][0]["markdown"] == "webp-ok"
    assert calls[0]["data_url"].startswith("data:image/webp;base64,")


def test_malformed_webp_is_rejected_before_network(tmp_path, monkeypatch):
    image = tmp_path / "broken.webp"
    image.write_bytes(b"RIFF\x10\x00\x00\x00WEBPbroken")
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(
        engine,
        "_call_openai_compatible_vlm",
        lambda **kwargs: pytest.fail("malformed WebP must not reach network"),
    )

    with pytest.raises(OcrDependencyError, match="image dimension validation failed"):
        engine._recognize_via_openai_compatible(image)


def test_image_byte_limit_default_is_conservative_for_two_gib_container():
    assert engine.OCR_MAX_IMAGE_BYTES == 32 * 1024 * 1024


def test_cloud_oversized_image_is_rejected_before_read_or_backend(tmp_path, monkeypatch):
    image = tmp_path / "large.png"
    image.write_bytes(b"x" * 32)
    monkeypatch.setattr(engine, "OCR_CLOUD", True)
    monkeypatch.setattr(engine, "OCR_MAX_IMAGE_BYTES", 16)
    monkeypatch.setattr(
        type(image),
        "read_bytes",
        lambda self: pytest.fail("oversized cloud image must not be read"),
    )
    monkeypatch.setattr(
        engine,
        "_recognize_via_paddle_cloud",
        lambda *args, **kwargs: pytest.fail("oversized cloud image must not reach backend"),
    )

    with pytest.raises(OcrDependencyError, match="image byte limit"):
        engine.recognize(image)


def test_cloud_malformed_image_is_rejected_before_backend(tmp_path, monkeypatch):
    image = tmp_path / "broken.webp"
    image.write_bytes(b"RIFF\x10\x00\x00\x00WEBPbroken")
    monkeypatch.setattr(engine, "OCR_CLOUD", True)
    monkeypatch.setattr(
        engine,
        "_recognize_via_paddle_cloud",
        lambda *args, **kwargs: pytest.fail("malformed cloud image must not reach backend"),
    )

    with pytest.raises(OcrDependencyError, match="image dimension validation failed"):
        engine.recognize(image)


@pytest.mark.parametrize("payload", [b"x" * 32, b"not-an-image"])
def test_local_paddle_rejects_invalid_image_before_pipeline(tmp_path, monkeypatch, payload):
    image = tmp_path / "invalid.png"
    image.write_bytes(payload)
    monkeypatch.setattr(engine, "OCR_CLOUD", False)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", None)
    monkeypatch.setattr(engine, "OCR_VL_USE_PADDLE_PIPELINE", True)
    monkeypatch.setattr(engine, "OCR_MAX_IMAGE_BYTES", 16)
    monkeypatch.setattr(
        engine,
        "_recognize_via_paddle_pipeline",
        lambda *args, **kwargs: pytest.fail("invalid image must not build local Paddle pipeline"),
    )

    with pytest.raises(OcrDependencyError):
        engine.recognize(image)


def test_cloud_image_reuses_single_validated_bytes_for_multipart(tmp_path, monkeypatch):
    image = tmp_path / "scan.png"
    _write_test_image(image)
    original_content = image.read_bytes()
    reads = []

    def read_once(self):
        reads.append(self)
        if len(reads) > 1:
            pytest.fail("validated cloud image must not be read a second time")
        return original_content

    captured = {}

    def fake_post(url, *, fields, file_path, headers, file_content):
        captured["content"] = file_content
        return {"data": {"jobId": "job-1"}}

    class JsonlResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"result":{"layoutParsingResults":[]}}\n'

    monkeypatch.setattr(type(image), "read_bytes", read_once)
    monkeypatch.setattr(engine, "OCR_CLOUD", True)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://ocr.test/jobs")
    monkeypatch.setattr(engine, "OCR_VL_API_KEY", "secret")
    monkeypatch.setattr(engine, "_post_multipart", fake_post)
    monkeypatch.setattr(engine, "_cloud_poll_until_done", lambda job_id: "http://result.test/x")
    monkeypatch.setattr(engine.urllib.request, "urlopen", lambda *args, **kwargs: JsonlResponse())

    result = engine.recognize(image)

    assert result["engine"] == "paddleocr-cloud"
    assert reads == [image]
    assert captured["content"] is original_content


def test_post_multipart_uses_supplied_content_without_reading_path(tmp_path, monkeypatch):
    image = tmp_path / "scan.png"
    image.write_bytes(b"old-on-disk-content")
    supplied_content = b"validated-content"
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(request, **kwargs):
        captured["body"] = request.data
        return Response()

    monkeypatch.setattr(
        type(image),
        "read_bytes",
        lambda self: pytest.fail("multipart must reuse supplied validated bytes"),
    )
    monkeypatch.setattr(engine.urllib.request, "urlopen", fake_urlopen)

    result = engine._post_multipart(
        "http://ocr.test/jobs",
        fields={"model": "ocr"},
        file_path=image,
        headers={},
        file_content=supplied_content,
    )

    assert result == {"ok": True}
    assert supplied_content in captured["body"]
    assert b"old-on-disk-content" not in captured["body"]
