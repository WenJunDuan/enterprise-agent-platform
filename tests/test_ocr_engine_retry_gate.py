"""H3 KD1/KD3/KD6：页级重试、VLM 客户端并发闸、渲染中途失败保留已完成页。

三组行为都在 ``server.ocr.engine`` 的 openai-compatible 路径上：
- KD1 单页 VLM 可恢复失败先重试 1 次再降级（重试预算不超页 deadline）。
- KD3 网络调用段经进程级 ``BoundedSemaphore`` 限流；闸等待不吃页 deadline。
- KD6 页迭代器中途抛结构化错误时保留已完成页（partial 底稿），不整份报废。
"""

from __future__ import annotations

import threading
import time

import pytest

from server.ocr import OcrDependencyError, engine


def _pdf_with_pages(tmp_path, count: int):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF")
    pages = [
        {"page_number": number, "mime_type": "image/png", "content": f"page-{number}".encode()}
        for number in range(1, count + 1)
    ]
    return pdf, pages


def _configure_remote(monkeypatch) -> None:
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm.test/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "paddleocr")
    monkeypatch.setattr(engine, "_VLM_RETRY_BACKOFF_SEC", 0.0)


# ── KD1 页级重试 ──────────────────────────────────────────────────────────────


def test_page_vlm_failure_retries_once_and_keeps_vlm_result(tmp_path, monkeypatch):
    """AC1：单页首次失败、第二次成功 → 该页仍是 VLM 结果、无降级、页序连续。"""
    pdf, pages = _pdf_with_pages(tmp_path, 3)
    monkeypatch.setattr(engine, "_iter_pdf_pages", lambda _path: iter(pages))
    _configure_remote(monkeypatch)
    attempts: list[int] = []

    def fake_vlm(*, data_url, prompt, **_kwargs):
        page_no = int(prompt.split("page ")[1].split(" ")[0])
        attempts.append(page_no)
        if page_no == 2 and attempts.count(2) == 1:
            raise OcrDependencyError("gateway 502")
        return f"vlm-{page_no}"

    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", fake_vlm)
    monkeypatch.setattr(
        engine,
        "_recognize_tesseract_page",
        lambda *_a, **_k: pytest.fail("retry success must not fall back to tesseract"),
    )

    result = engine._recognize_via_openai_compatible(pdf)

    assert attempts == [1, 2, 2, 3]
    assert [page["page_number"] for page in result["pages"]] == [1, 2, 3]
    assert [page["markdown"] for page in result["pages"]] == ["vlm-1", "vlm-2", "vlm-3"]
    assert result["engine"] == "openai-compatible-vlm"
    assert "degraded" not in result


def test_page_vlm_failure_twice_degrades_from_that_page(tmp_path, monkeypatch):
    """AC1：两次失败 → 该页起 Tesseract，行为与 0730 一致（degraded 整份透出）。"""
    pdf, pages = _pdf_with_pages(tmp_path, 4)
    monkeypatch.setattr(engine, "_iter_pdf_pages", lambda _path: iter(pages))
    _configure_remote(monkeypatch)
    vlm_calls: list[int] = []
    tess_calls: list[int] = []

    def fake_vlm(*, data_url, prompt, **_kwargs):
        page_no = int(prompt.split("page ")[1].split(" ")[0])
        vlm_calls.append(page_no)
        if page_no == 2:
            raise OcrDependencyError("gateway down")
        return f"vlm-{page_no}"

    def fake_tesseract(content, *, page_number, mime_type):
        tess_calls.append(page_number)
        return f"tess-{page_number}"

    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", fake_vlm)
    monkeypatch.setattr(engine, "_recognize_tesseract_page", fake_tesseract)

    result = engine._recognize_via_openai_compatible(pdf)

    assert vlm_calls == [1, 2, 2]  # 页 2 重试一次后才降级
    assert tess_calls == [2, 3, 4]
    assert [page["markdown"] for page in result["pages"]] == [
        "vlm-1",
        "tess-2",
        "tess-3",
        "tess-4",
    ]
    assert result["degraded"] is True
    assert result["engine"] == "tesseract"


def test_retry_is_skipped_when_page_budget_cannot_cover_backoff(tmp_path, monkeypatch):
    """AC1：重试预算计入页 deadline——预算不足以覆盖退避时直接降级，不超页预算。"""
    pdf, pages = _pdf_with_pages(tmp_path, 1)
    monkeypatch.setattr(engine, "_iter_pdf_pages", lambda _path: iter(pages))
    _configure_remote(monkeypatch)
    monkeypatch.setattr(engine, "_VLM_RETRY_BACKOFF_SEC", 30.0)
    monkeypatch.setattr(engine, "OCR_PAGE_TIMEOUT_SEC", 1)
    vlm_calls: list[str] = []

    def fake_vlm(*, data_url, prompt, **_kwargs):
        vlm_calls.append(prompt)
        raise OcrDependencyError("gateway down")

    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", fake_vlm)
    monkeypatch.setattr(
        engine, "_recognize_tesseract_page", lambda *_a, **_k: "tess-1"
    )

    result = engine._recognize_via_openai_compatible(pdf)

    assert len(vlm_calls) == 1  # 无第二次尝试
    assert result["degraded"] is True


def test_retry_timeout_is_capped_by_the_remaining_page_budget(tmp_path, monkeypatch):
    """AC1/F1：第二次调用的 timeout 必须收敛到"剩余预算"，否则单页最坏耗时是页 deadline 的两倍。"""
    pdf, pages = _pdf_with_pages(tmp_path, 1)
    monkeypatch.setattr(engine, "_iter_pdf_pages", lambda _path: iter(pages))
    _configure_remote(monkeypatch)
    monkeypatch.setattr(engine, "OCR_PAGE_TIMEOUT_SEC", 10)
    monkeypatch.setattr(engine, "_VLM_RETRY_BACKOFF_SEC", 2.0)
    monkeypatch.setattr(engine, "OCR_VL_TIMEOUT", 120.0)
    timeouts: list[float] = []

    def fake_call_vlm(*, url, model, api_key, data_url, prompt, timeout, ssl_context):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            time.sleep(0.05)  # 首次尝试自身也吃掉一点预算
            raise OcrDependencyError("gateway 502")
        return "vlm-1"

    monkeypatch.setattr(engine.vlm_client, "call_vlm", fake_call_vlm)
    monkeypatch.setattr(
        engine,
        "_recognize_tesseract_page",
        lambda *_a, **_k: pytest.fail("retry success must not fall back to tesseract"),
    )

    result = engine._recognize_via_openai_compatible(pdf)

    assert len(timeouts) == 2
    assert timeouts[0] == 10  # 首次 = 整页预算
    # 第二次 ≤ 剩余预算（10 - 首次耗时 - 2s 退避），且严格小于整页预算。
    assert 0 < timeouts[1] <= 10 - 2 - 0.05
    assert result["pages"][0]["markdown"] == "vlm-1"
    assert "degraded" not in result


def test_image_page_also_retries_once_before_degrading(tmp_path, monkeypatch):
    """AC1：图片（单页）路径与 PDF 页共用同一重试语义。"""
    image = tmp_path / "scan.png"
    image.write_bytes(b"fake-png")
    _configure_remote(monkeypatch)
    calls: list[int] = []

    def fake_vlm(*, data_url, prompt, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OcrDependencyError("gateway 503")
        return "vlm-image"

    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", fake_vlm)
    monkeypatch.setattr(
        engine,
        "_recognize_tesseract_page",
        lambda *_a, **_k: pytest.fail("retry success must not fall back to tesseract"),
    )

    result = engine._recognize_via_openai_compatible(image, content=b"fake-png")

    assert len(calls) == 2
    assert result["pages"][0]["markdown"] == "vlm-image"
    assert "degraded" not in result


# ── KD3 并发闸 ────────────────────────────────────────────────────────────────


def test_vlm_calls_never_exceed_configured_concurrency(monkeypatch):
    """AC4：mock 网关计数并发 → 峰值 ≤ 闸容量。"""
    _configure_remote(monkeypatch)
    limit = 3
    monkeypatch.setattr(engine, "_VLM_SEMAPHORE", threading.BoundedSemaphore(limit))
    lock = threading.Lock()
    state = {"live": 0, "peak": 0}

    def fake_vlm(*, data_url, prompt, **_kwargs):
        with lock:
            state["live"] += 1
            state["peak"] = max(state["peak"], state["live"])
        time.sleep(0.02)
        with lock:
            state["live"] -= 1
        return "ok"

    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", fake_vlm)
    threads = [
        threading.Thread(
            target=engine._call_vlm_page,
            kwargs={"data_url": "data:image/png;base64,eA==", "prompt": f"p{i}"},
        )
        for i in range(12)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert state["peak"] <= limit
    assert state["peak"] > 1  # 闸不是把并发压成串行


def test_gate_wait_does_not_consume_the_page_deadline(monkeypatch):
    """AC4：闸等待不计入页 deadline——排队久于页预算后仍照常重试。"""
    _configure_remote(monkeypatch)
    monkeypatch.setattr(engine, "OCR_PAGE_TIMEOUT_SEC", 1)
    monkeypatch.setattr(engine, "_VLM_RETRY_BACKOFF_SEC", 0.0)
    gate = threading.BoundedSemaphore(1)
    monkeypatch.setattr(engine, "_VLM_SEMAPHORE", gate)
    calls: list[float] = []

    def fake_vlm(*, data_url, prompt, **_kwargs):
        calls.append(time.monotonic())
        if len(calls) == 1:
            raise OcrDependencyError("gateway 502")
        return "ok"

    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", fake_vlm)
    result: list[str] = []

    def run() -> None:
        result.append(engine._call_vlm_page(data_url="d", prompt="p"))

    gate.acquire()
    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(1.3)  # 排队时长 > OCR_PAGE_TIMEOUT_SEC
    gate.release()
    worker.join(timeout=10)

    assert result == ["ok"]
    assert len(calls) == 2  # 排队没有吃掉重试预算


# ── KD6 渲染中途失败保留已完成页 ──────────────────────────────────────────────


def _iterator_failing_at(pages: list[dict], failing_index: int, error: BaseException):
    def _iterator(_path):
        for index, page in enumerate(pages):
            if index == failing_index:
                raise error
            yield page

    return _iterator


def test_render_failure_midway_keeps_completed_pages(tmp_path, monkeypatch):
    """AC3：5 页 PDF 第 3 页渲染故障 → 前 2 页正常出稿 + 尾部失败标记 + partial。"""
    pdf, pages = _pdf_with_pages(tmp_path, 5)
    _configure_remote(monkeypatch)
    monkeypatch.setattr(
        engine,
        "_iter_pdf_pages",
        _iterator_failing_at(pages, 2, OcrDependencyError("PDF page 3 render timed out")),
    )
    monkeypatch.setattr(
        engine, "_call_openai_compatible_vlm", lambda **_k: "page-text"
    )
    emitted: list[int] = []

    result = engine._recognize_via_openai_compatible(
        pdf, on_page=lambda page_no, _payload: emitted.append(page_no)
    )

    assert result["partial"] is True
    assert [page["page_number"] for page in result["pages"]] == [1, 2, 3]
    assert result["pages"][2]["markdown"].startswith("[第3页起识别失败:")
    assert "render timed out" in result["pages"][2]["markdown"]
    assert emitted == [1, 2]  # 失败标记不冒充成功页事件


def test_render_failure_on_first_page_still_raises(tmp_path, monkeypatch):
    """KD6 边界：一页都没成功 → 维持整份失败语义（不产出空 partial 底稿）。"""
    pdf, pages = _pdf_with_pages(tmp_path, 3)
    _configure_remote(monkeypatch)
    monkeypatch.setattr(
        engine,
        "_iter_pdf_pages",
        _iterator_failing_at(pages, 0, OcrDependencyError("PDF render failed: no pages")),
    )
    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", lambda **_k: "text")

    with pytest.raises(OcrDependencyError, match="no pages"):
        engine._recognize_via_openai_compatible(pdf)


def test_render_memory_error_is_not_disguised_as_partial(tmp_path, monkeypatch):
    """KD6 边界：MemoryError 等资源错误照旧透传，绝不伪装成 partial。"""
    pdf, pages = _pdf_with_pages(tmp_path, 4)
    _configure_remote(monkeypatch)
    monkeypatch.setattr(
        engine, "_iter_pdf_pages", _iterator_failing_at(pages, 2, MemoryError("oom"))
    )
    monkeypatch.setattr(engine, "_call_openai_compatible_vlm", lambda **_k: "text")

    with pytest.raises(MemoryError):
        engine._recognize_via_openai_compatible(pdf)
