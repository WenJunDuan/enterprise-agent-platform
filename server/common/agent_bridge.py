"""SDK bridge: shared infrastructure, run_agent, and run_agent_full.

Provides ClaudeRuntimeError, AgentRunMeta, build_options, and the streaming
run_agent / run_agent_full entrypoints.  The JSON structured-output entrypoint
lives in server.common.json_bridge (to keep files ≤ 300 lines).

Import these symbols from server.core (the public facade) — do not import
from this module directly in application code.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    query,
)
from server.platform.config import (
    configure_claude_runtime_env,
    get_claude_runtime_snapshot,
    offline_guard_error,
    resolve_model_context_window,
)
from server.platform.logging_setup import logging_context
from server.platform.paths import PROJECT_ROOT, ensure_local_layout
from server.common.session_logging import SessionLogger, _log_bridge_failure, _log_cli_stderr
from server.stores.session_store import (
    SessionRecord,
    append_session_record,
    new_conversation_id,
    resolve_latest_session_id,
    resolve_latest_session_id_admin,
    utc_now,
)

ensure_local_layout()
configure_claude_runtime_env()

logger = logging.getLogger(__name__)

# 合法推理强度档位（extended thinking effort）。env/per-call 传非法值一律剔除，不传给 CLI。
_VALID_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})

# 上下文截断预警（S7）：把注入 prompt 的字符数粗估成 token 数，与声明窗口比对。
# CJK 标书底稿密集，deepseek 分词约 1.5 char/token；env MODEL_CHARS_PER_TOKEN 可调。
# 这是安全预警而非精确 gate，取偏保守默认（宁可早报也不漏报截断风险）。
_DEFAULT_CHARS_PER_TOKEN = 1.5
# 预留输出 token 默认（对齐 build_options 的 CLAUDE_CODE_MAX_OUTPUT_TOKENS 兜底）。
_DEFAULT_RESERVED_OUTPUT_TOKENS = 32000


class ClaudeRuntimeError(RuntimeError):
    """Raised when a Claude request never produces a terminal result."""


def _positive_float_env(name: str, default: float) -> float:
    """Read a positive float from the environment, falling back to *default* on missing/invalid."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _reserved_output_tokens() -> int:
    """预留给模型输出的 token 数——它同样吃上下文窗口，须计入截断预警。"""
    raw = (os.getenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS") or "").strip()
    if not raw:
        return _DEFAULT_RESERVED_OUTPUT_TOKENS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_RESERVED_OUTPUT_TOKENS
    return value if value >= 0 else _DEFAULT_RESERVED_OUTPUT_TOKENS


def _estimate_prompt_tokens(prompt: str) -> int:
    """粗估 prompt 的输入 token 数（char 数 / MODEL_CHARS_PER_TOKEN）。"""
    chars_per_token = _positive_float_env("MODEL_CHARS_PER_TOKEN", _DEFAULT_CHARS_PER_TOKEN)
    return int(len(prompt) / chars_per_token)


def warn_if_context_may_truncate(
    prompt: str, *, model: str | None = None
) -> dict[str, Any] | None:
    """当预估输入 token + 预留输出 token 超过声明的模型上下文窗口时，记 WARNING。

    S7 截断防护：平台默认模型可切成窗口远小于 V4Pro[1M] 的 Flash，而评标会把数百页
    标书 OCR 底稿整段内联；超窗时网关会静默截断，模型据半截证据评分却无任何告警。
    本函数在每次 agent 调用前粗估注入体量并与 ``MODEL_CONTEXT_WINDOW`` 比对，超窗即预警。

    **Opt-in**：``MODEL_CONTEXT_WINDOW`` 未配置（<=0）时直接返回 None、不记日志，零行为变更。

    Args:
        prompt: 即将注入模型的完整 prompt 文本。
        model: 覆盖用于日志的模型名；缺省取当前 runtime 的 anthropic_model。

    Returns:
        超窗时返回诊断 dict（估算/预留/窗口/模型），否则返回 None。
    """
    window = resolve_model_context_window()
    if window <= 0:
        return None
    estimated_input = _estimate_prompt_tokens(prompt)
    reserved_output = _reserved_output_tokens()
    if estimated_input + reserved_output <= window:
        return None
    model_name = model or get_claude_runtime_snapshot()["anthropic_model"]
    logger.warning(
        "上下文可能被截断：预估输入 ~%d tokens + 预留输出 %d tokens 超过 "
        "MODEL_CONTEXT_WINDOW=%d（模型=%s）。大标书证据可能在网关侧被静默截断、"
        "导致评分依据不全；请改用大窗口模型，或分片 / 精简 OCR 底稿后再评。",
        estimated_input,
        reserved_output,
        window,
        model_name,
    )
    return {
        "estimated_input_tokens": estimated_input,
        "reserved_output_tokens": reserved_output,
        "context_window": window,
        "model": model_name,
    }


@dataclass(slots=True)
class AgentRunMeta:
    request_id: str
    conversation_id: str
    claude_session_id: str | None
    resume_session_id: str | None
    fork_from_session_id: str | None
    schema_name: str | None
    log_file: str
    result_file: str | None
    result_subtype: str | None
    cost_usd: float
    finished_at: str | None


def build_options(**overrides: Any) -> ClaudeAgentOptions:
    """Create a shared SDK options object for all entrypoints."""
    # 兜底进 env：这两项原本靠 setting_sources=["project"] 从 .claude/settings.json 加载；
    # 内联审核会改用 setting_sources=[] 精简系统提示，放进 env 才不会丢掉长超时与降噪。
    os.environ.setdefault("API_TIMEOUT_MS", "3000000")
    os.environ.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    # 评标大底稿（数百页标书 → 数十项 scoring + evidence_chain）输出 JSON 很长，输出 token 不足
    # 会截断成半截 JSON 触发重试/失败。给一个稳妥兜底（.env 显式设置仍优先）。
    os.environ.setdefault("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "32000")
    runtime = get_claude_runtime_snapshot()
    # 内网硬约束：base_url 为空或指向 api.anthropic.com 时直接拒绝运行，
    # 避免 CLI 去拨公网 anthropic、在物理隔离机上拖到 ConnectionRefused/超时。
    guard = offline_guard_error()
    if guard:
        raise ClaudeRuntimeError(guard)
    defaults: dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "setting_sources": ["project"],
        "allowed_tools": ["Read", "Glob", "Grep", "Write", "Skill", "Task"],
        "permission_mode": "bypassPermissions",
        "max_turns": int(os.getenv("AUDIT_MAX_TURNS", "30")),
        "model": runtime["anthropic_model"],
        # SDK 默认单条 stdout JSON 消息上限 1MiB；评标注入 OCR 底稿(数十 KB)或 agent
        # 直读大 PDF 的 tool_result 会超限，SDK 抛 "JSON message exceeded maximum buffer size"
        # 致整单失败。默认放到 20MiB(env CLAUDE_MAX_BUFFER_BYTES 可调)，覆盖大底稿/大附件场景。
        "max_buffer_size": int(os.getenv("CLAUDE_MAX_BUFFER_BYTES", str(20 * 1024 * 1024))),
        # 捕获 bundled CLI 的 stderr，崩溃时把真因落日志（见 _log_cli_stderr）。
        "stderr": _log_cli_stderr,
    }
    # 推理强度（extended thinking）：评标是高难合规判断，不开扩展思考时 deepseek 判断随机性大。
    # 但**不全局默认 xhigh**——audit 有 180s 超时，全局 xhigh 会拖慢/超时（codex r4 P1）。故：
    # 全局只认 env CLAUDE_REASONING_EFFORT（默认不设 → 走端点默认）；评标由 tender_worker per-call
    # 传 effort=xhigh（TENDER_REASONING_EFFORT），audit 不受影响。
    env_effort = os.getenv("CLAUDE_REASONING_EFFORT", "").strip().lower()
    if env_effort:
        defaults["effort"] = env_effort
    defaults.update(overrides)
    # env 或 per-call override 的 effort 统一校验：仅合法档位保留，非法/空一律剔除不致 CLI 报错。
    effort = str(defaults.get("effort") or "").strip().lower()
    if effort in _VALID_EFFORTS:
        defaults["effort"] = effort
    else:
        defaults.pop("effort", None)
    return ClaudeAgentOptions(**defaults)


def _resolve_session_ids(
    conversation_id: str,
    resume_session_id: str | None,
    fork_from_session_id: str | None,
    continue_recent: bool,
    tenant: str | None,
) -> tuple[str | None, str]:
    """Resolve resume/fork/continue 三元逻辑，返回 (resolved_resume_session_id, current_session_id)。

    优先级（高到低）：
    1. 显式 resume_session_id — 直接用；
    2. 无 fork/continue_recent 时 — 按 tenant 查最新 session；
    3. 否则 — 不 resume（fork 或 continue 由调用方设 options）。
    current_session_id 取 resolved_resume / fork / 新 uuid。
    """
    resolved_resume = resume_session_id or (
        (
            resolve_latest_session_id(conversation_id, tenant=tenant)
            if tenant
            else resolve_latest_session_id_admin(conversation_id)
        )
        if not fork_from_session_id and not continue_recent
        else None
    )
    current = resolved_resume or fork_from_session_id or str(uuid.uuid4())
    return resolved_resume, current


def _extract_system_session_id(message: SystemMessage, current: str | None) -> str | None:
    """从 SystemMessage 里提取 claude session_id，不存在时返回 current 原值。"""
    return (
        getattr(message, "session_id", None)
        or getattr(getattr(message, "data", {}), "get", lambda *_: None)("session_id")
        or current
    )


async def run_agent(
    prompt: str,
    conversation_id: str | None = None,
    resume_session_id: str | None = None,
    fork_from_session_id: str | None = None,
    continue_recent: bool = False,
    request_id: str | None = None,
    tenant: str | None = None,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Run the SDK query stream and forward structured events."""
    conversation_id = conversation_id or new_conversation_id()
    request_id = request_id or str(uuid.uuid4())
    started_at = utc_now()
    resolved_resume_session_id, current_session_id = _resolve_session_ids(
        conversation_id, resume_session_id, fork_from_session_id, continue_recent, tenant
    )
    session_logger = SessionLogger(current_session_id, request_id, prompt, started_at, tenant)
    warn_if_context_may_truncate(prompt)
    options = build_options(**opts)
    cli_stderr: list[str] = []
    options.stderr = cli_stderr.append

    with logging_context(request_id=request_id, tenant=tenant, session_id=current_session_id):
        if fork_from_session_id:
            options.resume = fork_from_session_id
            options.fork_session = True
        elif resolved_resume_session_id:
            options.resume = resolved_resume_session_id
        elif continue_recent:
            options.continue_conversation = True

        final_claude_session_id: str | None = None
        final_subtype = ""
        final_cost = 0.0
        final_status = "success"
        saw_terminal_result = False
        saw_assistant_text = False

        try:
            async for message in query(prompt=prompt, options=options):
                event = session_logger.log_message(message)
                if isinstance(message, ResultMessage):
                    saw_terminal_result = True
                    final_claude_session_id = (
                        getattr(message, "session_id", None) or final_claude_session_id
                    )
                    final_subtype = getattr(message, "subtype", "")
                    final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
                    if getattr(message, "is_error", False):
                        final_status = "error"
                elif isinstance(message, SystemMessage):
                    final_claude_session_id = _extract_system_session_id(
                        message, final_claude_session_id
                    )

                if event:
                    if event["type"] == "text":
                        saw_assistant_text = True
                    yield event

            if not saw_terminal_result and not saw_assistant_text:
                final_status = "error"
                raise ClaudeRuntimeError(
                    "Claude request ended without any assistant result. "
                    "Recent session logs show only API retries; check gateway base URL, auth, or model id."
                )
        except Exception as exc:
            final_status = "error"
            _log_bridge_failure(
                exc,
                request_id=request_id,
                tenant=tenant,
                current_session_id=current_session_id,
                cli_stderr=cli_stderr,
                session_logger=session_logger,
            )
            raise
        finally:
            append_session_record(
                SessionRecord(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    claude_session_id=final_claude_session_id,
                    resume_session_id=resolved_resume_session_id,
                    fork_from_session_id=fork_from_session_id,
                    schema_name=str(opts.get("schema_name")) if opts.get("schema_name") else None,
                    request_mode="stream",
                    prompt_preview=prompt[:200],
                    log_file=str(session_logger.log_file),
                    status=final_status,
                    result_subtype=final_subtype or None,
                    cost_usd=final_cost,
                    started_at=started_at,
                    finished_at=utc_now(),
                    tenant=tenant,
                    result_file=None,
                )
            )


async def run_agent_full(prompt: str, **opts: Any) -> str:
    """Collect a full text response from the event stream."""
    chunks: list[str] = []
    final_result = ""
    async for event in run_agent(prompt, **opts):
        if event["type"] == "text":
            chunks.append(event["content"])
        elif event["type"] == "result":
            final_result = event["content"]
    return final_result or "\n".join(chunk for chunk in chunks if chunk)
