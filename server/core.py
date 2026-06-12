"""Unified SDK bridge and local persistence for Claude runs."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)
from server.platform.config import (
    configure_claude_runtime_env,
    get_claude_runtime_snapshot,
    offline_guard_error,
)
from server.platform.logging_setup import logging_context
from server.platform.paths import PROJECT_ROOT, build_session_event_log_path, ensure_local_layout
from server.platform.storage import append_jsonl_record
from server.stores.result_store import archive_result_payload
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
CONTRACTS_DIR = PROJECT_ROOT / ".claude" / "contracts"
DEFAULT_OUTPUT_SCHEMA_NAME = "common/audit-result.schema.json"
INIT_RULES_REPORT_SCHEMA_NAME = "system/init-rules-report.schema.json"
StructuredJSON = dict[str, Any] | list[Any]
logger = logging.getLogger(__name__)

# `verdict` is the single source of truth; `result` (bool) and `conclusion` (label)
# are derived from it server-side so the model never has to keep three fields in sync.
AUDIT_DECISION_DERIVATION: dict[str, tuple[bool, str]] = {
    "approved": (True, "合规"),
    "rejected": (False, "不合规"),
    "manual_review": (False, "待人工复核"),
}


def _coerce_reason_to_str(reason: Any) -> str:
    """把单条 reason 拍平成字符串。

    契约里 reasons / policy_refs 是字符串数组，但模型(尤其网关模型)可能给成对象
    （如 {code, description, severity}）→ 前端按字符串渲染对象会触发 React #31 崩溃。
    """
    if isinstance(reason, str):
        return reason
    if isinstance(reason, dict):
        desc = str(reason.get("description") or reason.get("message") or reason.get("reason") or "").strip()
        severity = str(reason.get("severity") or "").strip()
        text = f"[{severity}] {desc}" if severity and desc else desc
        return text or json.dumps(reason, ensure_ascii=False)
    return str(reason)


def _scale_risk_dimension_score(raw: Any) -> int:
    """把维度分归一到契约的 0-10 区间。

    契约要求 score ∈ [0, 10]，但模型常按 0-100 量纲给（与 risk_score 同尺度）。
    >10 视为百分制并除以 10；最终 clamp 到 0-10。
    """
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0
    if score > 10:  # 模型用了 0-100 量纲，映射回契约的 0-10
        score /= 10.0
    return max(0, min(10, round(score)))


def _coerce_risk_dimensions(value: Any) -> list[dict[str, Any]] | None:
    """把 risk_dimensions 归一成契约形态：[{name, score(0-10)}]。

    契约是对象数组，但模型可能给成对象映射 {name: score}（如 {anomaly: 85}）。
    前端按数组渲染（.map / .length），拿到对象会显示异常或漏渲染，这里统一拍平。
    """
    if isinstance(value, dict):
        pairs: list[tuple[Any, Any]] = list(value.items())
    elif isinstance(value, list):
        pairs = [
            (item.get("name"), item.get("score")) for item in value if isinstance(item, dict)
        ]
    else:
        return None
    normalized = [
        {"name": str(name), "score": _scale_risk_dimension_score(score)}
        for name, score in pairs
        if name is not None and str(name).strip()
    ]
    return normalized or None


def enrich_audit_decision(structured_output: StructuredJSON) -> StructuredJSON:
    """Inject `result`/`conclusion` derived from `verdict`; normalize string-list fields."""
    if isinstance(structured_output, dict):
        derived = AUDIT_DECISION_DERIVATION.get(str(structured_output.get("verdict")))
        if derived is not None:
            structured_output["result"], structured_output["conclusion"] = derived
        # reasons / policy_refs 契约为字符串数组；模型给成对象数组时拍平，避免前端渲染崩溃。
        for field in ("reasons", "policy_refs"):
            value = structured_output.get(field)
            if isinstance(value, list):
                structured_output[field] = [_coerce_reason_to_str(item) for item in value]
        # risk_dimensions 契约为对象数组；模型给成 {name: score} 映射或 0-100 量纲时归一。
        if "risk_dimensions" in structured_output:
            normalized_dims = _coerce_risk_dimensions(structured_output["risk_dimensions"])
            if normalized_dims is not None:
                structured_output["risk_dimensions"] = normalized_dims
    return structured_output


class JSONContractError(ValueError):
    """Raised when a Claude response does not satisfy the JSON contract."""


class ClaudeRuntimeError(RuntimeError):
    """Raised when a Claude request never produces a terminal result."""


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


def resolve_output_schema_path(schema_name: str) -> Path:
    """Resolve a schema path under `.claude/contracts` without allowing path escape."""
    schema_path = (CONTRACTS_DIR / schema_name).resolve()
    contracts_root = CONTRACTS_DIR.resolve()
    if contracts_root not in schema_path.parents:
        raise JSONContractError(f"Schema path escapes contracts root: {schema_name}")
    if not schema_path.is_file():
        raise JSONContractError(f"Structured output schema not found: {schema_name}")
    return schema_path


def load_output_schema(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Load a JSON schema from `.claude/contracts`."""
    schema_path = resolve_output_schema_path(schema_name)
    try:
        loaded = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - exact error text is incidental
        raise JSONContractError(f"Structured output schema is invalid JSON: {schema_name}") from exc

    if not isinstance(loaded, dict):
        raise JSONContractError(f"Structured output schema must be a JSON object: {schema_name}")
    return loaded


def build_output_format(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Build the SDK `output_format` payload for structured outputs."""
    return {"type": "json_schema", "schema": load_output_schema(schema_name)}


def validate_structured_output_semantics(
    schema_name: str,
    structured_output: StructuredJSON,
) -> None:
    """Apply semantic validation rules that JSON Schema alone cannot express."""
    if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
        if not isinstance(structured_output, dict):
            raise JSONContractError("audit result structured output must be a JSON object.")

        verdict = structured_output.get("verdict")
        if verdict not in AUDIT_DECISION_DERIVATION:
            raise JSONContractError("audit result returned an unknown verdict.")

        if not str(structured_output.get("explanation") or "").strip():
            raise JSONContractError("audit result field `explanation` must be non-empty.")

        if verdict == "manual_review":
            reason = structured_output.get("manual_review_reason")
            valid_reasons = {
                "missing_approval",
                "rule_gap",
                "data_conflict",
                "insufficient_evidence",
                "budget_exceeded",
                "invoice_invalid",
                "pre_approval_mismatch",
            }
            if reason not in valid_reasons:
                raise JSONContractError(
                    "audit result with verdict=manual_review must include a valid manual_review_reason."
                )

        # risk_dimensions 是可选的风险元数据。网关模型（qwen 等）给的格式常不规范——
        # 不规范就清洗/丢弃，绝不因为一个可选字段让整单审核失败（核心是 verdict/explanation）。
        valid_dim_names = {"invoice", "amount", "approval", "budget", "anomaly"}
        dimensions = structured_output.get("risk_dimensions")
        if isinstance(dimensions, list):
            structured_output["risk_dimensions"] = [
                dim
                for dim in dimensions
                if isinstance(dim, dict)
                and dim.get("name") in valid_dim_names
                and isinstance(dim.get("score"), int)
                and not isinstance(dim.get("score"), bool)
                and 0 <= dim["score"] <= 10
            ]
        elif dimensions is not None:
            structured_output.pop("risk_dimensions", None)

        return

    if schema_name != INIT_RULES_REPORT_SCHEMA_NAME:
        return

    if not isinstance(structured_output, dict):
        raise JSONContractError("init-rules structured output must be a JSON object.")

    source_path = str(structured_output.get("source_path") or "").strip()
    if not source_path:
        raise JSONContractError("init-rules result must include a non-empty source_path.")

    status = structured_output.get("status")
    if status != "initialized":
        return

    written_files = structured_output.get("written_files")
    categories = structured_output.get("categories")
    extracted_rule_count = structured_output.get("extracted_rule_count")

    if not isinstance(written_files, list) or not written_files:
        raise JSONContractError(
            "init-rules cannot return status=initialized with empty written_files."
        )
    if not isinstance(categories, list) or not categories:
        raise JSONContractError("init-rules cannot return status=initialized with empty categories.")
    if not isinstance(extracted_rule_count, int) or extracted_rule_count <= 0:
        raise JSONContractError(
            "init-rules cannot return status=initialized with extracted_rule_count <= 0."
        )


def _log_cli_stderr(line: str) -> None:
    """SDK 把 bundled CLI 的 stderr 逐行回调到这里。

    CLI 崩溃 (exit 1) 时真正的错误只写在它自己的 stderr，默认会被 SDK 吞成
    "Check stderr output for details"。在这里落到日志，崩溃后即可定位真因
    （如网关响应畸形、流式解析异常），不必再手动复现。
    """
    text = line.rstrip()
    if text:
        logger.warning("claude_cli_stderr: %s", text)


def build_options(**overrides: Any) -> ClaudeAgentOptions:
    """Create a shared SDK options object for all entrypoints."""
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
    defaults: dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "setting_sources": ["project"],
        "allowed_tools": ["Read", "Glob", "Grep", "Write", "Skill", "Task"],
        "permission_mode": "bypassPermissions",
        "max_turns": int(os.getenv("AUDIT_MAX_TURNS", "30")),
        "max_budget_usd": float(os.getenv("MAX_BUDGET_USD", "1.0")),
        "model": runtime["anthropic_model"],
        # 捕获 bundled CLI 的 stderr，崩溃时把真因落日志（见 _log_cli_stderr）。
        "stderr": _log_cli_stderr,
    }
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


class SessionLogger:
    """Persist the raw SDK event stream as JSONL."""

    def __init__(
        self,
        session_id: str,
        request_id: str,
        prompt: str,
        started_at: str,
        tenant: str | None,
    ) -> None:
        self.session_id = session_id
        self.request_id = request_id
        self.tenant = tenant
        self.start_time = time.time()
        self.started_at = started_at
        self.log_file = build_session_event_log_path(
            session_id=session_id,
            request_id=request_id,
            timestamp=started_at,
        )
        self._write(
            {
                "event": "session_start",
                "session_id": session_id,
                "request_id": request_id,
                "tenant": tenant,
                "prompt": prompt,
                "timestamp": started_at,
            }
        )

    def log_message(self, message: Any) -> dict[str, Any] | None:
        """Capture a stream message and return an event suitable for callers."""
        event: dict[str, Any] | None = None

        if isinstance(message, SystemMessage):
            session_id = getattr(message, "session_id", None) or getattr(
                getattr(message, "data", {}),
                "get",
                lambda *_: None,
            )("session_id")
            if session_id:
                self.session_id = str(session_id)
            self._write(
                {
                    "event": "system",
                    "subtype": getattr(message, "subtype", ""),
                    "session_id": self.session_id,
                    "timestamp": self._now(),
                }
            )
            if session_id:
                event = {"type": "session", "session_id": session_id}

        elif isinstance(message, AssistantMessage):
            message_session_id = getattr(message, "session_id", None)
            if message_session_id:
                self.session_id = str(message_session_id)
            for block in getattr(message, "content", []):
                if isinstance(block, TextBlock):
                    event = {"type": "text", "content": block.text}
                    self._write(
                        {
                            "event": "assistant_text",
                            "content": block.text,
                            "session_id": self.session_id,
                            "timestamp": self._now(),
                        }
                    )
                elif isinstance(block, ToolUseBlock):
                    self._write(
                        {
                            "event": "tool_call",
                            "tool": block.name,
                            "input": str(block.input)[:1000],
                            "session_id": self.session_id,
                            "timestamp": self._now(),
                        }
                    )
                elif isinstance(block, ToolResultBlock):
                    self._write(
                        {
                            "event": "tool_result",
                            "content": str(getattr(block, "content", ""))[:1000],
                            "session_id": self.session_id,
                            "timestamp": self._now(),
                        }
                    )

        elif isinstance(message, ResultMessage):
            if getattr(message, "session_id", None):
                self.session_id = str(message.session_id)
            elapsed = time.time() - self.start_time
            event = {
                "type": "result",
                "content": message.result or "",
                "cost": float(getattr(message, "total_cost_usd", 0.0) or 0.0),
                "structured_output": getattr(message, "structured_output", None),
                "subtype": getattr(message, "subtype", ""),
            }
            self._write(
                {
                    "event": "session_end",
                    "subtype": getattr(message, "subtype", ""),
                    "is_error": bool(getattr(message, "is_error", False)),
                    "result": (message.result or "")[:2000],
                    "duration_sec": round(elapsed, 2),
                    "cost_usd": event["cost"],
                    "structured_output": getattr(message, "structured_output", None),
                    "session_id": self.session_id,
                    "timestamp": self._now(),
                }
            )

        return event

    def _write(self, record: dict[str, Any]) -> None:
        enriched = {
            "request_id": self.request_id,
            "tenant": self.tenant,
            "session_id": self.session_id,
            **record,
        }
        append_jsonl_record(self.log_file, enriched)
        if record.get("event") in {"session_start", "session_end"}:
            logger.info(
                "session_event",
                extra={
                    "event_name": record.get("event"),
                    "request_id": self.request_id,
                    "tenant": self.tenant,
                    "session_id": self.session_id,
                    "result_subtype": record.get("subtype"),
                },
            )

    def log_error(self, error: Exception) -> None:
        """Capture internal bridge errors that happen outside Claude result blocks."""
        self._write(
            {
                "event": "bridge_error",
                "error_type": error.__class__.__name__,
                "message": str(error),
                "timestamp": self._now(),
            }
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


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


def _log_bridge_failure(
    exc: Exception,
    *,
    request_id: str,
    tenant: str | None,
    current_session_id: str,
    cli_stderr: list[str],
    session_logger: "SessionLogger",
) -> None:
    """记录 SDK 调用失败：结构化日志 + CLI stderr 尾部 + session 错误事件。

    CLI exit 非零时真正的错误只在它自己的 stderr，这里把尾部打出来帮助定位崩溃真因
    （如网关响应畸形、流式解析异常），不必再手动复现。
    """
    logger.exception(
        "claude_bridge_failed",
        extra={"request_id": request_id, "tenant": tenant, "session_id": current_session_id},
    )
    captured_stderr = "".join(cli_stderr).strip()
    if captured_stderr:
        # CLI exit 非零时把它的 stderr 全文打出来，否则只有一句无用的
        # "Check stderr output for details"。这是定位 CLI 崩溃的关键。
        logger.error("claude_cli_stderr | %s", captured_stderr[-6000:])
    session_logger.log_error(exc)


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
                    final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id
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


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型文本里抽取**最终**的 JSON 对象。

    针对 reasoning 模型：思考/草稿（常含一段草稿 JSON）在 </think> 之前，真正答案在
    之后；所以先截到最后一个 </think> 之后，去掉 ```json 围栏，扫出所有平衡的 {...}，
    返回**最后一个**能解析成 dict 的（最终答案通常在最后）。这样不会误抓推理里的草稿。
    用于"文本模式"：网关模型（如 qwen）直接输出 JSON 文本，由服务端解析。
    """
    if not text:
        return None
    # reasoning 模型把草稿放 </think> 之前，真正答案在最后一个 </think> 之后
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    cleaned = text.replace("```json", "").replace("```", "")
    # 扫出所有平衡的顶层 {...}
    objects: list[str] = []
    i = 0
    n = len(cleaned)
    while i < n:
        if cleaned[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        closed_at = -1
        for j in range(i, n):
            ch = cleaned[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    objects.append(cleaned[i : j + 1])
                    closed_at = j
                    break
        i = closed_at + 1 if closed_at != -1 else n
    # 最终答案在最后：从后往前返回第一个能解析成 dict 的
    for candidate in reversed(objects):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


async def run_agent_json(
    prompt: str,
    conversation_id: str | None = None,
    resume_session_id: str | None = None,
    fork_from_session_id: str | None = None,
    continue_recent: bool = False,
    schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME,
    structured: bool = True,
    request_id: str | None = None,
    tenant: str | None = None,
    **opts: Any,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """Run Claude and return the parsed JSON object.

    structured=True 用 SDK 的 output_format 强制结构化输出（需模型支持 function
    calling）；structured=False 走文本模式：模型直接输出 JSON 文本，服务端自己抽取解析。
    """
    conversation_id = conversation_id or new_conversation_id()
    request_id = request_id or str(uuid.uuid4())
    started_at = utc_now()
    resolved_resume_session_id, current_session_id = _resolve_session_ids(
        conversation_id, resume_session_id, fork_from_session_id, continue_recent, tenant
    )
    session_logger = SessionLogger(current_session_id, request_id, prompt, started_at, tenant)
    output_opts = {"output_format": build_output_format(schema_name)} if structured else {}
    options = build_options(**output_opts, **opts)
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
        result_file: str | None = None
        finished_at: str | None = None
        final_structured_output: StructuredJSON | None = None
        text_accum: list[str] = []

        try:
            async for message in query(prompt=prompt, options=options):
                session_logger.log_message(message)

                if isinstance(message, SystemMessage):
                    final_claude_session_id = _extract_system_session_id(
                        message, final_claude_session_id
                    )
                    continue

                if isinstance(message, AssistantMessage):
                    for block in getattr(message, "content", []):
                        if isinstance(block, TextBlock):
                            text_accum.append(block.text)
                    continue

                if not isinstance(message, ResultMessage):
                    continue

                final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id
                final_subtype = getattr(message, "subtype", "")
                final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)

                if structured:
                    structured_output = getattr(message, "structured_output", None)
                    if structured_output is not None and final_structured_output is None:
                        if not isinstance(structured_output, (dict, list)):
                            final_status = "error"
                            raise JSONContractError("Claude returned a non-object structured output.")
                        validate_structured_output_semantics(schema_name, structured_output)
                        if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
                            structured_output = enrich_audit_decision(structured_output)
                        final_structured_output = structured_output
                        finished_at = utc_now()
                        continue
                    if final_subtype == "error_max_structured_output_retries":
                        final_status = "error"
                        raise JSONContractError(
                            f"Claude failed to satisfy structured output schema after retries: {schema_name}"
                        )
                elif final_structured_output is None:
                    # 文本模式：模型把 JSON 当文本输出，这里抽取 + 语义校验。
                    raw_text = (getattr(message, "result", "") or "") or "".join(text_accum)
                    parsed = _extract_json_object(raw_text)
                    if parsed is not None:
                        validate_structured_output_semantics(schema_name, parsed)
                        if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
                            parsed = enrich_audit_decision(parsed)
                        final_structured_output = parsed
                        finished_at = utc_now()
                        continue

                if getattr(message, "is_error", False):
                    final_status = "error"
                    raise JSONContractError(message.result or "Claude returned an error result.")

            if final_structured_output is None:
                final_status = "error"
                if structured:
                    raise JSONContractError("Claude returned no structured output.")
                raise JSONContractError(
                    "文本模式下未能从模型输出中解析出 JSON 对象（模型可能没按要求只输出 JSON）。"
                )

            result_record = archive_result_payload(
                request_id=request_id,
                tenant=tenant,
                conversation_id=conversation_id,
                claude_session_id=final_claude_session_id,
                resume_session_id=resolved_resume_session_id,
                fork_from_session_id=fork_from_session_id,
                schema_name=schema_name,
                request_mode="structured" if structured else "text",
                result_subtype=final_subtype or None,
                cost_usd=final_cost,
                prompt_preview=prompt[:200],
                response=final_structured_output,
                created_at=finished_at or utc_now(),
            )
            result_file = result_record.result_file
            return final_structured_output, AgentRunMeta(
                request_id=request_id,
                conversation_id=conversation_id,
                claude_session_id=final_claude_session_id,
                resume_session_id=resolved_resume_session_id,
                fork_from_session_id=fork_from_session_id,
                schema_name=schema_name,
                log_file=str(session_logger.log_file),
                result_file=result_file,
                result_subtype=final_subtype or None,
                cost_usd=final_cost,
                finished_at=finished_at,
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
                    schema_name=schema_name,
                    request_mode="structured" if structured else "text",
                    prompt_preview=prompt[:200],
                    log_file=str(session_logger.log_file),
                    status=final_status,
                    result_subtype=final_subtype or None,
                    cost_usd=final_cost,
                    started_at=started_at,
                    finished_at=finished_at or utc_now(),
                    tenant=tenant,
                    result_file=result_file,
                )
            )
