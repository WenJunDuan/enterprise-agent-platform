"""OpenAI-compatible upstream model client used by the local FastAPI service."""

from __future__ import annotations

import certifi
import httpx
import json
import ssl
from time import perf_counter

from server.config import ModelSettings, load_model_settings
from server.logging_config import get_logger


class UpstreamError(RuntimeError):
    """Raised when the upstream model server cannot be reached or parsed."""


def load_settings() -> ModelSettings:
    return load_model_settings()


def _build_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def build_chat_request(message: str, settings: ModelSettings) -> httpx.Request:
    payload = {
        "model": settings.model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    return httpx.Request(
        method="POST",
        url=f"{settings.base_url}/v1/chat/completions",
        headers=headers,
        content=json.dumps(payload).encode("utf-8"),
    )


def _build_http_client(settings: ModelSettings) -> httpx.Client:
    return httpx.Client(
        timeout=settings.timeout_seconds,
        verify=_build_ssl_context(),
    )


def extract_text(payload: dict) -> str:
    choices = payload.get("choices")
    if not choices:
        raise ValueError("missing choices in upstream response")

    message = choices[0].get("message", {})
    content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_blocks = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block
        ]
        if text_blocks:
            return "\n".join(text_blocks)

    raise ValueError("unsupported upstream response format")


def chat_once(
    message: str, settings: ModelSettings | None = None, *, request_id: str = "-"
) -> str:
    effective_settings = settings or load_settings()
    request = build_chat_request(message, effective_settings)
    logger = get_logger("model_client")
    start = perf_counter()

    logger.debug(
        "sending upstream request request_id=%s model=%s base_url=%s prompt_chars=%s",
        request_id,
        effective_settings.model,
        effective_settings.base_url,
        len(message),
    )

    try:
        with _build_http_client(effective_settings) as client:
            response = client.send(request)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        logger.error(
            "upstream request failed request_id=%s model=%s status=%s detail=%s",
            request_id,
            effective_settings.model,
            exc.response.status_code,
            detail,
        )
        raise UpstreamError(
            f"upstream request failed with status {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "upstream request failed request_id=%s model=%s error=%s",
            request_id,
            effective_settings.model,
            exc,
        )
        raise UpstreamError(str(exc)) from exc
    except Exception as exc:
        logger.error(
            "upstream request failed request_id=%s model=%s error=%s",
            request_id,
            effective_settings.model,
            exc,
        )
        raise UpstreamError(str(exc)) from exc

    try:
        result = extract_text(payload)
    except Exception as exc:
        logger.error(
            "invalid upstream response request_id=%s model=%s error=%s",
            request_id,
            effective_settings.model,
            exc,
        )
        raise UpstreamError(f"invalid upstream response: {exc}") from exc

    duration_seconds = perf_counter() - start
    log_method = (
        logger.warning
        if duration_seconds >= effective_settings.slow_request_threshold_seconds
        else logger.info
    )
    log_message = (
        "slow upstream response request_id=%s model=%s duration_ms=%.1f response_chars=%s"
        if duration_seconds >= effective_settings.slow_request_threshold_seconds
        else "upstream request finished request_id=%s model=%s duration_ms=%.1f response_chars=%s"
    )
    log_method(
        log_message,
        request_id,
        effective_settings.model,
        duration_seconds * 1000,
        len(result),
    )
    return result
