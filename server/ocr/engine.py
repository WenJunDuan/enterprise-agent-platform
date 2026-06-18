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
import urllib.error
import urllib.request
from pathlib import Path

from server.ocr import OcrDependencyError

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
        with fitz.open(path) as document:
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
        with urllib.request.urlopen(request, timeout=OCR_VL_TIMEOUT) as response:
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


def _recognize_via_openai_compatible(path: Path) -> dict:
    """LiteLLM/OpenAI-compatible fallback：让已部署 PaddleOCR-VL 读取图片页面。"""
    if not OCR_VL_SERVER_URL or not OCR_VL_MODEL_NAME:
        raise OcrDependencyError("OCR_VL_SERVER_URL / OCR_VL_MODEL_NAME 未配置，无法调用远端 OCR VLM")

    prompt = "Extract all visible document text. Return concise markdown only."
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


def _recognize_via_paddle_pipeline(path: Path) -> dict:
    """扫描件 → 每页 markdown + 版面（PaddleOCR-VL 完整 pipeline）。"""
    results = _build_vl_pipeline().predict(str(path))
    pages = []
    for res in results:
        data = res.json if hasattr(res, "json") else {}
        pages.append(
            {
                "markdown": _page_markdown(res),
                "layout": data.get("parsing_res_list", data.get("layout", [])),
            }
        )
    return {"kind": "ocr", "pipeline_version": OCR_VL_PIPELINE_VERSION, "pages": pages}


def recognize(path: Path) -> dict:
    """扫描件识别。

    默认走 LiteLLM/OpenAI-compatible 远端 VLM，避开本地 layout predictor 在部分 arm64
    容器运行时的 native 崩溃；需要完整 PaddleOCRVL pipeline 时显式设
    OCR_VL_USE_PADDLE_PIPELINE=1。
    """
    if OCR_VL_SERVER_URL and not OCR_VL_USE_PADDLE_PIPELINE:
        return _recognize_via_openai_compatible(path)
    return _recognize_via_paddle_pipeline(path)


def recognize_seal(path: Path) -> dict:
    """印章 → [{bbox, shape, text, color, confidence}, ...]（字段以版本返回为准）。"""
    results = _build_seal_pipeline().predict(str(path))
    seals: list[dict] = []
    for res in results:
        data = res.json if hasattr(res, "json") else {}
        for item in data.get("seal_res_list") or data.get("rec_texts") or []:
            seals.append(item if isinstance(item, dict) else {"text": item})
    return {"kind": "seal", "seals": seals}
