"""Environment-backed runtime settings for the serve layer."""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
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


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# 内网部署默认强制关掉的 CLI 外连开关（均为 self-bundled claude CLI 二进制里真实存在的变量）。
# 覆盖：遥测 / 错误上报 / 统计(statsig) / 自动更新 / bug 上报 / 插件市场自动安装 / 成本告警。
_OFFLINE_DISABLE_ENV = (
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL",
    "DISABLE_TELEMETRY",
    "DISABLE_ERROR_REPORTING",
    "DISABLE_AUTOUPDATER",
    "DISABLE_BUG_COMMAND",
    "DISABLE_COST_WARNINGS",
)


def is_anthropic_api_endpoint(base_url: str | None) -> bool:
    """内网禁止连接的目标：空（CLI 会退回默认 api.anthropic.com）或 *.anthropic.com 域名。"""
    if not base_url or not base_url.strip():
        return True
    host = (urllib.parse.urlparse(base_url.strip()).hostname or "").lower()
    return host == "anthropic.com" or host.endswith(".anthropic.com")


def offline_guard_error(environ: Mapping[str, str] | None = None) -> str | None:
    """内网/物理隔离硬约束：拒绝连接 api.anthropic.com。

    base_url 为空或指向 anthropic.com 时返回错误消息（否则返回 None）。
    设 ALLOW_ANTHROPIC_API=1 整体解除（仅在确有公网访问时）。
    """
    env = environ if environ is not None else os.environ
    if _truthy(env.get("ALLOW_ANTHROPIC_API")):
        return None
    base_url = env.get("ANTHROPIC_BASE_URL") or env.get("MODEL_BASE_URL")
    if is_anthropic_api_endpoint(base_url):
        return (
            "内网部署禁止连接 api.anthropic.com：MODEL_BASE_URL / ANTHROPIC_BASE_URL "
            "为空或指向 anthropic.com，请指向内网网关（如 http://litellm:4000）。"
            "确需公网访问请设 ALLOW_ANTHROPIC_API=1。"
        )
    return None


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

    # 内网/物理隔离：默认强制关掉 CLI 对 anthropic.com 的所有非必需外连。
    # 设 ALLOW_ANTHROPIC_API=1 可整体放开（仅在确有公网访问时）。
    if not _truthy(env.get("ALLOW_ANTHROPIC_API")):
        for key in _OFFLINE_DISABLE_ENV:
            env.setdefault(key, "1")

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

    guard = offline_guard_error(environ)
    if guard:
        errors.append(guard)

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
    """Read an integer from the environment, returning *default* on missing or invalid values."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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
        session_archive_after_days=_env_int("SESSION_ARCHIVE_AFTER_DAYS", 7),
        audit_task_running_timeout_seconds=_env_int("AUDIT_TASK_RUNNING_TIMEOUT_SECONDS", 600),
        submission_retention_days=_env_int("SUBMISSION_RETENTION_DAYS", 7),
        max_upload_file_bytes=_env_int("MAX_UPLOAD_FILE_BYTES", 10 * 1024 * 1024),
        runtime_log_max_bytes=_env_int("APP_SERVER_LOG_MAX_BYTES", 5 * 1024 * 1024),
        runtime_log_backups=_env_int("APP_SERVER_LOG_BACKUPS", 5),
        app_server_name=os.getenv("APP_SERVER_NAME", "enterprise-agent-api"),
    )


@dataclass(frozen=True, slots=True)
class CreditApiSettings:
    """外部企业信用查询 API 配置（G3 工具契约化）。

    未配置（``url``/``key`` 任一为空）→ 工具跳过、评分项保持 ``manual_review``（人工）。
    配置后（填 ``CREDIT_API_URL`` + ``CREDIT_API_KEY``）→ 自动调用，无需改代码。
    不缓存：每次读 env，便于在部署机上填好 url/key 后无需重启即生效。
    """

    url: str
    key: str
    timeout_seconds: float

    @property
    def configured(self) -> bool:
        return bool(self.url.strip()) and bool(self.key.strip())


def get_credit_api_settings() -> CreditApiSettings:
    """Read external credit-API settings from env (uncached)."""
    return CreditApiSettings(
        url=os.getenv("CREDIT_API_URL", "").strip(),
        key=os.getenv("CREDIT_API_KEY", "").strip(),
        timeout_seconds=float(os.getenv("CREDIT_API_TIMEOUT_SECONDS", "10")),
    )


@dataclass(frozen=True, slots=True)
class AuditSettings:
    """内联审核行为开关。

    均可经 env 在 compose 中调整、无需重建镜像；每次审核读一次（不缓存），
    便于在部署机上改一项重启容器即生效。各字段的取舍背景：
    - lean_context: setting_sources=[] 砍掉 .claude/CLAUDE.md 等无关系统提示，
      减小慢/网关模型的 prefill 负担；内联审核自包含（规则+案件已注入），
      不依赖项目设置。设 AUDIT_LEAN_CONTEXT=0 回退到加载项目设置。
    - structured_output: True 用 SDK output_format 强制结构化输出（需模型支持
      function calling）；默认 False 走文本模式——让模型直接输出 JSON 文本、由
      服务端解析，兼容不支持原生 function calling 的网关模型（如 qwen，会把
      tool_use/JSON 当文本吐导致 CLI 崩溃）。
    - enable_read: 多模态读附件原件（发票 / 行程图片）。默认关闭以保持低延迟
      （每次 Read 都是一次网关往返）；结构化模式本就需要 Read，故二者任一开启
      即提供 Read 工具。
    - contract_max_retry: 慢/网关模型在文本模式下偶发两类随机失败——半截 JSON /
      漏填必填字段（契约校验失败），或 bundled CLI 流式解析崩溃 (exit 1)。两类都
      对单次调用而非输入本身敏感，重跑一次（新 session）即可显著降低 flaky 率。
      设 0 关闭重试。
    """

    lean_context: bool
    structured_output: bool
    enable_read: bool
    contract_max_retry: int
    inline_max_turns: int

    @property
    def allowed_tools(self) -> list[str]:
        """结构化模式需要 Read；文本模式仅在显式开启核验时给 Read。"""
        return ["Read"] if (self.structured_output or self.enable_read) else []


def get_audit_settings() -> AuditSettings:
    """Read inline-audit behavior knobs fresh from the environment."""
    return AuditSettings(
        lean_context=_env_bool("AUDIT_LEAN_CONTEXT", default=True),
        structured_output=_env_bool("AUDIT_STRUCTURED_OUTPUT", default=False),
        enable_read=_env_bool("AUDIT_ENABLE_READ", default=False),
        contract_max_retry=max(0, _env_int("AUDIT_CONTRACT_MAX_RETRY", 1)),
        inline_max_turns=_env_int("AUDIT_INLINE_MAX_TURNS", 8),
    )


@dataclass(frozen=True, slots=True)
class OcrSettings:
    """文档识别 → 表单回填的运行开关（env 可调，每次读一次）。

    服务端走"内联单跳"：确定性流水线（分类 + 直读 + 调 OCR）在 server.ocr 进程内跑完，
    只把识别底稿内联给模型做一次"字段映射"判断——对齐 audit_runner，砍掉逐文件 Bash 往返。
    - allowed_tools: 映射阶段全部输入已内联，**不需要任何工具**（无 Bash / Read），网关往返压到 1。
    - max_turns: 单次映射应答即可，给极小轮数。
    - contract_max_retry: 慢 / 网关模型偶发半截 JSON 或漏字段，重跑一次降 flaky。
    """

    max_turns: int
    contract_max_retry: int

    @property
    def allowed_tools(self) -> list[str]:
        """映射输入全内联，无需任何工具。"""
        return []


def get_ocr_settings() -> OcrSettings:
    """Read doc-extract / form-fill behavior knobs fresh from the environment."""
    return OcrSettings(
        max_turns=_env_int("OCR_MAX_TURNS", 4),
        contract_max_retry=max(0, _env_int("OCR_CONTRACT_MAX_RETRY", 1)),
    )


def runtime_setting_snapshot() -> dict[str, Any]:
    """Expose settings in a JSON-serializable shape for diagnostics."""
    settings = get_app_settings()
    audit = get_audit_settings()
    runtime = get_claude_runtime_snapshot()
    return {
        "audit_lean_context": audit.lean_context,
        "audit_structured_output": audit.structured_output,
        "audit_enable_read": audit.enable_read,
        "audit_contract_max_retry": audit.contract_max_retry,
        "audit_inline_max_turns": audit.inline_max_turns,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "allow_unscoped_continue_recent": settings.allow_unscoped_continue_recent,
        "tenant_keys_are_default": tenant_keys_are_default(),
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
