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
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from server.ocr import OcrDependencyError, OcrError
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
OCR_VL_CLOUD_MAX_WAIT = float(os.getenv("OCR_VL_CLOUD_MAX_WAIT", "600"))


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
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(path.suffix.lower(), "application/octet-stream")


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"


def _image_data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _render_pdf_pages(path: Path) -> list[dict]:
    """PDF 必须先按页渲染成图片，再交给 OpenAI-compatible VLM 的 image_url。"""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise OcrDependencyError("缺少 PyMuPDF：请安装 pymupdf 以支持 PDF 调用远端 OCR VLM") from exc

    pages: list[dict] = []
    try:
        # fitz 非线程安全；与 native 直读共享同一把 FITZ_LOCK 串行化（codex P1-1：扫描 PDF
        # 渲染也调 fitz.open，并行 OCR 时会与 native 直读并发崩）。
        with FITZ_LOCK, fitz.open(path) as document:
            matrix = fitz.Matrix(OCR_VL_PDF_RENDER_SCALE, OCR_VL_PDF_RENDER_SCALE)
            for index, page in enumerate(document):
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                pages.append(
                    {
                        "page_number": index + 1,
                        "mime_type": "image/png",
                        "content": pixmap.tobytes("png"),
                    }
                )
    except Exception as exc:
        raise OcrDependencyError(f"PDF 渲染失败：{exc}") from exc

    if not pages:
        raise OcrDependencyError("PDF 渲染失败：未产生任何页面")
    return pages


def _call_openai_compatible_vlm(*, data_url: str, prompt: str) -> str:
    body = {
        "model": OCR_VL_MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 4096,
    }
    headers = {"Content-Type": "application/json"}
    if OCR_VL_API_KEY:
        headers["Authorization"] = f"Bearer {OCR_VL_API_KEY}"
    request = urllib.request.Request(
        _chat_completions_url(OCR_VL_SERVER_URL),
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=OCR_VL_TIMEOUT, context=_SSL_CONTEXT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = f"HTTP Error {exc.code}: {exc.reason}"
        try:
            response_body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            response_body = ""
        if response_body:
            detail = f"{detail}；响应：{response_body[:1000]}"
        raise OcrDependencyError(f"OCR VLM 远端调用失败：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OcrDependencyError(f"OCR VLM 远端调用失败：{exc}") from exc

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OcrDependencyError(f"OCR VLM 返回结构异常：{payload!r}") from exc


def _recognize_via_openai_compatible(path: Path, *, purpose: str | None = None) -> dict:
    """LiteLLM/OpenAI-compatible fallback：让已部署 PaddleOCR-VL 读取图片页面。"""
    if not OCR_VL_SERVER_URL or not OCR_VL_MODEL_NAME:
        raise OcrDependencyError("OCR_VL_SERVER_URL / OCR_VL_MODEL_NAME 未配置，无法调用远端 OCR VLM")

    prompt = "Extract all visible document text. Return concise markdown only."
    if purpose:
        # 场景化识别目的（如评标：完整还原评分标准/扣分细则/废标条款表格）——追加在通用提取指令后。
        prompt = f"{prompt}\n{purpose}"
    if path.suffix.lower() == ".pdf":
        pages = [
            {
                "markdown": _call_openai_compatible_vlm(
                    data_url=_image_data_url(page["content"], page["mime_type"]),
                    prompt=f"{prompt}\nThis image is page {page['page_number']} of the PDF.",
                ),
                "layout": [],
                "page_number": page["page_number"],
            }
            for page in _render_pdf_pages(path)
        ]
    else:
        markdown = _call_openai_compatible_vlm(
            data_url=_image_data_url(path.read_bytes(), _mime_type(path)),
            prompt=prompt,
        )
        pages = [{"markdown": markdown, "layout": []}]

    return {
        "kind": "ocr",
        "pipeline_version": OCR_VL_PIPELINE_VERSION,
        "engine": "openai-compatible-vlm",
        "pages": pages,
    }


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


def _recognize_via_paddle_pipeline(path: Path, *, purpose: str | None = None) -> dict:
    """扫描件 → 每页 markdown + 版面 + 置信度（PaddleOCR-VL 完整 pipeline）。

    注：purpose 对本地 paddle pipeline 暂不生效（固定版面 OCR，无自定义 prompt 注入点）。
    """
    _ = purpose  # 本地 pipeline 暂无 prompt 注入点，显式忽略避免误导。
    # 本地 PaddleOCR pipeline 非线程安全（全局 predictor/GPU/runtime），并行 OCR 时经 PADDLE_LOCK
    # 串行化（codex P1-4）。predict + 结果物化都在锁内，防 res 惰性求值跨线程触发 paddle。
    with PADDLE_LOCK:
        results = _build_vl_pipeline().predict(str(path))
        pages = []
        for res in results:
            data = res.json if hasattr(res, "json") else {}
            layout = data.get("parsing_res_list", data.get("layout", []))
            pages.append(
                {
                    "markdown": _page_markdown(res),
                    "layout": layout,
                    "confidence": _page_confidence(layout),
                }
            )
    return {"kind": "ocr", "pipeline_version": OCR_VL_PIPELINE_VERSION, "pages": pages}


def _post_multipart(
    url: str, *, fields: dict[str, str], file_path: Path, headers: dict[str, str]
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
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'.encode())
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        url,
        data=b"".join(parts),
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=OCR_VL_TIMEOUT, context=_SSL_CONTEXT) as response:
        return json.loads(response.read().decode("utf-8"))


def _cloud_submit_job(path: Path) -> str:
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
        with urllib.request.urlopen(request, timeout=OCR_VL_TIMEOUT, context=_SSL_CONTEXT) as response:
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
                {"markdown": text, "layout": layout, "confidence": _page_confidence(layout)}
            )
    return pages


def _recognize_via_paddle_cloud(path: Path, *, purpose: str | None = None) -> dict:
    """线上 PaddleOCR-VL 云服务（aistudio job API）：建 job → 轮询 → 取 jsonl。

    协议与 OpenAI 兼容路径完全不同（异步 job-poll）。服务端切页+版面，**无需本地渲染/本地 paddleocr**。
    失败/超时抛异常由 pipeline per-file 隔离（→ kind=error / file_clarity=failed），绝不静默。

    注：purpose 对云 job API 暂不生效——服务端固定版面+OCR，不接受自定义 prompt；
    保留参数统一调用链，待云服务支持识别提示再启用。
    """
    _ = purpose  # 云路径暂无 prompt 注入点（见 docstring），显式忽略避免误导。
    if not OCR_VL_SERVER_URL or not OCR_VL_API_KEY:
        raise OcrDependencyError("OCR_CLOUD=1 但 OCR_VL_SERVER_URL / OCR_VL_API_KEY 未配置")
    try:
        job_id = _cloud_submit_job(path)
        jsonl_url = _cloud_poll_until_done(job_id)
        request = urllib.request.Request(jsonl_url)
        with urllib.request.urlopen(request, timeout=OCR_VL_TIMEOUT, context=_SSL_CONTEXT) as response:
            jsonl_text = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OcrError(f"PaddleOCR 云调用失败：{exc}") from exc
    return {
        "kind": "ocr",
        "pipeline_version": OCR_VL_PIPELINE_VERSION,
        "engine": "paddleocr-cloud",
        "pages": _parse_cloud_jsonl(jsonl_text),
    }


def recognize(path: Path, *, purpose: str | None = None) -> dict:
    """扫描件识别。

    OCR_CLOUD=1 走线上 PaddleOCR-VL 云服务（job-poll）；否则默认走 LiteLLM/OpenAI-compatible
    远端 VLM，避开本地 layout predictor 在部分 arm64 容器运行时的 native 崩溃；需要完整
    PaddleOCRVL pipeline 时显式设 OCR_VL_USE_PADDLE_PIPELINE=1。

    purpose：场景化识别目的（如评标），仅 OpenAI-compatible 路径注入进 prompt 生效；
    云 job API / 本地 paddle pipeline 为固定版面 OCR，接受参数但暂不注入（见各自 docstring）。
    """
    if OCR_CLOUD:  # 显式开关优先：=1 走线上云服务（job-poll），与 litellm/本地解耦
        return _recognize_via_paddle_cloud(path, purpose=purpose)
    if OCR_VL_SERVER_URL and not OCR_VL_USE_PADDLE_PIPELINE:
        return _recognize_via_openai_compatible(path, purpose=purpose)
    return _recognize_via_paddle_pipeline(path, purpose=purpose)


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
