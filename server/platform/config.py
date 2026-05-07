"""Environment-backed runtime settings for the serve layer."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, MutableMapping

from dotenv import load_dotenv

from server.platform.paths import PROJECT_ROOT, ensure_local_layout

DOTENV_PATH = PROJECT_ROOT / ".env"
DOTENV_LOADED = load_dotenv(DOTENV_PATH)
ensure_local_layout()

DEFAULT_TENANT_KEYS_RAW = '{"default":"sk-default"}'
_DEFAULT_TENANT_KEY_WARNING_EMITTED = False


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
    """Transparently forward MODEL_* env vars onto their ANTHROPIC_* counterparts.

    No branching on model identity; if the user wants alias routing
    (e.g. `sonnet` → some other model), they configure
    ANTHROPIC_DEFAULT_*_MODEL themselves in .env — the SDK/CLI handles it.
    """
    env = environ if environ is not None else os.environ

    passthrough = (
        ("MODEL_BASE_URL", "ANTHROPIC_BASE_URL"),
        ("MODEL_API_KEY", "ANTHROPIC_API_KEY"),
        ("MODEL_AUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"),
        ("MODEL_NAME", "ANTHROPIC_MODEL"),
    )
    for src, dst in passthrough:
        value = env.get(src)
        if value and not env.get(dst):
            env[dst] = value.strip()

    if env.get("MODEL_API_KEY") and not env.get("ANTHROPIC_AUTH_TOKEN"):
        env["ANTHROPIC_AUTH_TOKEN"] = env["MODEL_API_KEY"].strip()

    if env.get("MODEL_CUSTOM_HEADERS") and not env.get("ANTHROPIC_CUSTOM_HEADERS"):
        env["ANTHROPIC_CUSTOM_HEADERS"] = _normalize_custom_headers(env["MODEL_CUSTOM_HEADERS"])

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


def resolve_second_review_model(environ: Mapping[str, str] | None = None) -> str | None:
    """Resolve the second-pass review model from .env only.

    Order: SECOND_REVIEW_MODEL → ANTHROPIC_DEFAULT_HAIKU_MODEL → ANTHROPIC_MODEL → MODEL_NAME.
    Returns None when nothing is configured; the caller decides how to handle it.
    """
    env = environ if environ is not None else os.environ
    for key in (
        "SECOND_REVIEW_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_MODEL",
        "MODEL_NAME",
    ):
        value = (env.get(key) or "").strip()
        if value:
            return value
    return None


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
    global _DEFAULT_TENANT_KEY_WARNING_EMITTED

    raw = os.getenv("TENANT_KEYS", DEFAULT_TENANT_KEYS_RAW)
    if tenant_keys_are_default(raw) and not _DEFAULT_TENANT_KEY_WARNING_EMITTED:
        logging.warning(
            "TENANT_KEYS env var not set, using insecure default; set TENANT_KEYS before production."
        )
        _DEFAULT_TENANT_KEY_WARNING_EMITTED = True
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TENANT_KEYS must be a JSON object") from exc
    if not isinstance(data, dict):
        raise RuntimeError("TENANT_KEYS must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def tenant_keys_are_default(raw: str | None = None) -> bool:
    candidate = raw if raw is not None else os.getenv("TENANT_KEYS", DEFAULT_TENANT_KEYS_RAW)
    return candidate.strip() == DEFAULT_TENANT_KEYS_RAW


@dataclass(frozen=True, slots=True)
class AppSettings:
    api_host: str
    api_port: int
    allow_unscoped_continue_recent: bool
    session_store_max_shard_bytes: int
    session_store_max_shards: int
    session_archive_after_days: int
    audit_task_running_timeout_seconds: int
    submission_retention_days: int
    max_upload_file_bytes: int
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
        session_store_max_shard_bytes=_env_int("SESSION_STORE_MAX_SHARD_BYTES", 50 * 1024 * 1024),
        session_store_max_shards=_env_int("SESSION_STORE_MAX_SHARDS", 24),
        session_archive_after_days=_env_int("SESSION_ARCHIVE_AFTER_DAYS", 7),
        audit_task_running_timeout_seconds=_env_int("AUDIT_TASK_RUNNING_TIMEOUT_SECONDS", 600),
        submission_retention_days=_env_int("SUBMISSION_RETENTION_DAYS", 7),
        max_upload_file_bytes=_env_int("MAX_UPLOAD_FILE_BYTES", 10 * 1024 * 1024),
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
        "tenant_keys_are_default": tenant_keys_are_default(),
        "session_store_max_shard_bytes": settings.session_store_max_shard_bytes,
        "session_store_max_shards": settings.session_store_max_shards,
        "session_archive_after_days": settings.session_archive_after_days,
        "audit_task_running_timeout_seconds": settings.audit_task_running_timeout_seconds,
        "submission_retention_days": settings.submission_retention_days,
        "max_upload_file_bytes": settings.max_upload_file_bytes,
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
