"""OpenAI 兼容 VLM 的单页识别传输层：一次 HTTP 往返 + 可恢复错误归一。

从 ``server.ocr.engine`` 抽出（H3：engine.py 基线 887 行已越 300 线，本 sprint 净增上界 60 行，
超出即拆本模块——design 影响范围节指定的落点）。**只做传输**：拼请求体、发请求、把可恢复的
传输/协议/解码/响应结构错误归一为 ``OcrDependencyError``；资源与取消类错误（``MemoryError`` /
``KeyboardInterrupt`` / ``SystemExit``）刻意透传，绝不伪装成"可降级"。

并发闸与页级重试等**策略**不在本模块——它们与页序连续性、降级范围一并留在 engine 的页级循环里
（见 ``engine._call_vlm_page``），避免策略散落两处。
"""

from __future__ import annotations

import http.client
import json
import ssl
import urllib.error
import urllib.request

from server.ocr import OcrDependencyError

# 单次识别请求的采样与长度参数：OCR 要的是确定性转写，不是创作。
_VLM_TEMPERATURE = 0
_VLM_MAX_TOKENS = 4096
_HTTP_ERROR_BODY_MAX_CHARS = 1000


def _build_request_body(*, model: str | None, data_url: str, prompt: str) -> dict:
    """组装 OpenAI 兼容 chat/completions 请求体（图 + 文两段 content）。"""
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "temperature": _VLM_TEMPERATURE,
        "max_tokens": _VLM_MAX_TOKENS,
    }


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    """把 HTTPError 连同（尽力读到的）响应体渲染成一行可诊断详情。"""
    detail = f"HTTP Error {exc.code}: {exc.reason}"
    try:
        response_body = exc.read().decode("utf-8", errors="replace").strip()
    except (OSError, UnicodeDecodeError, http.client.HTTPException):
        response_body = ""
    if response_body:
        detail = f"{detail}；响应：{response_body[:_HTTP_ERROR_BODY_MAX_CHARS]}"
    return detail


def call_vlm(
    *,
    url: str,
    model: str | None,
    api_key: str | None,
    data_url: str,
    prompt: str,
    timeout: float,
    ssl_context: ssl.SSLContext | None,
) -> str:
    """向 OpenAI 兼容端点发一次单页识别请求，返回页 markdown 文本。

    Args:
        url: 完整 chat/completions URL。
        model: 端点侧注册的模型名。
        api_key: Bearer token；None/空则不带 Authorization 头。
        data_url: 页图 data URL。
        prompt: 识别提示。
        timeout: 单次请求超时（秒）。
        ssl_context: TLS 上下文；None 走 urllib 默认。

    Returns:
        非空的识别文本。

    Raises:
        OcrDependencyError: 可恢复的传输/协议/解码失败，或响应结构不符（供调用方降级）。
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(_build_request_body(model=model, data_url=data_url, prompt=prompt)).encode(
            "utf-8"
        ),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise OcrDependencyError(f"OCR VLM 远端调用失败：{_http_error_detail(exc)}") from exc
    except (
        OSError,
        urllib.error.URLError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        http.client.HTTPException,
        ssl.SSLError,
    ) as exc:
        raise OcrDependencyError(f"OCR VLM 远端调用失败：{exc}") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OcrDependencyError(f"OCR VLM 返回结构异常：{payload!r}") from exc
    if not isinstance(content, str) or not content.strip():
        raise OcrDependencyError(f"OCR VLM 返回结构异常：{payload!r}")
    return content
