"""OCR 引擎客户端：PaddleOCR-VL / LiteLLM OCR + PaddleX 印章产线。

⚠️ 引擎 API 签名以实际安装的 paddleocr / paddlex 版本与部署的 serving 为准
（见 .claude/skills/multi-ocr/references/engines.md + 官方文档）；POC 阶段须对真实
文件/端点核对返回结构后定稿。默认走 LiteLLM/OpenAI 兼容端点以避开本地 layout predictor
在部分 arm64 容器运行时的 native 崩溃；需要完整 pipeline 时显式开启
OCR_VL_USE_PADDLE_PIPELINE=1。依赖在函数内导入，缺失抛 OcrDependencyError。

PaddleOCR-VL 文档: https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html
PaddleX 印章产线: https://paddlepaddle.github.io/PaddleX/latest/pipeline_usage/tutorials/ocr_pipelines/seal_recognition.html
"""

from __future__ import annotations

import base64
import json
import os
import selectors
import shutil
import signal
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import warnings
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from server.ocr import OcrDependencyError, OcrError, cloud_chunk, vlm_client
from server.ocr.locks import FITZ_LOCK, PADDLE_LOCK

# PaddleOCR-VL 完整 pipeline 可选启用；默认由 LiteLLM/OpenAI-compatible 端点做整页识别。
OCR_VL_PIPELINE_VERSION = os.getenv("OCR_VL_PIPELINE_VERSION", "v1.6")
OCR_VL_BACKEND = os.getenv("OCR_VL_BACKEND", "vllm-server")
OCR_VL_SERVER_URL = os.getenv("OCR_VL_SERVER_URL")  # litellm OpenAI 端点，例 http://litellm:4000/v1
OCR_VL_MODEL_NAME = os.getenv("OCR_VL_MODEL_NAME")  # litellm 里为 PaddleOCR-VL 注册的 model_name
OCR_VL_MAX_CONCURRENCY = os.getenv("OCR_VL_MAX_CONCURRENCY")  # 可选，向网关并发数
OCR_VL_API_KEY = os.getenv("OCR_VL_API_KEY")
OCR_VL_TIMEOUT = float(os.getenv("OCR_VL_TIMEOUT", "120"))
OCR_VL_PDF_RENDER_SCALE = float(os.getenv("OCR_VL_PDF_RENDER_SCALE", "2"))
OCR_VL_USE_PADDLE_PIPELINE = os.getenv("OCR_VL_USE_PADDLE_PIPELINE", "0").lower() in {
    "1",
    "true",
    "yes",
}
OCR_SEAL_PIPELINE = os.getenv("OCR_SEAL_PIPELINE", "seal_recognition")

# 线上 PaddleOCR-VL 云服务（aistudio job API）：OCR_CLOUD=1 走云（异步 job-poll，服务端切页+版面，
# 无需本地渲染/无需本地 paddleocr），=0 走上面的 OpenAI 兼容/本地 pipeline。复用同一套
# OCR_VL_SERVER_URL(=job url)/OCR_VL_API_KEY/OCR_VL_MODEL_NAME，换 litellm 只改 .env 这三行的值。
OCR_CLOUD = os.getenv("OCR_CLOUD", "0").lower() in {"1", "true", "yes"}
OCR_VL_CLOUD_POLL_INTERVAL = float(os.getenv("OCR_VL_CLOUD_POLL_INTERVAL", "5"))
# 云 job 轮询总超时。默认 1200 对齐 TENDER_TIMEOUT_SEC——混合大标书整份/子集云 OCR 在云端排队时，
# 旧默认 600 会误判超时（评标整体仍有 TENDER_TIMEOUT 兜底，audit 侧由 AUDIT_TIMEOUT_SEC 上限收口）。
OCR_VL_CLOUD_MAX_WAIT = float(os.getenv("OCR_VL_CLOUD_MAX_WAIT", "1200"))


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


# KD3 客户端并发闸：逐页 VLM 此前只在本地 paddle pipeline 接了 OCR_VL_MAX_CONCURRENCY，
# openai-compatible 路径直接 urllib 裸调 → 预热 4×6 + inline 6 线程可 ~30 路并发打网关，
# 页级超时暴增。进程级信号量与 office_convert 的 BoundedSemaphore 同构，默认 4。
_VLM_MAX_CONCURRENCY = _positive_int_env("OCR_VL_MAX_CONCURRENCY", 4)
_VLM_SEMAPHORE = threading.BoundedSemaphore(_VLM_MAX_CONCURRENCY)
# KD1 单页重试的固定退避（秒）。常量而非 env：只有一个现实取值，测试经 monkeypatch 置 0。
_VLM_RETRY_BACKOFF_SEC = 2.0

OCR_MAX_PDF_PAGES = _positive_int_env("OCR_MAX_PDF_PAGES", 500)
# 云 job API 单次上传的页数上限，超过则按页分片（2026-08-14 P0：43.2 MB / 400 页整包上传被
# 服务端拒绝，投标文件完全读不出）。默认值的实测出处见 ``cloud_chunk.DEFAULT_CHUNK_PAGES``。
OCR_CLOUD_CHUNK_PAGES = _positive_int_env(
    "OCR_CLOUD_CHUNK_PAGES", cloud_chunk.DEFAULT_CHUNK_PAGES
)
OCR_MAX_PAGE_PIXELS = _positive_int_env("OCR_MAX_PAGE_PIXELS", 25_000_000)
OCR_MAX_TEMP_BYTES = _positive_int_env("OCR_MAX_TEMP_BYTES", 536_870_912)
OCR_MAX_IMAGE_BYTES = _positive_int_env("OCR_MAX_IMAGE_BYTES", 32 * 1024 * 1024)
OCR_PAGE_TIMEOUT_SEC = _positive_int_env("OCR_PAGE_TIMEOUT_SEC", 90)
OCR_MAX_TEXT_CHARS_PER_PAGE = _positive_int_env("OCR_MAX_TEXT_CHARS_PER_PAGE", 200_000)

_IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _make_ssl_context() -> ssl.SSLContext | None:
    """用 certifi 的 CA 包构造 SSL context——urllib 默认在 macOS 等环境找不到系统 CA 会
    CERTIFICATE_VERIFY_FAILED（requests 自带 certifi 故无此问题）。缺 certifi 则回落系统默认。
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


_SSL_CONTEXT = _make_ssl_context()


def _build_vl_pipeline():
    """构造 PaddleOCR-VL 完整 pipeline，可选挂到已部署的 vLLM serving 后端。

    API 对齐 PaddleOCR 3.x 官方文档：pipeline_version + vl_rec_backend + vl_rec_server_url。
    """
    try:
        from paddleocr import PaddleOCRVL
    except ImportError as exc:
        raise OcrDependencyError(
            "缺少 paddleocr：audit-agent 容器内 pip install 'paddleocr[doc-parser]>=3.4.0'"
        ) from exc
    kwargs: dict = {"pipeline_version": OCR_VL_PIPELINE_VERSION}
    if OCR_VL_SERVER_URL:
        # VLM 推理走统一 litellm 网关（OpenAI 兼容）；vl_rec_api_model_name 必须等于
        # litellm 里为 PaddleOCR-VL 注册的 model_name，否则上游 "model does not exist"。
        kwargs["vl_rec_backend"] = OCR_VL_BACKEND
        kwargs["vl_rec_server_url"] = OCR_VL_SERVER_URL
        if OCR_VL_MODEL_NAME:
            kwargs["vl_rec_api_model_name"] = OCR_VL_MODEL_NAME
        if OCR_VL_MAX_CONCURRENCY:
            kwargs["vl_rec_max_concurrency"] = int(OCR_VL_MAX_CONCURRENCY)
    return PaddleOCRVL(**kwargs)


def _build_seal_pipeline():
    try:
        from paddlex import create_pipeline
    except ImportError as exc:
        raise OcrDependencyError("缺少 paddlex：pip install paddlex（印章产线）") from exc
    return create_pipeline(pipeline=OCR_SEAL_PIPELINE)


def _page_markdown(res) -> str:
    """res.markdown 是 dict（keys: markdown_texts / markdown_images / page_continuation_flags）。"""
    markdown = getattr(res, "markdown", None)
    if isinstance(markdown, dict):
        return markdown.get("markdown_texts", "")
    return markdown or ""


def _mime_type(path: Path) -> str:
    return _IMAGE_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"


def _image_data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class _TimedPipeReader:
    """Deadline-aware unbuffered reader for the renderer's framed stdout."""

    def __init__(self, stream) -> None:
        self._fd = stream.fileno()
        self._buffer = bytearray()
        self.eof = False

    def _fill(self, deadline: float) -> bool:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        with selectors.DefaultSelector() as selector:
            selector.register(self._fd, selectors.EVENT_READ)
            if not selector.select(remaining):
                return False
        chunk = os.read(self._fd, 65_536)
        if not chunk:
            self.eof = True
            return False
        self._buffer.extend(chunk)
        return True

    def readline(self, deadline: float) -> bytes | None:
        while b"\n" not in self._buffer:
            if not self._fill(deadline):
                return None
        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = bytearray(rest)
        return bytes(line)

    def read_exact(self, length: int, deadline: float) -> bytes | None:
        while len(self._buffer) < length:
            if not self._fill(deadline):
                return None
        content = bytes(self._buffer[:length])
        del self._buffer[:length]
        return content


def _render_worker_argv(path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "server.ocr.page_render_worker",
        str(path),
        str(OCR_VL_PDF_RENDER_SCALE),
        str(OCR_MAX_PAGE_PIXELS),
    ]


def _terminate_render_process(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _renderer_error(process: subprocess.Popen[bytes]) -> str:
    if process.poll() is None:
        return "renderer closed its output stream before completing"
    if process.stderr is None:
        return "renderer exited without diagnostics"
    detail = process.stderr.read().decode("utf-8", "replace").strip()
    return detail[-1000:] or "renderer exited without diagnostics"


def _read_render_header(reader: _TimedPipeReader, process, page_number: int) -> dict:
    deadline = time.monotonic() + OCR_PAGE_TIMEOUT_SEC
    line = reader.readline(deadline)
    if line is None:
        if reader.eof:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            raise OcrDependencyError(
                f"PDF page {page_number} render failed: {_renderer_error(process)}"
            )
        if process.poll() is None:
            raise TimeoutError(f"PDF page {page_number} render timed out")
        raise OcrDependencyError(
            f"PDF page {page_number} render failed: {_renderer_error(process)}"
        )
    try:
        return json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OcrDependencyError("PDF renderer returned an invalid frame") from exc


def _render_pdf_pages(path: Path):
    """Stream pages from a killable renderer process with a hard per-page timeout."""
    process = subprocess.Popen(
        _render_worker_argv(path),
        shell=False,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert process.stdout is not None
    reader = _TimedPipeReader(process.stdout)
    total_bytes = 0
    try:
        metadata = _read_render_header(reader, process, 1)
        page_count = metadata.get("page_count")
        if not isinstance(page_count, int) or page_count < 1:
            raise OcrDependencyError("PDF render failed: no pages")
        if page_count > OCR_MAX_PDF_PAGES:
            raise OcrDependencyError(
                f"PDF page count {page_count} exceeds configured limit {OCR_MAX_PDF_PAGES}"
            )
        for page_number in range(1, page_count + 1):
            deadline = time.monotonic() + OCR_PAGE_TIMEOUT_SEC
            header = _read_render_header(reader, process, page_number)
            length = header.get("length")
            remaining_bytes = OCR_MAX_TEMP_BYTES - total_bytes
            if (
                header.get("type") != "page"
                or header.get("page_number") != page_number
                or not isinstance(length, int)
                or isinstance(length, bool)
                or length < 1
            ):
                raise OcrDependencyError("PDF renderer returned an invalid page frame")
            if length > remaining_bytes:
                raise OcrDependencyError(
                    "PDF rendered bytes exceed configured temporary byte limit"
                )
            content = reader.read_exact(length, deadline)
            if content is None:
                if reader.eof:
                    raise OcrDependencyError(
                        f"PDF page {page_number} render failed: {_renderer_error(process)}"
                    )
                raise TimeoutError(f"PDF page {page_number} render timed out")
            total_bytes += length
            if total_bytes > OCR_MAX_TEMP_BYTES:
                raise OcrDependencyError("PDF rendered bytes exceed configured temporary byte limit")
            yield {"page_number": page_number, "mime_type": "image/png", "content": content}
        returncode = process.wait(timeout=5)
        if returncode != 0:
            raise OcrDependencyError(f"PDF render failed: {_renderer_error(process)}")
    except TimeoutError as exc:
        raise OcrDependencyError(str(exc)) from exc
    finally:
        if process.poll() is None:
            _terminate_render_process(process)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def _iter_pdf_pages(path: Path):
    """Compatibility seam allowing tests/callers to replace the page iterator."""
    return iter(_render_pdf_pages(path))


def _validate_image_resource_limits(path: Path, content: bytes) -> None:
    """Reject malformed or oversized images before base64/network expansion."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise OcrDependencyError("image dimension validation requires Pillow") from exc

    expected_formats = {
        ".bmp": {"BMP"},
        ".jpeg": {"JPEG"},
        ".jpg": {"JPEG"},
        ".png": {"PNG"},
        ".tif": {"TIFF"},
        ".tiff": {"TIFF"},
        ".webp": {"WEBP"},
    }
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                image_format = image.format
                if width <= 0 or height <= 0:
                    raise ValueError("image parser returned invalid dimensions")
                if image_format not in expected_formats.get(path.suffix.lower(), set()):
                    raise ValueError("image content does not match its file extension")
                pixels = width * height
                if pixels > OCR_MAX_PAGE_PIXELS:
                    raise OcrDependencyError("image exceeds configured pixel limit")
                image.verify()
    except OcrDependencyError:
        raise
    except Exception as exc:
        raise OcrDependencyError(f"image dimension validation failed: {exc}") from exc


def _read_image_with_resource_limits(path: Path) -> bytes:
    """Stat-gate an image before allocation, then close TOCTOU and pixel checks."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise OcrDependencyError(f"image stat failed: {exc}") from exc
    if size < 1 or size > OCR_MAX_IMAGE_BYTES:
        raise OcrDependencyError("image exceeds configured image byte limit")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise OcrDependencyError(f"image read failed: {exc}") from exc
    if len(content) < 1 or len(content) > OCR_MAX_IMAGE_BYTES:
        raise OcrDependencyError("image exceeds configured image byte limit")
    _validate_image_resource_limits(path, content)
    return content


def _recognize_tesseract_page(
    content: bytes, *, page_number: int, mime_type: str
) -> str:
    """Run bounded local Tesseract for one already-rendered image page."""
    _ = mime_type
    executable = shutil.which("tesseract")
    if executable is None:
        raise OcrDependencyError("Tesseract command is not installed")
    argv = [executable, "stdin", "stdout", "-l", "chi_sim+eng", "--oem", "1", "--psm", "3"]
    try:
        completed = subprocess.run(
            argv,
            input=content,
            capture_output=True,
            check=False,
            timeout=OCR_PAGE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OcrDependencyError(f"Tesseract failed on page {page_number}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace") if isinstance(completed.stderr, bytes) else str(completed.stderr)
        raise OcrDependencyError(f"Tesseract failed on page {page_number}: {detail[-500:]}")
    if completed.stdout is None:
        output = ""
    elif isinstance(completed.stdout, bytes):
        output = completed.stdout.decode("utf-8", "replace")
    else:
        output = str(completed.stdout)
    text = output.strip()[:OCR_MAX_TEXT_CHARS_PER_PAGE]
    if not text:
        raise OcrDependencyError(f"Tesseract returned no text on page {page_number}")
    return text


def _call_openai_compatible_vlm(
    *, data_url: str, prompt: str, budget_sec: float | None = None
) -> str:
    """Call the remote VLM while preserving the OCR fallback error boundary.

    传输与错误归一在 ``server.ocr.vlm_client``（H3 拆分）；本函数只负责把 engine 侧的运行时配置
    （端点/模型/密钥/超时/TLS 上下文）绑上去——配置读取留在 engine 是有意为之：既有测试与部署
    都以 ``engine.OCR_VL_*`` 为唯一调参面。

    Args:
        data_url: 页图 data URL。
        prompt: 识别提示。
        budget_sec: 本次调用可用的剩余时间预算（秒）。``None`` = 整页预算。重试时由
            ``_call_vlm_page`` 传入剩余量，防"两次尝试各拿整页 timeout"把单页拖成两倍页 deadline。
    """
    timeout = min(OCR_VL_TIMEOUT, OCR_PAGE_TIMEOUT_SEC)
    if budget_sec is not None:
        timeout = min(timeout, budget_sec)
    return vlm_client.call_vlm(
        url=_chat_completions_url(OCR_VL_SERVER_URL),
        model=OCR_VL_MODEL_NAME,
        api_key=OCR_VL_API_KEY,
        data_url=data_url,
        prompt=prompt,
        timeout=timeout,
        ssl_context=_SSL_CONTEXT,
    )


def _call_vlm_page(*, data_url: str, prompt: str) -> str:
    """单页 VLM 调用：并发闸 + 可恢复失败重试一次（KD1 + KD3）。

    闸（``_VLM_SEMAPHORE``）保护网关不被数十路并发打崩——这是页级超时的源头之一。等待发生在
    页 deadline 起算**之前**，故排队时长不吃页预算（页 deadline 的语义是"识别耗时"；排队饿死
    由源头减压治，不由本函数计时）。

    重试固定退避 ``_VLM_RETRY_BACKOFF_SEC``，且"首次尝试 + 退避 + 第二次调用"整体必须落在该页
    ``OCR_PAGE_TIMEOUT_SEC`` 预算内：第二次调用的 timeout **收敛为剩余预算**（review F1——否则
    两次各拿整页 timeout，单页最坏 2× 页 deadline，比不重试更糟）。剩余预算不够退避则直接抛出，
    由调用方按 0730 语义降级 Tesseract。

    Args:
        data_url: 页图 data URL。
        prompt: 该页识别提示。

    Returns:
        VLM 返回的页 markdown。

    Raises:
        OcrDependencyError: 两次尝试都命中可恢复错误，或预算不足以重试。
    """
    with _VLM_SEMAPHORE:
        deadline = time.monotonic() + OCR_PAGE_TIMEOUT_SEC
        try:
            return _call_openai_compatible_vlm(data_url=data_url, prompt=prompt)
        except OcrDependencyError:
            remaining = deadline - time.monotonic() - _VLM_RETRY_BACKOFF_SEC
            if remaining <= 0:
                raise
            time.sleep(_VLM_RETRY_BACKOFF_SEC)
            return _call_openai_compatible_vlm(
                data_url=data_url, prompt=prompt, budget_sec=remaining
            )


def _tesseract_page_or_raise(page: dict, vlm_error: OcrDependencyError) -> str:
    """VLM 失败后的本地 Tesseract 兜底；兜底也失败则抛出合并了两侧原因的错误。"""
    try:
        return _recognize_tesseract_page(
            page["content"], page_number=page["page_number"], mime_type=page["mime_type"]
        )
    except OcrDependencyError as fallback_error:
        raise OcrDependencyError(
            f"{vlm_error}; Tesseract fallback failed: {fallback_error}"
        ) from fallback_error


def _pdf_page_payload(page: dict, *, prompt: str, use_tesseract: bool) -> tuple[dict, bool]:
    """识别一页并组装 payload。返回 ``(payload, use_tesseract)``——一旦降级，页序其后全降级
    （0730 "页只发一次" + 页序连续性决策不变）。"""
    if use_tesseract:
        markdown = _recognize_tesseract_page(
            page["content"], page_number=page["page_number"], mime_type=page["mime_type"]
        )
    else:
        try:
            markdown = _call_vlm_page(
                data_url=_image_data_url(page["content"], page["mime_type"]),
                prompt=f"{prompt}\nThis image is page {page['page_number']} of the PDF.",
            )
        except OcrDependencyError as vlm_error:
            use_tesseract = True
            markdown = _tesseract_page_or_raise(page, vlm_error)
    payload = {
        "markdown": markdown[:OCR_MAX_TEXT_CHARS_PER_PAGE],
        "layout": [],
        "page_number": page["page_number"],
    }
    if use_tesseract:
        payload.update({"engine": "tesseract", "degraded": True, "clarity": "unknown"})
    return payload, use_tesseract


def _page_failure_marker(page_number: int, reason: object) -> dict:
    """KD6：渲染中途失败时替代剩余页的单行标记页（页号 = 首个失败页）。"""
    return {
        "markdown": f"[第{page_number}页起识别失败: {reason}]",
        "layout": [],
        "page_number": page_number,
        "error": str(reason),
    }


def _recognize_pdf_pages_via_vlm(
    path: Path, *, prompt: str, on_page: Callable[[int, dict], None] | None
) -> tuple[list[dict], bool, bool]:
    """逐页识别 PDF，返回 ``(pages, degraded, partial)``。

    KD6：页迭代器中途抛出的**结构化**错误（渲染超时/渲染进程失败等）不再冲出循环报废整份——
    已成功页照常出稿，剩余页折成一行 ``[第M页起识别失败: …]`` 标记，结果标 ``partial``。
    一页都没成功时维持原语义直接抛出（空 partial 底稿没有价值，且会掩盖整份失败）。
    ``MemoryError`` / 取消 / 进程退出仍透传不伪装（0730 设计）。
    """
    pages: list[dict] = []
    use_tesseract = False
    partial = False
    page_iterator = _iter_pdf_pages(path)
    try:
        while True:
            try:
                page = next(page_iterator)
            except StopIteration:
                break
            except (OcrDependencyError, OcrError) as exc:
                if not pages:
                    raise
                pages.append(_page_failure_marker(len(pages) + 1, exc))
                partial = True
                break
            payload, use_tesseract = _pdf_page_payload(
                page, prompt=prompt, use_tesseract=use_tesseract
            )
            pages.append(payload)
            if on_page is not None:
                on_page(page["page_number"], payload)
    finally:
        close_iterator = getattr(page_iterator, "close", None)
        if callable(close_iterator):
            close_iterator()
    return pages, use_tesseract, partial


def _recognize_via_openai_compatible(
    path: Path,
    *,
    purpose: str | None = None,
    on_page: Callable[[int, dict], None] | None = None,
    content: bytes | None = None,
) -> dict:
    """LiteLLM/OpenAI-compatible fallback：让已部署 PaddleOCR-VL 读取图片页面。

    Args:
        path: 待识别文件路径（PDF 或图片）。
        purpose: 场景化识别目的，追加进 prompt。
        on_page: 可选页级完成回调 ``(page_no, {"markdown": str})``。识别循环本就在
            ``FITZ_LOCK``/``PADDLE_LOCK`` 之外（``_render_pdf_pages`` 每页物化后先释放锁再
            yield），故每页识别完成即可直接触发。图片按单页触发一次。
    """
    if not OCR_VL_SERVER_URL or not OCR_VL_MODEL_NAME:
        raise OcrDependencyError(
            "OCR_VL_SERVER_URL / OCR_VL_MODEL_NAME 未配置，无法调用远端 OCR VLM"
        )

    prompt = "Extract all visible document text. Return concise markdown only."
    if purpose:
        # 场景化识别目的（如评标：完整还原评分标准/扣分细则/废标条款表格）——追加在通用提取指令后。
        prompt = f"{prompt}\n{purpose}"
    degraded = False
    partial = False
    if path.suffix.lower() == ".pdf":
        pages, degraded, partial = _recognize_pdf_pages_via_vlm(
            path, prompt=prompt, on_page=on_page
        )
    else:
        if content is None:
            content = _read_image_with_resource_limits(path)
        try:
            markdown = _call_vlm_page(
                data_url=_image_data_url(content, _mime_type(path)),
                prompt=prompt,
            )
        except OcrDependencyError as vlm_error:
            degraded = True
            markdown = _tesseract_page_or_raise(
                {"content": content, "page_number": 1, "mime_type": _mime_type(path)},
                vlm_error,
            )
        markdown = markdown[:OCR_MAX_TEXT_CHARS_PER_PAGE]
        pages = [{"markdown": markdown, "layout": [], "page_number": 1}]
        if degraded:
            pages[0].update({"engine": "tesseract", "degraded": True, "clarity": "unknown"})
        if on_page is not None:
            on_page(1, pages[0])

    result = {
        "kind": "ocr",
        "pipeline_version": OCR_VL_PIPELINE_VERSION,
        "engine": "tesseract" if degraded else "openai-compatible-vlm",
        "pages": pages,
    }
    if degraded:
        result.update({"degraded": True, "clarity": "unknown"})
    if partial:
        # KD6：部分页缺失对下游状态机可见（doc 层落 partial，不冒充 ready）。
        result["partial"] = True
    return result


def _page_confidence(layout: list) -> float | None:
    """从 PaddleOCR-VL 版面块的逐块 ``score`` 聚合页置信度（取**最低块**=页内最糊处）。

    P2：这些 score 此前落在 ``page["layout"]`` 里从未被 surfaced（``build_extraction_block``
    只读 markdown）。layout 项形如 ``{"score"/"confidence": float, ...}``，字段名随 PaddleX
    版本浮动，故宽松扫 ``score|confidence``。无任何 score（如 VLM 端点路径 layout=[]）→ None。
    """
    scores: list[float] = []
    for item in layout if isinstance(layout, list) else []:
        if not isinstance(item, dict):
            continue
        value = item.get("score", item.get("confidence"))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            scores.append(float(value))
    return min(scores) if scores else None


def _recognize_via_paddle_pipeline(
    path: Path,
    *,
    purpose: str | None = None,
    on_page: Callable[[int, dict], None] | None = None,
) -> dict:
    """扫描件 → 每页 markdown + 版面 + 置信度（PaddleOCR-VL 完整 pipeline）。

    注：purpose 对本地 paddle pipeline 暂不生效（固定版面 OCR，无自定义 prompt 注入点）。

    Args:
        on_page: 可选页级完成回调 ``(page_no, {"markdown", "layout", "confidence"})``。
            **buffer-then-fire**：页结果先收集到本地 list，退出 ``with PADDLE_LOCK`` 临界区
            后才逐条回放——回调绝不在持有 ``PADDLE_LOCK`` 时被调用（D9 T1，同 native.read_pdf_text
            纪律，防并行 OCR 下锁竞争被放大）。
    """
    _ = purpose  # 本地 pipeline 暂无 prompt 注入点，显式忽略避免误导。
    # 本地 PaddleOCR pipeline 非线程安全（全局 predictor/GPU/runtime），并行 OCR 时经 PADDLE_LOCK
    # 串行化（codex P1-4）。predict + 结果物化都在锁内，防 res 惰性求值跨线程触发 paddle。
    page_buffer: list[tuple[int, dict]] = []
    with PADDLE_LOCK:
        results = _build_vl_pipeline().predict(str(path))
        pages = []
        for page_no, res in enumerate(results, start=1):
            data = res.json if hasattr(res, "json") else {}
            layout = data.get("parsing_res_list", data.get("layout", []))
            page_payload = {
                "markdown": _page_markdown(res),
                "layout": layout,
                "confidence": _page_confidence(layout),
            }
            pages.append(page_payload)
            if on_page is not None:
                page_buffer.append((page_no, page_payload))
    if on_page is not None:  # 锁已释放，此时才回放（buffer-then-fire）
        for page_no, payload in page_buffer:
            on_page(page_no, payload)
    return {"kind": "ocr", "pipeline_version": OCR_VL_PIPELINE_VERSION, "pages": pages}


def _post_multipart(
    url: str,
    *,
    fields: dict[str, str],
    file_path: Path,
    headers: dict[str, str],
    file_content: bytes | None = None,
) -> dict:
    """urllib 手搓 multipart/form-data 上传（项目不装 requests）。返回解析后的 JSON。"""
    boundary = "----ocrcloud" + base64.urlsafe_b64encode(os.urandom(12)).decode("ascii")
    safe_name = f"upload{file_path.suffix.lower()}"  # 避非 ASCII 文件名在 multipart 头里的编码坑
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'.encode()
    )
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(file_path.read_bytes() if file_content is None else file_content)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        url,
        data=b"".join(parts),
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=OCR_VL_TIMEOUT, context=_SSL_CONTEXT) as response:
        return json.loads(response.read().decode("utf-8"))


def _cloud_submit_job(path: Path, *, content: bytes | None = None) -> str:
    """上传文件建 OCR job（Local File Mode）→ 返回 jobId。"""
    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }
    payload = _post_multipart(
        OCR_VL_SERVER_URL,
        fields={"model": OCR_VL_MODEL_NAME or "", "optionalPayload": json.dumps(optional_payload)},
        file_path=path,
        headers={"Authorization": f"Bearer {OCR_VL_API_KEY}"},
        file_content=content,
    )
    try:
        return payload["data"]["jobId"]
    except (KeyError, TypeError) as exc:
        raise OcrError(f"PaddleOCR 云：建 job 返回异常 {payload!r}") from exc


def _cloud_poll_until_done(job_id: str) -> str:
    """轮询 job 直到 done → 返回 jsonl url；failed/超时抛 OcrError（总超时 OCR_VL_CLOUD_MAX_WAIT）。"""
    job_url = f"{OCR_VL_SERVER_URL.rstrip('/')}/{job_id}"
    headers = {"Authorization": f"Bearer {OCR_VL_API_KEY}"}
    deadline = time.monotonic() + OCR_VL_CLOUD_MAX_WAIT
    while True:
        request = urllib.request.Request(job_url, headers=headers)
        with urllib.request.urlopen(
            request, timeout=OCR_VL_TIMEOUT, context=_SSL_CONTEXT
        ) as response:
            data = json.loads(response.read().decode("utf-8")).get("data", {})
        state = data.get("state")
        if state == "done":
            return data["resultUrl"]["jsonUrl"]
        if state == "failed":
            raise OcrError(f"PaddleOCR 云 job 失败：{data.get('errorMsg')}")
        if time.monotonic() >= deadline:
            raise OcrError(f"PaddleOCR 云 job 超时（>{int(OCR_VL_CLOUD_MAX_WAIT)}s，末态 {state}）")
        time.sleep(OCR_VL_CLOUD_POLL_INTERVAL)


def _parse_cloud_jsonl(jsonl_text: str) -> list[dict]:
    """解析 PaddleOCR 云 jsonl：每行 result.layoutParsingResults[] → 页（**只取文本，不下图**）。

    置信度尽力而为：版面里若有逐块 score(prunedResult/layout)，经 _page_confidence 接出；无则 None。
    """
    pages: list[dict] = []
    for line in jsonl_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        result = json.loads(line).get("result", {})
        for res in result.get("layoutParsingResults", []):
            markdown = res.get("markdown", {})
            text = markdown.get("text", "") if isinstance(markdown, dict) else str(markdown or "")
            layout = res.get("prunedResult") or res.get("layout") or []
            layout = layout if isinstance(layout, list) else []
            pages.append(
                {
                    # 连续页号（跨 jsonl 行累加）。否则 pages 缺 page_number → draft_render.render_body
                    # 回退按渲染顺序枚举；整份云 OCR（混合 PDF 全文转云）时若下游过滤/重排页列表，
                    # 枚举序号会与真实页错位 → evidence 回查【第N页】定位失准（伤 G2）。显式钉页号。
                    "page_number": len(pages) + 1,
                    "markdown": text,
                    "layout": layout,
                    "confidence": _page_confidence(layout),
                }
            )
    return pages


def _cloud_fetch_pages(path: Path, *, content: bytes | None = None) -> list[dict]:
    """一次上传单元：建 job → 轮询 → 取 jsonl → 解析成页列表（页号为本次上传的顺序号）。"""
    try:
        job_id = _cloud_submit_job(path, content=content)
        jsonl_url = _cloud_poll_until_done(job_id)
        request = urllib.request.Request(jsonl_url)
        with urllib.request.urlopen(
            request, timeout=OCR_VL_TIMEOUT, context=_SSL_CONTEXT
        ) as response:
            jsonl_text = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        # from exc 保留 HTTPError.code——cloud_chunk 据此区分"限流可重试"与"确定性失败"。
        raise OcrError(f"PaddleOCR 云调用失败：{exc}") from exc
    return _parse_cloud_jsonl(jsonl_text)


def _cloud_result(pages: list[dict], *, partial: bool = False) -> dict:
    result = {
        "kind": "ocr",
        "pipeline_version": OCR_VL_PIPELINE_VERSION,
        "engine": "paddleocr-cloud",
        # 页号是**云返回结果的顺序号**（_parse_cloud_jsonl 跨行累加；分片路径再叠加本片起始页
        # 偏移），不是文档页号——云端跳页/合并即平移。标出坐标系，pipeline._guard_cloud_page_count
        # 据此比对 classify 页数，不一致则整份 page_confidence=low（H2 KD1 cloud_seq）。
        "page_artifact": "cloud_seq",
        "pages": pages,
    }
    if partial:
        # 有片失败已折成 [识别失败] 标记页 → 对下游状态机可见（doc 层落 partial，不冒充 ready）。
        result["partial"] = True
    return result


def _recognize_via_paddle_cloud(
    path: Path, *, purpose: str | None = None, content: bytes | None = None
) -> dict:
    """线上 PaddleOCR-VL 云服务（aistudio job API）：建 job → 轮询 → 取 jsonl。

    协议与 OpenAI 兼容路径完全不同（异步 job-poll）。服务端切页+版面，**无需本地渲染/本地 paddleocr**。
    失败/超时抛异常由 pipeline per-file 隔离（→ kind=error / file_clarity=failed），绝不静默。

    超过 ``OCR_CLOUD_CHUNK_PAGES`` 页的 PDF 改走分片上传（2026-08-14 P0：43.2 MB / 400 页整包
    被服务端拒绝）；阈值以下逐字节走原路径——分片只为绕开服务端大包上限，不改小文件行为。

    注：purpose 对云 job API 暂不生效——服务端固定版面+OCR，不接受自定义 prompt；
    保留参数统一调用链，待云服务支持识别提示再启用。
    """
    _ = purpose  # 云路径暂无 prompt 注入点（见 docstring），显式忽略避免误导。
    if not OCR_VL_SERVER_URL or not OCR_VL_API_KEY:
        raise OcrDependencyError("OCR_CLOUD=1 但 OCR_VL_SERVER_URL / OCR_VL_API_KEY 未配置")
    if content is None and path.suffix.lower() == ".pdf":
        page_count = cloud_chunk.pdf_page_count(path)
        if page_count is not None and page_count > OCR_CLOUD_CHUNK_PAGES:
            pages, partial = cloud_chunk.recognize_pdf_in_chunks(
                path,
                page_count=page_count,
                chunk_pages=OCR_CLOUD_CHUNK_PAGES,
                extract_subset=extract_pdf_subset,
                fetch_pages=_cloud_fetch_pages,
            )
            return _cloud_result(pages, partial=partial)
    return _cloud_result(_cloud_fetch_pages(path, content=content))


def extract_pdf_subset(path: Path, page_indices: list[int]) -> Path | None:
    """把 PDF 的指定页（0-based, 升序）抽成一份临时 PDF，返回路径；本地失败返回 None。

    用于混合 PDF 只补扫描页：调用方对返回的子集 PDF 跑 ``recognize`` 走当前配置引擎，只 OCR
    扫描页、避免整份重 OCR 覆盖数字页的原生高保真文本。**调用方负责删除**返回的临时文件。
    fitz 缺失 / 渲染失败 → None（调用方据此回退整份云 OCR）；不抛异常以保留回退路径。

    fitz 非线程安全，经共享 ``FITZ_LOCK`` 串行化（与 native 直读 / 整页渲染共用同一把锁）。

    存盘必须带 ``garbage=4, deflate=True, clean=True``（2026-08-14 P0）：``insert_pdf`` 会把
    共享资源（字体/图片）逐页复制进子集，裸存实测 **100 页子集 43.6 MB > 400 页原文件 43.2 MB**；
    带上三参后 50 页子集 20.3 MB → 3.24 MB。混合 PDF 补扫描页那条既有路径同样受益。
    """
    if not page_indices:
        return None
    try:
        import pymupdf as fitz
    except ImportError:
        return None
    tmp_path: Path | None = None
    try:
        with FITZ_LOCK, fitz.open(path) as src:
            subset = fitz.open()
            try:
                for idx in page_indices:
                    if 0 <= idx < src.page_count:
                        subset.insert_pdf(src, from_page=idx, to_page=idx)
                if subset.page_count == 0:
                    return None
                fd, name = tempfile.mkstemp(suffix=".pdf")
                os.close(fd)
                tmp_path = Path(name)
                subset.save(str(tmp_path), garbage=4, deflate=True, clean=True)
            finally:
                subset.close()
        return tmp_path
    except Exception:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return None


def recognize(
    path: Path,
    *,
    purpose: str | None = None,
    on_page: Callable[[int, dict], None] | None = None,
) -> dict:
    """扫描件识别。

    OCR_CLOUD=1 走线上 PaddleOCR-VL 云服务（job-poll）；否则默认走 LiteLLM/OpenAI-compatible
    远端 VLM，避开本地 layout predictor 在部分 arm64 容器运行时的 native 崩溃；需要完整
    PaddleOCRVL pipeline 时显式设 OCR_VL_USE_PADDLE_PIPELINE=1。

    purpose：场景化识别目的（如评标），仅 OpenAI-compatible 路径注入进 prompt 生效；
    云 job API / 本地 paddle pipeline 为固定版面 OCR，接受参数但暂不注入（见各自 docstring）。

    on_page：可选页级完成回调（D9 streaming-ocr T1）。云 job-poll 路径（服务端整档返回，
    见 ``_recognize_via_paddle_cloud`` docstring）无中间页可透出，**不接受** on_page——
    该路径粒度为文件级单元，由调用方（``server.ocr.pipeline``）在拿到整份结果后退化为
    一次文件级事件。
    """
    validated_content = None
    if path.suffix.lower() in _IMAGE_MIME_TYPES:
        validated_content = _read_image_with_resource_limits(path)

    if OCR_CLOUD:  # 显式开关优先：=1 走线上云服务（job-poll），与 litellm/本地解耦
        if validated_content is not None:
            return _recognize_via_paddle_cloud(
                path, purpose=purpose, content=validated_content
            )
        return _recognize_via_paddle_cloud(path, purpose=purpose)
    if OCR_VL_SERVER_URL and not OCR_VL_USE_PADDLE_PIPELINE:
        if validated_content is not None:
            return _recognize_via_openai_compatible(
                path,
                purpose=purpose,
                on_page=on_page,
                content=validated_content,
            )
        return _recognize_via_openai_compatible(path, purpose=purpose, on_page=on_page)
    return _recognize_via_paddle_pipeline(path, purpose=purpose, on_page=on_page)


def recognize_seal(path: Path) -> dict:
    """印章 → [{bbox, shape, text, color, confidence}, ...]（字段以版本返回为准）。"""
    # 本地印章 pipeline 非线程安全，与 paddle pipeline 共享 PADDLE_LOCK 串行（codex P1-4）。
    with PADDLE_LOCK:
        results = _build_seal_pipeline().predict(str(path))
        seals: list[dict] = []
        for res in results:
            data = res.json if hasattr(res, "json") else {}
            for item in data.get("seal_res_list") or data.get("rec_texts") or []:
                seals.append(item if isinstance(item, dict) else {"text": item})
    return {"kind": "seal", "seals": seals}
