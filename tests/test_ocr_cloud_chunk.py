"""Bug B（2026-08-14 生产 P0）：云 OCR 大文件整包上传失败 → 投标文件完全读不出。

现场：`PaddleOCR 云调用失败：<urlopen error EOF occurred in violation of protocol>` →
`tender_bid_doc_ocr_failed`。部署机实测定位（400 页 / 43.2 MB 投标 PDF）：

1. `.env` 的 `HTTP_PROXY/HTTPS_PROXY` 未把 OCR 域名放进 `NO_PROXY`，43 MB 穿代理被掐断
   （运维侧修，代码不处理代理）；
2. 绕过代理后服务端对大包直接 `HTTP 400`——逐档实测 **50 页(3.24 MB) 成功 / 80 页 400**；
3. `extract_pdf_subset` 存子集不带压缩参数，`insert_pdf` 复制共享资源 → 实测 100 页子集
   43.6 MB **大于** 400 页原文件 43.2 MB；
4. 服务端有限流：连发大包后连 2 页的小包也被 400 拒绝，冷却几十秒才恢复。

故：超阈值按页分片上传 + 片间节流 + 对可重试状态码有限退避重试；页号必须与原文档一一对应
（错误的证据页码比没有证据更危险）。
"""

from __future__ import annotations

import sys
import urllib.error

import pytest

from server.ocr import OcrError, cloud_chunk, engine


def _http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://ocr.test/jobs", status, "Bad Request", {}, None)


def _cloud_failure(status: int | None = 400) -> OcrError:
    """构造与 ``_recognize_via_paddle_cloud`` 同型的失败：OcrError from HTTPError。"""
    cause = _http_error(status) if status is not None else None
    error = OcrError("PaddleOCR 云调用失败")
    if cause is not None:
        error.__cause__ = cause
    return error


def _fake_subset_extractor(calls: list[list[int]]):
    """替身 ``extract_pdf_subset``：落一个真实临时文件，好一并验证调用方删干净了。"""

    def extract(path, page_indices):
        calls.append(list(page_indices))
        target = path.parent / f"subset-{page_indices[0]}.pdf"
        target.write_bytes(b"%PDF-1.7\n")
        return target

    return extract


def _pages_for(start: int, count: int) -> list[dict]:
    """模拟云端返回：页号永远是**本片内**的 1..n（``_parse_cloud_jsonl`` 的既定语义）。"""
    return [
        {"page_number": local, "markdown": f"chunk{start}-local{local}", "layout": []}
        for local in range(1, count + 1)
    ]


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """分片节流与退避在测试里不真睡（保留调用记录供断言）。"""
    slept: list[float] = []
    monkeypatch.setenv("OCR_CLOUD_CHUNK_PAUSE_SEC", "0")
    monkeypatch.setattr(cloud_chunk, "_RETRY_BACKOFF_BASE_SEC", 0.0)
    monkeypatch.setattr(cloud_chunk.time, "sleep", slept.append)
    return slept


# ── 分片规划与页号对齐 ─────────────────────────────────────────────────────────


def test_plan_chunks_covers_every_page_without_gap_or_overlap():
    assert cloud_chunk.plan_chunks(120, 50) == [(0, 50), (50, 100), (100, 120)]
    assert cloud_chunk.plan_chunks(100, 50) == [(0, 50), (50, 100)]
    assert cloud_chunk.plan_chunks(1, 50) == [(0, 1)]


def test_chunked_pages_keep_original_document_page_numbers(tmp_path):
    """本项最大风险：合并后页号必须 == 原文档真实页号，否则【第N页】证据锚点整体错位。"""
    requested: list[list[int]] = []

    def fetch(path):
        start = int(path.stem.split("-")[1])
        return _pages_for(start, 50 if start < 100 else 20)

    pages, partial = cloud_chunk.recognize_pdf_in_chunks(
        tmp_path / "bid.pdf",
        page_count=120,
        chunk_pages=50,
        extract_subset=_fake_subset_extractor(requested),
        fetch_pages=fetch,
    )

    assert requested == [list(range(50)), list(range(50, 100)), list(range(100, 120))]
    assert [page["page_number"] for page in pages] == list(range(1, 121))
    assert partial is False
    # 每一页的正文来自它该来的那一片、该来的那一页（不是"页号连续但内容错位"）。
    assert pages[0]["markdown"] == "chunk0-local1"
    assert pages[49]["markdown"] == "chunk0-local50"
    assert pages[50]["markdown"] == "chunk50-local1"
    assert pages[99]["markdown"] == "chunk50-local50"
    assert pages[100]["markdown"] == "chunk100-local1"
    assert pages[119]["markdown"] == "chunk100-local20"
    # 子集 PDF 是临时文件，调用方负责删除（extract_pdf_subset 的既定契约）。
    assert list(tmp_path.glob("subset-*.pdf")) == []


def test_failed_chunk_is_marked_and_other_chunks_still_produce_text(tmp_path):
    """部分可读优于整份不可读：失败片按页码范围标 [识别失败]，其余片照常出稿。"""

    def fetch(path):
        start = int(path.stem.split("-")[1])
        if start == 50:
            raise _cloud_failure(status=None)
        return _pages_for(start, 50 if start < 100 else 20)

    pages, partial = cloud_chunk.recognize_pdf_in_chunks(
        tmp_path / "bid.pdf",
        page_count=120,
        chunk_pages=50,
        extract_subset=_fake_subset_extractor([]),
        fetch_pages=fetch,
    )

    assert partial is True
    assert [page["page_number"] for page in pages] == list(range(1, 121))
    assert pages[0]["markdown"] == "chunk0-local1"
    assert pages[100]["markdown"] == "chunk100-local1"
    failed = pages[50:100]
    assert all("[识别失败]" in page["markdown"] for page in failed)
    assert all("51-100" in page["markdown"] for page in failed)


def test_all_chunks_failing_raises_instead_of_returning_an_empty_draft(tmp_path):
    """一片都没成功 → 抛出，绝不用空底稿冒充"读到了"。"""

    def fetch(path):
        raise _cloud_failure(status=None)

    with pytest.raises(OcrError):
        cloud_chunk.recognize_pdf_in_chunks(
            tmp_path / "bid.pdf",
            page_count=120,
            chunk_pages=50,
            extract_subset=_fake_subset_extractor([]),
            fetch_pages=fetch,
        )


def test_unextractable_chunk_is_marked_without_calling_the_upload(tmp_path):
    """本地抽子集失败（返回 None）→ 该片标失败，不把 None 送进上传层。"""
    uploaded: list[object] = []
    extract = _fake_subset_extractor([])

    def fetch(path):
        uploaded.append(path)
        return _pages_for(2, 2)

    pages, partial = cloud_chunk.recognize_pdf_in_chunks(
        tmp_path / "bid.pdf",
        page_count=4,
        chunk_pages=2,
        extract_subset=lambda path, indices: None if indices[0] == 0 else extract(path, indices),
        fetch_pages=fetch,
    )

    assert partial is True
    assert len(uploaded) == 1
    assert "[识别失败]" in pages[0]["markdown"]
    assert pages[2]["markdown"] == "chunk2-local1"


# ── 限流：片间节流 + 有限退避重试 ───────────────────────────────────────────────


def test_rate_limited_chunk_is_retried_with_backoff_then_succeeds(tmp_path):
    """服务端限流回 400；退避重试后应当成功，而不是把整片判失败。"""
    attempts: list[int] = []

    def fetch(path):
        attempts.append(1)
        if len(attempts) <= 2:
            raise _cloud_failure(400)
        return _pages_for(0, 2)

    pages, partial = cloud_chunk.recognize_pdf_in_chunks(
        tmp_path / "bid.pdf",
        page_count=2,
        chunk_pages=2,
        extract_subset=_fake_subset_extractor([]),
        fetch_pages=fetch,
    )

    assert len(attempts) == 3
    assert partial is False
    assert [page["page_number"] for page in pages] == [1, 2]


def test_retry_is_bounded_and_the_chunk_is_finally_marked(tmp_path):
    """退避重试是**有限**的：首片一直 429 不得无限重试，标失败后继续跑后续片。"""
    attempts: list[str] = []

    def fetch(path):
        attempts.append(path.stem)
        if path.stem == "subset-0":
            raise _cloud_failure(429)
        return _pages_for(2, 2)

    pages, partial = cloud_chunk.recognize_pdf_in_chunks(
        tmp_path / "bid.pdf",
        page_count=4,
        chunk_pages=2,
        extract_subset=_fake_subset_extractor([]),
        fetch_pages=fetch,
    )

    assert attempts.count("subset-0") == cloud_chunk._CHUNK_MAX_RETRY + 1
    assert cloud_chunk._CHUNK_MAX_RETRY >= 1
    assert partial is True
    assert "[识别失败]" in pages[0]["markdown"]
    assert pages[2]["markdown"] == "chunk2-local1"


def test_non_retryable_failure_is_not_retried(tmp_path):
    """建 job 返回结构异常之类的确定性失败：重发结果必然相同，不浪费配额重试。"""
    attempts: list[str] = []

    def fetch(path):
        attempts.append(path.stem)
        if path.stem == "subset-0":
            raise OcrError("PaddleOCR 云：建 job 返回异常 {}")
        return _pages_for(2, 2)

    pages, partial = cloud_chunk.recognize_pdf_in_chunks(
        tmp_path / "bid.pdf",
        page_count=4,
        chunk_pages=2,
        extract_subset=_fake_subset_extractor([]),
        fetch_pages=fetch,
    )

    assert attempts.count("subset-0") == 1
    assert partial is True
    assert "[识别失败]" in pages[0]["markdown"]


def test_chunks_are_paced_to_respect_the_server_rate_limit(tmp_path, monkeypatch, _no_sleeping):
    """连发 8 片会从第 3 片起全挂（部署机实测）→ 片间必须留间隔。"""
    monkeypatch.setenv("OCR_CLOUD_CHUNK_PAUSE_SEC", "1.5")

    cloud_chunk.recognize_pdf_in_chunks(
        tmp_path / "bid.pdf",
        page_count=6,
        chunk_pages=2,
        extract_subset=_fake_subset_extractor([]),
        fetch_pages=lambda path: _pages_for(0, 2),
    )

    # 3 片之间 2 个间隔（末片之后不必再等）。
    assert _no_sleeping == [1.5, 1.5]


# ── engine 接线：只有超阈值的 PDF 才分片 ─────────────────────────────────────────


def _wire_cloud(monkeypatch, *, page_count: int, chunk_pages: int) -> list[object]:
    fetched: list[object] = []
    monkeypatch.setattr(engine, "OCR_CLOUD", True)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://ocr.test/jobs")
    monkeypatch.setattr(engine, "OCR_VL_API_KEY", "test-fake-key-not-real")
    monkeypatch.setattr(engine, "OCR_CLOUD_CHUNK_PAGES", chunk_pages)
    monkeypatch.setattr(cloud_chunk, "pdf_page_count", lambda path: page_count)
    monkeypatch.setattr(engine, "extract_pdf_subset", _fake_subset_extractor([]))

    def fake_fetch(path, *, content=None):
        fetched.append(path)
        return _pages_for(0, 2)

    monkeypatch.setattr(engine, "_cloud_fetch_pages", fake_fetch)
    return fetched


def test_large_pdf_takes_the_chunked_upload_path(tmp_path, monkeypatch):
    pdf = tmp_path / "bid.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    fetched = _wire_cloud(monkeypatch, page_count=6, chunk_pages=2)

    result = engine.recognize(pdf)

    assert len(fetched) == 3
    assert [page["page_number"] for page in result["pages"]] == [1, 2, 3, 4, 5, 6]
    assert result["engine"] == "paddleocr-cloud"
    assert result["page_artifact"] == "cloud_seq"


def test_small_pdf_still_uploads_in_one_shot(tmp_path, monkeypatch):
    """小文件走原路径逐字节不变——分片只为绕开服务端大包上限。"""
    pdf = tmp_path / "bid.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    fetched = _wire_cloud(monkeypatch, page_count=2, chunk_pages=50)

    result = engine.recognize(pdf)

    assert fetched == [pdf]
    assert [page["page_number"] for page in result["pages"]] == [1, 2]


def test_chunk_page_threshold_defaults_to_the_measured_safe_size():
    """部署机实测：50 页(3.24 MB) 成功、80 页 HTTP 400。"""
    assert cloud_chunk.DEFAULT_CHUNK_PAGES == 50


# ── extract_pdf_subset 存盘压缩（子集不得比原文件还大）────────────────────────────


class _FakeSubsetDoc:
    def __init__(self, page_count: int = 0) -> None:
        self.page_count = page_count
        self.save_kwargs: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def insert_pdf(self, _src, *, from_page, to_page):
        self.page_count += to_page - from_page + 1

    def save(self, target, **kwargs):
        self.save_kwargs = kwargs
        open(target, "wb").close()

    def close(self):
        return None


def test_subset_is_saved_with_resource_garbage_collection_and_compression(tmp_path, monkeypatch):
    """insert_pdf 复制共享资源（字体/图片）；不带 garbage/deflate/clean 存盘即体积爆炸。"""
    subset = _FakeSubsetDoc()

    class _FakeFitz:
        @staticmethod
        def open(path=None):
            return subset if path is None else _FakeSubsetDoc(page_count=400)

    monkeypatch.setitem(sys.modules, "pymupdf", _FakeFitz)

    out = engine.extract_pdf_subset(tmp_path / "src.pdf", [0, 1])

    assert out is not None
    out.unlink()
    assert subset.save_kwargs == {"garbage": 4, "deflate": True, "clean": True}


def test_pdf_subset_is_never_larger_than_the_source_document(tmp_path):
    """实测反例：100 页子集 43.6 MB > 400 页原文件 43.2 MB（未压缩存盘）。"""
    fitz = pytest.importorskip("pymupdf")

    src = tmp_path / "src.pdf"
    doc = fitz.open()
    for index in range(20):
        page = doc.new_page()
        page.insert_text(
            (50, 50),
            f"page-{index} " + "本项目采用公开招标方式。" * 30,
            fontname="china-s",
            fontsize=8,
        )
    doc.save(str(src), garbage=4, deflate=True, clean=True)
    doc.close()

    out = engine.extract_pdf_subset(src, list(range(10)))

    assert out is not None
    try:
        assert out.stat().st_size <= src.stat().st_size
    finally:
        out.unlink()
