"""Environment-backed runtime settings for the serve layer."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, MutableMapping

from dotenv import load_dotenv

from server.platform.paths import PROJECT_ROOT, ensure_local_layout

DOTENV_PATH = PROJECT_ROOT / ".env"
DOTENV_LOADED = load_dotenv(DOTENV_PATH)
ensure_local_layout()

KNOWN_CLAUDE_MODEL_ALIASES = {"default", "sonnet", "opus", "haiku", "opusplan"}


def _looks_like_native_claude_model(model_name: str) -> bool:
    normalized = model_name.strip()
    return normalized.startswith("claude-") or normalized in KNOWN_CLAUDE_MODEL_ALIASES


def _normalize_custom_headers(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return normalized

    if normalized.startswith("{"):
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return normalized
        if isinstance(parsed, dict):
            return "\n".join(f"{key}: {item}" for key, item in parsed.items())

    return normalized


def configure_claude_runtime_env(
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, str | None]:
    """Map local gateway-style env vars to Claude SDK/CLI env vars."""
    env = environ if environ is not None else os.environ

    model_base_url = env.get("MODEL_BASE_URL")
    model_api_key = env.get("MODEL_API_KEY")
    model_auth_token = env.get("MODEL_AUTH_TOKEN")
    model_name = env.get("MODEL_NAME")
    model_custom_headers = env.get("MODEL_CUSTOM_HEADERS")

    if model_base_url and not env.get("ANTHROPIC_BASE_URL"):
        env["ANTHROPIC_BASE_URL"] = model_base_url

    if model_api_key and not env.get("ANTHROPIC_API_KEY"):
        env["ANTHROPIC_API_KEY"] = model_api_key

    if model_auth_token and not env.get("ANTHROPIC_AUTH_TOKEN"):
        env["ANTHROPIC_AUTH_TOKEN"] = model_auth_token
    elif model_api_key and not env.get("ANTHROPIC_AUTH_TOKEN"):
        env["ANTHROPIC_AUTH_TOKEN"] = model_api_key

    if model_custom_headers and not env.get("ANTHROPIC_CUSTOM_HEADERS"):
        env["ANTHROPIC_CUSTOM_HEADERS"] = _normalize_custom_headers(model_custom_headers)

    if model_name:
        normalized = model_name.strip()
        looks_like_native_model = _looks_like_native_claude_model(normalized)

        if looks_like_native_model:
            if not env.get("ANTHROPIC_MODEL"):
                env["ANTHROPIC_MODEL"] = normalized
        else:
            if not env.get("ANTHROPIC_DEFAULT_SONNET_MODEL"):
                env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = normalized
            if not env.get("ANTHROPIC_DEFAULT_OPUS_MODEL"):
                env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = normalized
            if not env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"):
                env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = normalized
            if not env.get("ANTHROPIC_MODEL"):
                env["ANTHROPIC_MODEL"] = "sonnet"

    return {
        "anthropic_base_url": env.get("ANTHROPIC_BASE_URL"),
        "anthropic_api_key": env.get("ANTHROPIC_API_KEY"),
        "anthropic_auth_token": env.get("ANTHROPIC_AUTH_TOKEN"),
        "anthropic_model": env.get("ANTHROPIC_MODEL"),
        "anthropic_default_sonnet_model": env.get("ANTHROPIC_DEFAULT_SONNET_MODEL"),
        "anthropic_default_opus_model": env.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
        "anthropic_default_haiku_model": env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"),
        "anthropic_custom_headers_configured": "1" if bool(env.get("ANTHROPIC_CUSTOM_HEADERS")) else None,
    }


configure_claude_runtime_env()


def get_claude_runtime_snapshot(environ: MutableMapping[str, str] | None = None) -> dict[str, Any]:
    """Return a redacted snapshot of the active Claude runtime configuration."""
    env = environ if environ is not None else os.environ
    original_env = dict(env)
    mapped = configure_claude_runtime_env(env)

    credential_source = None
    if original_env.get("ANTHROPIC_AUTH_TOKEN"):
        credential_source = "ANTHROPIC_AUTH_TOKEN"
    elif original_env.get("MODEL_AUTH_TOKEN"):
        credential_source = "MODEL_AUTH_TOKEN"
    elif original_env.get("ANTHROPIC_API_KEY"):
        credential_source = "ANTHROPIC_API_KEY"
    elif original_env.get("MODEL_API_KEY"):
        credential_source = "MODEL_API_KEY"

    base_url_source = None
    if original_env.get("ANTHROPIC_BASE_URL"):
        base_url_source = "ANTHROPIC_BASE_URL"
    elif original_env.get("MODEL_BASE_URL"):
        base_url_source = "MODEL_BASE_URL"

    model_source = None
    if original_env.get("ANTHROPIC_MODEL"):
        model_source = "ANTHROPIC_MODEL"
    elif original_env.get("MODEL_NAME"):
        model_source = "MODEL_NAME"

    return {
        "dotenv_path": str(DOTENV_PATH),
        "dotenv_exists": DOTENV_PATH.exists(),
        "dotenv_loaded": DOTENV_LOADED,
        "anthropic_base_url": mapped["anthropic_base_url"],
        "anthropic_api_key_configured": bool(mapped["anthropic_api_key"]),
        "anthropic_auth_token_configured": bool(mapped["anthropic_auth_token"]),
        "anthropic_model": mapped["anthropic_model"],
        "anthropic_default_sonnet_model": mapped["anthropic_default_sonnet_model"],
        "anthropic_default_opus_model": mapped["anthropic_default_opus_model"],
        "anthropic_default_haiku_model": mapped["anthropic_default_haiku_model"],
        "anthropic_custom_headers_configured": mapped["anthropic_custom_headers_configured"] == "1",
        "second_review_model": resolve_second_review_model(env),
        "base_url_source": base_url_source,
        "credential_source": credential_source,
        "model_source": model_source,
        "native_auth_configured": bool(
            original_env.get("ANTHROPIC_API_KEY") or original_env.get("ANTHROPIC_AUTH_TOKEN")
        ),
    }


def validate_claude_runtime(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Validate the minimum runtime config required for Claude SDK CLI usage."""
    runtime = get_claude_runtime_snapshot(environ)
    errors: list[str] = []

    if not runtime["anthropic_base_url"] and not runtime["native_auth_configured"]:
        errors.append("MODEL_BASE_URL or ANTHROPIC_BASE_URL is required")

    if not (
        runtime["anthropic_api_key_configured"] or runtime["anthropic_auth_token_configured"]
    ):
        errors.append(
            "MODEL_API_KEY / MODEL_AUTH_TOKEN / ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is required"
        )

    if not runtime["anthropic_model"]:
        errors.append("MODEL_NAME or ANTHROPIC_MODEL is required")

    return errors


def get_claude_runtime_report(environ: MutableMapping[str, str] | None = None) -> dict[str, Any]:
    """Build a CLI-friendly status report for Claude runtime configuration."""
    runtime = get_claude_runtime_snapshot(environ)
    errors = validate_claude_runtime(environ)
    return {
        "status": "ok" if not errors else "degraded",
        "runtime": runtime,
        "errors": errors,
    }


def resolve_second_review_model(environ: Mapping[str, str] | None = None) -> str:
    """Pick a safe review model for either native Claude or an external gateway."""
    env = environ if environ is not None else os.environ

    explicit = env.get("SECOND_REVIEW_MODEL")
    if explicit and explicit.strip():
        return explicit.strip()

    mapped_haiku = env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
    if mapped_haiku and mapped_haiku.strip():
        return mapped_haiku.strip()

    model_name = env.get("MODEL_NAME")
    if model_name and not _looks_like_native_claude_model(model_name):
        return model_name.strip()

    return "claude-haiku-4-5-20251001"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def load_tenant_keys() -> dict[str, str]:
    """Load tenant API keys from environment."""
    raw = os.getenv("TENANT_KEYS", '{"default":"sk-default"}')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TENANT_KEYS must be a JSON object") from exc
    if not isinstance(data, dict):
        raise RuntimeError("TENANT_KEYS must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


@dataclass(frozen=True, slots=True)
class AppSettings:
    api_host: str
    api_port: int
    allow_unscoped_continue_recent: bool
    session_archive_after_days: int
    runtime_log_max_bytes: int
    runtime_log_backups: int
    app_server_name: str


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    """Read stable runtime settings for the local serve layer."""
    return AppSettings(
        api_host=os.getenv("APP_SERVER_HOST", "127.0.0.1"),
        api_port=_env_int("APP_SERVER_PORT", 8000),
        allow_unscoped_continue_recent=_env_bool("ALLOW_UNSCOPED_CONTINUE_RECENT", default=False),
        session_archive_after_days=_env_int("SESSION_ARCHIVE_AFTER_DAYS", 7),
        runtime_log_max_bytes=_env_int("APP_SERVER_LOG_MAX_BYTES", 5 * 1024 * 1024),
        runtime_log_backups=_env_int("APP_SERVER_LOG_BACKUPS", 5),
        app_server_name=os.getenv("APP_SERVER_NAME", "enterprise-agent-api"),
    )


def runtime_setting_snapshot() -> dict[str, Any]:
    """Expose settings in a JSON-serializable shape for diagnostics."""
    settings = get_app_settings()
    runtime = get_claude_runtime_snapshot()
    return {
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "allow_unscoped_continue_recent": settings.allow_unscoped_continue_recent,
        "session_archive_after_days": settings.session_archive_after_days,
        "runtime_log_max_bytes": settings.runtime_log_max_bytes,
        "runtime_log_backups": settings.runtime_log_backups,
        "app_server_name": settings.app_server_name,
        "dotenv_path": runtime["dotenv_path"],
        "dotenv_exists": runtime["dotenv_exists"],
        "dotenv_loaded": runtime["dotenv_loaded"],
        "anthropic_api_key_configured": runtime["anthropic_api_key_configured"],
        "anthropic_auth_token_configured": runtime["anthropic_auth_token_configured"],
        "anthropic_base_url": runtime["anthropic_base_url"],
        "anthropic_model": runtime["anthropic_model"],
        "anthropic_default_sonnet_model": runtime["anthropic_default_sonnet_model"],
        "anthropic_default_opus_model": runtime["anthropic_default_opus_model"],
        "anthropic_default_haiku_model": runtime["anthropic_default_haiku_model"],
        "anthropic_custom_headers_configured": runtime["anthropic_custom_headers_configured"],
        "second_review_model": runtime["second_review_model"],
        "base_url_source": runtime["base_url_source"],
        "credential_source": runtime["credential_source"],
        "model_source": runtime["model_source"],
    }
