"""Environment-backed runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path


DEFAULT_ENV_FILE = Path(".env")
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_SLOW_REQUEST_THRESHOLD_SECONDS = 10.0
DEFAULT_LOG_FILE = Path("logs/service.log")
DEFAULT_MEMORY_ROOT = Path("knowledge/memory")


@dataclass(frozen=True, slots=True)
class ModelSettings:
    base_url: str
    model: str
    api_key: str | None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    slow_request_threshold_seconds: float = DEFAULT_SLOW_REQUEST_THRESHOLD_SECONDS


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level_name: str
    level: int
    log_file: Path


@dataclass(frozen=True, slots=True)
class MemorySettings:
    root_dir: Path


def _read_env_file_values(env_path: Path | None = None) -> dict[str, str]:
    path = env_path or DEFAULT_ENV_FILE
    candidate = path if path.is_absolute() else Path.cwd() / path
    if not candidate.is_file():
        return {}

    values: dict[str, str] = {}

    for raw_line in candidate.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value

    return values


def _clean_env(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _build_env_view(env_path: Path | None = None) -> dict[str, str]:
    env_view = _read_env_file_values(env_path)
    env_view.update(os.environ)
    return env_view


def _first_configured_env(env_view: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = _clean_env(env_view.get(name))
        if value is not None:
            return value
    return None


def _parse_float(name: str, raw_value: str) -> float:
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got: {raw_value}") from exc


def _resolve_log_level(raw_level: str | None) -> tuple[str, int]:
    normalized = (raw_level or "INFO").strip().upper()
    resolved = getattr(logging, normalized, None)
    if not isinstance(resolved, int):
        return "INFO", logging.INFO
    return normalized, resolved


def load_model_settings(env_path: Path | None = None) -> ModelSettings:
    env_view = _build_env_view(env_path)

    base_url = _first_configured_env(
        env_view,
        "MODEL_BASE_URL",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
    ) or DEFAULT_MODEL_BASE_URL
    model = _first_configured_env(env_view, "MODEL_NAME", "OPENAI_MODEL", "AGENT_MODEL")
    api_key = _first_configured_env(
        env_view,
        "MODEL_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    )
    timeout_raw = _first_configured_env(env_view, "UPSTREAM_TIMEOUT_SECONDS") or str(DEFAULT_TIMEOUT_SECONDS)
    slow_threshold_raw = _first_configured_env(env_view, "SLOW_REQUEST_THRESHOLD_SECONDS") or str(
        DEFAULT_SLOW_REQUEST_THRESHOLD_SECONDS
    )

    if model is None:
        raise ValueError("MODEL_NAME is required. Set MODEL_NAME or a supported legacy alias in your .env.")

    return ModelSettings(
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key,
        timeout_seconds=_parse_float("UPSTREAM_TIMEOUT_SECONDS", timeout_raw),
        slow_request_threshold_seconds=_parse_float(
            "SLOW_REQUEST_THRESHOLD_SECONDS", slow_threshold_raw
        ),
    )


def load_logging_settings(env_path: Path | None = None) -> LoggingSettings:
    env_view = _build_env_view(env_path)
    level_name, level = _resolve_log_level(env_view.get("APP_LOG_LEVEL") or env_view.get("LOG_LEVEL"))
    log_file = Path(env_view.get("APP_LOG_FILE") or DEFAULT_LOG_FILE)
    return LoggingSettings(level_name=level_name, level=level, log_file=log_file)


def load_memory_settings(env_path: Path | None = None) -> MemorySettings:
    env_view = _build_env_view(env_path)
    return MemorySettings(root_dir=Path(env_view.get("APP_MEMORY_ROOT") or DEFAULT_MEMORY_ROOT))
