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
import re
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookCallback,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    query,
)

from server.common.session_logging import SessionLogger, _log_bridge_failure, _log_cli_stderr
from server.platform.config import (
    configure_claude_runtime_env,
    get_claude_runtime_snapshot,
    offline_guard_error,
    resolve_model_context_window,
    resolve_model_max_output_tokens,
)
from server.platform.logging_setup import logging_context
from server.platform.paths import PROJECT_ROOT, ensure_local_layout
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

# 合法推理强度档位（extended thinking effort）的**内置默认全集**。env/per-call 传非白名单值
# 一律剔除，不传给 CLI。
_VALID_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})

# 部署可声明本端点**实际**接受哪几档（逗号分隔）。端点的合法档位由它自己的 chat template
# 决定：某些端点自校验 reasoning_effort、收到不认识的档位直接 400，而 SDK 这一侧无从探测。
# 未声明 → 用内置全集，行为与声明前逐字一致；刻意不按模型名分支——那等于把"换端点要重踩"
# 固化进源码，而端点能力是部署事实、不是代码该知道的模型知识。
_VALID_EFFORTS_ENV = "CLAUDE_VALID_REASONING_EFFORTS"

# 上下文截断预警（S7）：把注入 prompt 的字符数粗估成 token 数，与声明窗口比对。
# CJK 标书底稿密集，deepseek 分词约 1.5 char/token；env MODEL_CHARS_PER_TOKEN 可调。
# 这是安全预警而非精确 gate，取偏保守默认（宁可早报也不漏报截断风险）。
_DEFAULT_CHARS_PER_TOKEN = 1.5
_OCR_PAGE_PREFIX = "uv run python .claude/skills/ocr-page/ocr.py"
_OCR_PAGE_SHELL_META = frozenset(";&|$(){}<>\r\n" + chr(96))
_OCR_PAGE_MAX_NUMBER = sys.maxsize
_OCR_PAGE_FILE_TOKEN = (
    r"""(?:["][^"'\\;&|$()\{\}<>\x60*?\[\]!\r\n]+["]"""
    r"""|['][^"'\\;&|$()\{\}<>\x60*?\[\]!\r\n]+[']"""
    r"""|[^"'\\\s;&|$()\{\}<>\x60*?\[\]!\r\n]+)"""
)
_OCR_PAGE_SPEC = r"[0-9]+(?:-[0-9]+)?"
_OCR_PAGE_COMMAND_RE = re.compile(
    rf"{re.escape(_OCR_PAGE_PREFIX)}[ \t]+(?P<file>{_OCR_PAGE_FILE_TOKEN})"
    rf"(?:[ \t]+(?:--pages[ \t]+(?P<pages_before>{_OCR_PAGE_SPEC})"
    rf"(?:[ \t]+--seal)?|--seal(?:[ \t]+--pages[ \t]+"
    rf"(?P<pages_after>{_OCR_PAGE_SPEC}))?))?"
)


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


def valid_efforts() -> frozenset[str]:
    """本次部署接受的推理强度档位。

    读 ``CLAUDE_VALID_REASONING_EFFORTS``（逗号分隔，大小写与空白不敏感）；未设或全空白时
    回落内置全集 :data:`_VALID_EFFORTS`，保证零行为变更。

    Returns:
        小写档位集合。
    """
    raw = (os.getenv(_VALID_EFFORTS_ENV) or "").strip()
    if not raw:
        return _VALID_EFFORTS
    declared = frozenset(part.strip().lower() for part in raw.split(",") if part.strip())
    return declared or _VALID_EFFORTS


def _resolve_effort(effort: str) -> str | None:
    """校验一个已归一化的 effort；非白名单值剔除并留 WARNING。

    剔除本身是既有行为（非法档位传给 CLI 会报错），此前是**静默** pop——调用方以为自己设了
    ``xhigh``，实际发出去的是端点默认，两者的判断质量差得远却没有任何痕迹。空值不算"被剔除
    的值"（那只是没设），保持安静，否则这条信号会被日常噪音淹没。

    Args:
        effort: 已 strip + lower 的档位字符串；空串表示未设置。

    Returns:
        保留下来的档位，或 ``None`` 表示不传给 CLI。
    """
    if not effort:
        return None
    allowed = valid_efforts()
    if effort in allowed:
        return effort
    logger.warning(
        "reasoning_effort %r 不在本部署声明的白名单 %s 内，已剔除（本次调用走端点默认强度）。"
        "端点若自校验该字段，传非白名单值会直接 400；如需启用请按端点实际能力设置 %s。",
        effort,
        sorted(allowed),
        _VALID_EFFORTS_ENV,
    )
    return None


def _reserved_output_tokens(model: str | None = None) -> int | None:
    """Read the configured output budget for the selected model, if supplied."""
    return resolve_model_max_output_tokens(model=model)


def _estimate_prompt_tokens(prompt: str) -> int:
    """粗估 prompt 的输入 token 数（char 数 / MODEL_CHARS_PER_TOKEN）。"""
    chars_per_token = _positive_float_env("MODEL_CHARS_PER_TOKEN", _DEFAULT_CHARS_PER_TOKEN)
    return int(len(prompt) / chars_per_token)


def warn_if_context_may_truncate(prompt: str, *, model: str | None = None) -> dict[str, Any] | None:
    """当配置的输入/输出预算可能超窗时记 WARNING。

    S7 截断防护：评标会把数百页标书 OCR 底稿整段内联；超窗时网关会静默截断，模型据半截
    证据评分却无任何告警。本函数只使用部署配置，不推断或写死任何模型上限。

    **Opt-in**：``MODEL_CONTEXT_WINDOW`` 未配置（<=0）时直接返回 None、不记日志，零行为变更。

    Args:
        prompt: 即将注入模型的完整 prompt 文本。
        model: 覆盖用于日志的模型名；缺省取当前 runtime 的 anthropic_model。

    Returns:
        超窗时返回诊断 dict（估算/预留/窗口/模型），否则返回 None。
    """
    window = resolve_model_context_window(model=model)
    if window <= 0:
        return None
    estimated_input = _estimate_prompt_tokens(prompt)
    reserved_output = _reserved_output_tokens(model)
    if reserved_output is None:
        return None
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


def _ocr_hook_result(decision: str, reason: str) -> dict[str, Any]:
    """Build the SDK PreToolUse response used by the ocr-page trust boundary."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }


def _unquote_ocr_file(file_token: str) -> str:
    """Remove the one optional shell quote pair accepted by the command grammar."""
    if len(file_token) >= 2 and file_token[0] == file_token[-1] and file_token[0] in "\"'":
        return file_token[1:-1]
    return file_token


def _validate_ocr_pages(page_spec: str | None) -> str | None:
    """Validate page syntax, ordering, positivity, and native-integer bounds."""
    if page_spec is None:
        return None
    try:
        bounds = tuple(int(part) for part in page_spec.split("-"))
    except ValueError:
        return "pages must contain bounded positive integers"
    if len(bounds) not in {1, 2} or any(
        page <= 0 or page > _OCR_PAGE_MAX_NUMBER for page in bounds
    ):
        return "pages must contain bounded positive integers"
    if len(bounds) == 2 and bounds[0] > bounds[1]:
        return "page range start must not exceed its end"
    return None


def _validate_ocr_file(file_token: str, case_root: Path) -> str | None:
    """Resolve the file and require an existing regular file inside the real case root."""
    raw_file = _unquote_ocr_file(file_token)
    if "\x00" in raw_file:
        return "ocr-page file path contains a NUL byte"
    file_path = Path(raw_file)
    if not file_path.is_absolute():
        return "ocr-page file path must be absolute"
    try:
        root_real = Path(os.path.realpath(case_root))
        file_real = Path(os.path.realpath(file_path))
    except (OSError, ValueError):
        return "ocr-page file path cannot be resolved"
    if not root_real.is_dir():
        return "case root is not an existing directory"
    if not file_real.is_relative_to(root_real):
        return "ocr-page file resolves outside the case root"
    if not file_real.is_file():
        return "ocr-page file is not an existing regular file"
    return None


def _validate_ocr_command(command: str, case_root: Path) -> str | None:
    """Validate one complete Bash command against the ocr-page grammar and boundary."""
    shell_meta = next((char for char in command if char in _OCR_PAGE_SHELL_META), None)
    if shell_meta is not None:
        return f"shell metacharacter {shell_meta!r} is not allowed"
    match = re.fullmatch(_OCR_PAGE_COMMAND_RE, command)
    if match is None:
        return "command is not an exact ocr-page invocation"
    file_reason = _validate_ocr_file(match.group("file"), case_root)
    if file_reason is not None:
        return file_reason
    page_spec = match.group("pages_before") or match.group("pages_after")
    return _validate_ocr_pages(page_spec)


def _make_ocr_page_hook(case_root: Path) -> HookCallback:
    """Create a fail-closed Bash PreToolUse hook bound to one canonical case root."""
    normalized_root = Path(os.path.realpath(case_root))

    async def check_ocr_page(
        input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """Allow only a validated ocr-page command from the bound case."""
        if input_data.get("tool_name") != "Bash":
            return _ocr_hook_result("deny", "only Bash is supported by this hook")
        tool_input = input_data.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            return _ocr_hook_result("deny", "Bash command is missing or not a string")
        reason = _validate_ocr_command(command, normalized_root)
        return (
            _ocr_hook_result("allow", "validated ocr-page command")
            if reason is None
            else (_ocr_hook_result("deny", reason))
        )

    return check_ocr_page


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
    # 尾部默认字段（D1 M1 补丁）：契约重试次数，默认 0（本次调用一次成功，未重试）。
    # slots=True 禁止外部动态挂属性，此字段必须在此声明才能被赋值——server.tender.runner
    # 的契约重试循环在成功 attempt 后写 meta.retry_count = attempt，供 eval 回归闸
    # 记录运维基线指标（S7 配套问题②）。纯增量、有默认值，json_bridge.py 唯一构造点全
    # 关键字传参，不传本字段时安全走默认 0，audit/expense 调用链零改动。
    retry_count: int = 0
    # 尾部默认字段（D10③，同 retry_count 先例）：耗时/token 指标，默认 0——只有
    # server/audit/direct.py 的直连路径实际填写（网关一次往返即拿到 usage），
    # CLI 路径（run_agent_json/run_agent）不改动、维持默认 0（无对应 SDK 事件可读）。
    # slots=True 同样禁止外部动态挂属性，字段必须在此声明才能被赋值。
    wall_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


def build_options(*, case_root: Path | None = None, **overrides: Any) -> ClaudeAgentOptions:
    """Create SDK options, optionally exposing Bash behind the ocr-page trust boundary."""
    # 兜底进 env：这两项原本靠 setting_sources=["project"] 从 .claude/settings.json 加载；
    # 内联审核会改用 setting_sources=[] 精简系统提示，放进 env 才不会丢掉长超时与降噪。
    os.environ.setdefault("API_TIMEOUT_MS", "3000000")
    os.environ.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    runtime = get_claude_runtime_snapshot()
    # 内网硬约束：base_url 为空或指向 api.anthropic.com 时直接拒绝运行，
    # 避免 CLI 去拨公网 anthropic、在物理隔离机上拖到 ConnectionRefused/超时。
    guard = offline_guard_error()
    if guard:
        raise ClaudeRuntimeError(guard)
    # 安全硬化（2026-07-18 Hotfix）：显式限定 agent 子进程的**可用**工具集，去掉 Bash/Edit。
    # 原实现只设 allowed_tools（免提示放行清单）+ permission_mode=bypassPermissions（豁免全部
    # 权限检查），但从不设 tools → CLI 走默认全量内置工具（含 Bash）且在 bypass 下全放行。
    # 评标 agent 处理**攻击者可控**的投标 PDF，内容注入可诱导其执行 Bash = 命令注入/RCE 面
    # （security-checklist P0）。tools 是「工具是否存在」的闸（≠ allowed_tools 的「免提示放行」），
    # 限定为与 allowed_tools 一致的 6 项后 Bash 对子进程根本不存在。R4 接线 ocr-page 时再按
    # PreToolUse 白名单开受控 Bash（D11 批次 A）。可逆、行为对现有 6 工具零影响。
    _AGENT_TOOLS = ["Read", "Glob", "Grep", "Write", "Skill", "Task"]
    defaults: dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "setting_sources": ["project"],
        "tools": _AGENT_TOOLS,
        "allowed_tools": list(_AGENT_TOOLS),
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
    selected_model = str(defaults.get("model") or "").strip() or None
    child_env = dict(defaults.get("env") or {})
    configured_output = resolve_model_max_output_tokens(model=selected_model)
    if configured_output is not None and "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in child_env:
        child_env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(configured_output)
    if child_env:
        defaults["env"] = child_env
    if case_root is not None:
        tools = list(defaults.get("tools") or _AGENT_TOOLS)
        if "Bash" not in tools:
            tools.append("Bash")
        allowed_tools = list(defaults.get("allowed_tools") or tools)
        if "Bash" not in allowed_tools:
            allowed_tools.append("Bash")
        defaults["tools"] = tools
        defaults["allowed_tools"] = allowed_tools
        defaults["hooks"] = {
            "PreToolUse": [
                HookMatcher(matcher="Bash", hooks=[_make_ocr_page_hook(Path(case_root))])
            ]
        }
    # env 或 per-call override 的 effort 统一校验：仅白名单档位保留，其余剔除（并出声）。
    resolved_effort = _resolve_effort(str(defaults.get("effort") or "").strip().lower())
    if resolved_effort is None:
        defaults.pop("effort", None)
    else:
        defaults["effort"] = resolved_effort
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
    case_root: Path | None = None,
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
    warn_if_context_may_truncate(prompt, model=opts.get("model"))
    options = build_options(case_root=case_root, **opts)
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
