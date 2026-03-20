"""Shared execution helpers used by API and future CLI workflows."""

from __future__ import annotations

from dataclasses import dataclass

from server.config import ModelSettings, load_model_settings
from server.logging_config import get_logger
from server.memory_writer import MemoryRecord, append_memory_record
from server.model_client import chat_once


logger = get_logger("core")


class MemoryWriteError(RuntimeError):
    """Raised when business runtime memory cannot be persisted."""


@dataclass(frozen=True, slots=True)
class CoreResponse:
    status: str
    request_id: str
    source: str
    model: str
    output_text: str
    memory_path: str | None
    metadata: dict[str, object]


def run_chat(
    message: str,
    *,
    source: str,
    request_id: str,
    settings: ModelSettings | None = None,
    memory_record: MemoryRecord | None = None,
) -> CoreResponse:
    effective_settings = settings or load_model_settings()

    logger.debug(
        "core chat started request_id=%s source=%s model=%s input_chars=%s",
        request_id,
        source,
        effective_settings.model,
        len(message),
    )
    output_text = chat_once(message, effective_settings, request_id=request_id)

    memory_path: str | None = None
    if memory_record is not None:
        try:
            memory_path = str(append_memory_record(memory_record))
            logger.info(
                "business memory appended request_id=%s source=%s path=%s",
                request_id,
                source,
                memory_path,
            )
        except Exception as exc:
            logger.error(
                "business memory append failed request_id=%s source=%s error=%s",
                request_id,
                source,
                exc,
            )
            raise MemoryWriteError(f"business memory append failed: {exc}") from exc

    logger.info(
        "core chat completed request_id=%s source=%s model=%s output_chars=%s",
        request_id,
        source,
        effective_settings.model,
        len(output_text),
    )
    return CoreResponse(
        status="ok",
        request_id=request_id,
        source=source,
        model=effective_settings.model,
        output_text=output_text,
        memory_path=memory_path,
        metadata={
            "input_chars": len(message),
            "output_chars": len(output_text),
        },
    )
