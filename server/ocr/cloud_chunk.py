"""云 OCR 大文件按页分片上传（2026-08-14 生产 P0 Bug B）。

事故：400 页 / 43.2 MB 投标 PDF 整包 POST 给 PaddleOCR 云 job API →
``PaddleOCR 云调用失败：<urlopen error EOF occurred in violation of protocol>`` →
``tender_bid_doc_ocr_failed``，投标文件完全读不出。部署机实测定位到三件事：

1. ``HTTP_PROXY/HTTPS_PROXY`` 未把 OCR 域名放进 ``NO_PROXY``，43 MB 穿代理被掐断
   （运维侧修 .env，代码不处理代理）；
2. 绕过代理后服务端对大包直接 ``HTTP 400``——逐档实测 **50 页(3.24 MB) 成功 / 80 页 400**；
3. 服务端有限流：连发大包后连 2 页的小包也被 400 拒绝，冷却几十秒才恢复。

因此超阈值的 PDF 按页分片上传，片间留间隔，可重试状态码有限退避重试。

**页号对齐是本模块最重要的不变量**：合并后的 ``page_number`` 必须等于原文档真实页号。页号来自
**本片起始页索引 + 片内序号**（不是跨片累加），因此某片少返回几页也不会把后续片整体平移；
错误的 ``【第N页】`` 证据锚点比没有证据更危险。整份页数与 classify 结果不符时仍由
``pipeline._guard_cloud_page_count`` 兜底降级（``page_artifact=cloud_seq`` 语义不变）。

上传与抽子集两个动作由调用方注入（``server.ocr.engine`` 持有端点配置与 ``extract_pdf_subset``），
本模块不反向 import engine。
"""

from __future__ import annotations

import logging
import os
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path

from server.ocr import OcrDependencyError, OcrError
from server.ocr.draft_render import OCR_ERROR_PREFIX
from server.ocr.locks import FITZ_LOCK

logger = logging.getLogger(__name__)

# 单片页数。部署机实测（2026-08-14，43.2 MB / 400 页投标 PDF，绕过代理后）：
# 50 页 / 3.24 MB 建 job 成功，80 页 HTTP 400 Bad Request → 取实测安全档 50。
DEFAULT_CHUNK_PAGES = 50
# 片间间隔：连发 8 片会从第 3 片起被限流全挂（实测），故默认隔 2 秒再发下一片。
_DEFAULT_CHUNK_PAUSE_SEC = 2.0
# 单片重试次数（共 3 次尝试）与退避基数。限流冷却实测在几十秒量级 → 10s、20s 两档退避。
_CHUNK_MAX_RETRY = 2
_RETRY_BACKOFF_BASE_SEC = 10.0
# 可重试状态码。400 也在内：该服务端把限流拒绝也回成 400（实测同一 2 页小包冷却后即成功）。
_RETRYABLE_STATUS = frozenset({400, 408, 429, 500, 502, 503, 504})


def _chunk_pause_sec() -> float:
    """Return the inter-chunk pause (reads ``OCR_CLOUD_CHUNK_PAUSE_SEC`` live)."""
    raw = (os.getenv("OCR_CLOUD_CHUNK_PAUSE_SEC") or "").strip()
    try:
        value = float(raw) if raw else _DEFAULT_CHUNK_PAUSE_SEC
    except ValueError:
        return _DEFAULT_CHUNK_PAUSE_SEC
    return max(0.0, value)


def _pause(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def pdf_page_count(path: Path) -> int | None:
    """Return the PDF page count, or ``None`` when it cannot be determined locally.

    ``None`` 与 ``extract_pdf_subset`` 同一契约：本地读不出（缺 pymupdf / 文件坏）就回退整份
    上传，不抛异常——分片是**优化**，不是新的失败点。
    """
    try:
        import pymupdf as fitz
    except ImportError:
        return None
    try:
        with FITZ_LOCK, fitz.open(path) as document:
            return int(document.page_count)
    except Exception:
        return None


def plan_chunks(page_count: int, chunk_pages: int) -> list[tuple[int, int]]:
    """Split ``page_count`` pages into consecutive 0-based ``[start, end)`` ranges.

    Args:
        page_count: 文档真实页数。
        chunk_pages: 单片页数上限。

    Returns:
        无空洞、无重叠、按页序排列的区间列表。
    """
    return [
        (start, min(start + chunk_pages, page_count))
        for start in range(0, page_count, chunk_pages)
    ]


def _is_retryable(exc: BaseException) -> bool:
    """限流 / 瞬时传输失败可重试；建 job 返回结构异常等确定性失败不重试。"""
    cause = exc.__cause__
    if isinstance(cause, urllib.error.HTTPError):
        return cause.code in _RETRYABLE_STATUS
    return isinstance(cause, (urllib.error.URLError, TimeoutError))


def _fetch_with_backoff(
    subset_path: Path, fetch_pages: Callable[[Path], list[dict]], *, first_page: int
) -> list[dict]:
    """Upload one chunk, retrying rate-limited / transient failures with bounded backoff."""
    for attempt in range(_CHUNK_MAX_RETRY + 1):
        try:
            return fetch_pages(subset_path)
        except (OcrError, OcrDependencyError) as exc:
            if attempt >= _CHUNK_MAX_RETRY or not _is_retryable(exc):
                raise
            logger.warning(
                "cloud_ocr_chunk_retry",
                extra={"first_page": first_page, "attempt": attempt + 1, "reason": str(exc)},
            )
            _pause(_RETRY_BACKOFF_BASE_SEC * (attempt + 1))
    # 不可达：循环要么 return 要么在最后一次 attempt re-raise。
    raise AssertionError("unreachable: chunk retry loop exited without returning")


def _recognize_chunk(
    path: Path,
    start: int,
    end: int,
    extract_subset: Callable[[Path, list[int]], Path | None],
    fetch_pages: Callable[[Path], list[dict]],
) -> list[dict]:
    """Recognize pages ``[start, end)`` and restamp them with their original page numbers."""
    subset_path = extract_subset(path, list(range(start, end)))
    if subset_path is None:
        raise OcrError(f"PaddleOCR 云分片：本地抽取第 {start + 1}-{end} 页子集 PDF 失败")
    try:
        raw_pages = _fetch_with_backoff(subset_path, fetch_pages, first_page=start + 1)
    finally:
        # extract_pdf_subset 的既定契约：调用方负责删除临时子集。
        subset_path.unlink(missing_ok=True)
    return [
        {**page, "page_number": start + offset} for offset, page in enumerate(raw_pages, start=1)
    ]


def _failure_pages(start: int, end: int, reason: BaseException) -> list[dict]:
    """整片失败时，为该片每一页留一条可见的失败标记（部分可读优于整份不可读）。"""
    marker = f"{OCR_ERROR_PREFIX} 第{start + 1}-{end}页分片云 OCR 失败: {reason}"
    return [
        {
            "page_number": number,
            "markdown": marker,
            "layout": [],
            "confidence": None,
            "error": str(reason),
        }
        for number in range(start + 1, end + 1)
    ]


def recognize_pdf_in_chunks(
    path: Path,
    *,
    page_count: int,
    chunk_pages: int,
    extract_subset: Callable[[Path, list[int]], Path | None],
    fetch_pages: Callable[[Path], list[dict]],
) -> tuple[list[dict], bool]:
    """Recognize a large PDF by uploading page chunks instead of the whole file.

    Args:
        path: 原始 PDF 路径。
        page_count: 文档真实页数（``pdf_page_count`` 产出）。
        chunk_pages: 单片页数上限。
        extract_subset: 抽子集 PDF 的可调用对象（``engine.extract_pdf_subset``）；返回临时文件
            路径，本函数负责删除；返回 ``None`` 视为该片失败。
        fetch_pages: 单次上传识别的可调用对象（``engine._cloud_fetch_pages``）。

    Returns:
        ``(pages, partial)``——``pages`` 的 ``page_number`` 与原文档页号一一对应；
        ``partial`` 表示有片失败并已折成可见的 ``[识别失败]`` 标记页。

    Raises:
        OcrError: 所有片都失败（空底稿没有价值，且会掩盖整份失败）。
    """
    chunks = plan_chunks(page_count, chunk_pages)
    pause = _chunk_pause_sec()
    pages: list[dict] = []
    failed = 0
    for position, (start, end) in enumerate(chunks):
        if position:
            # 服务端限流：连发会从第 3 片起全挂，片间必须留间隔。
            _pause(pause)
        try:
            pages.extend(_recognize_chunk(path, start, end, extract_subset, fetch_pages))
        except (OcrError, OcrDependencyError) as exc:
            failed += 1
            logger.warning(
                "cloud_ocr_chunk_failed",
                extra={"first_page": start + 1, "last_page": end, "reason": str(exc)},
            )
            pages.extend(_failure_pages(start, end, exc))
    if failed == len(chunks):
        raise OcrError(
            f"PaddleOCR 云分片 OCR 全部失败（{len(chunks)} 片 / {page_count} 页），整份不可读"
        )
    return pages, failed > 0
