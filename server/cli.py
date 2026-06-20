"""CLI entrypoints for the platform."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import typer
import uvicorn

from server.common.command_adapter import run_command_full, run_command_json
from server.core import (
    AgentRunMeta,
    ClaudeRuntimeError,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    DEFAULT_OUTPUT_SCHEMA_NAME,
    run_agent_full,
)
from server.ops.maintenance import run_maintenance
from server.platform import config as config_module
from server.platform.asset_validation import validate_knowledge_assets
from server.platform.config import get_claude_runtime_report
from server.platform.source_proxy import prepare_text_proxy
from server.stores.memory_store import get_memory_record_by_id, list_memory_records
from server.stores.request_store import (
    get_request_audit_by_request_id_admin,
    list_request_audits_admin,
)
from server.stores.result_store import (
    get_result_payload_by_request_id_admin,
    get_result_record_by_request_id_admin,
    list_result_records_admin,
)
from server.stores.review_delta_store import (
    get_review_delta_payload_by_request_id_admin,
    get_review_delta_record_by_request_id_admin,
    list_review_delta_records_admin,
)
from server.stores.session_store import (
    get_sdk_session_transcript,
    list_conversation_summaries_admin,
    list_logged_sessions_admin,
    new_conversation_id,
)

app = typer.Typer(help="Enterprise agent platform CLI.")
logger = logging.getLogger(__name__)
INIT_RULES_PROXY_DIR = Path("logs/service/init-rules")


def _ensure_cli_runtime() -> None:
    report = get_claude_runtime_report()
    if report["status"] == "ok":
        return
    _echo_json(report)
    raise typer.Exit(code=1)


def _run_cli(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except ClaudeRuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except JSONContractError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc


def _echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _emit_cli_json_result(meta: AgentRunMeta, payload: dict | list) -> None:
    _echo_json(
        {
            "request_id": meta.request_id,
            "conversation_id": meta.conversation_id,
            "claude_session_id": meta.claude_session_id,
            "schema_name": meta.schema_name,
            "result_file": meta.result_file,
            "cost": meta.cost_usd,
            "response": payload,
        }
    )


def _invoke_text_command(coro: Any) -> None:
    typer.echo(_run_cli(coro))


def _invoke_json_command(coro: Any) -> None:
    payload, meta = _run_cli(coro)
    _emit_cli_json_result(meta, payload)


@app.command()
def runtime(
    strict: bool = typer.Option(False, help="Exit non-zero when runtime config is degraded."),
) -> None:
    """Print the current redacted Claude runtime configuration."""
    report = get_claude_runtime_report()
    _echo_json(report)
    if strict and report["status"] != "ok":
        raise typer.Exit(code=1)


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="Raw prompt text."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Run one prompt and print the final output."""
    _ensure_cli_runtime()
    _invoke_text_command(
        run_agent_full(
            prompt,
            conversation_id=conversation_id or new_conversation_id(),
            resume_session_id=resume_session_id or None,
            fork_from_session_id=fork_from_session_id or None,
        )
    )


@app.command()
def audit(
    path: str = typer.Argument(..., help="Path to a source file or directory."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Trigger the built-in audit workflow for a file or directory path."""
    _ensure_cli_runtime()
    _invoke_text_command(
        run_command_full(
            "audit",
            path,
            conversation_id=conversation_id or new_conversation_id(),
            resume_session_id=resume_session_id or None,
            fork_from_session_id=fork_from_session_id or None,
        )
    )


@app.command("audit-json")
def audit_json(
    path: str = typer.Argument(..., help="Path to a source file or directory."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Run audit for a file or directory path with structured output and print metadata."""
    _ensure_cli_runtime()

    async def _run() -> tuple[dict | list, AgentRunMeta]:
        return await run_command_json(
            "audit",
            path,
            conversation_id=conversation_id or new_conversation_id(),
            resume_session_id=resume_session_id or None,
            fork_from_session_id=fork_from_session_id or None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        )

    _invoke_json_command(_run())


@app.command("tender-evaluate")
def tender_evaluate(
    path: str = typer.Argument(..., help="Path to a tender case directory or file."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Run the five-step tender bid evaluation harness for a case path."""
    _ensure_cli_runtime()
    _invoke_text_command(
        run_command_full(
            "tender-evaluate",
            path,
            conversation_id=conversation_id or new_conversation_id(),
            resume_session_id=resume_session_id or None,
            fork_from_session_id=fork_from_session_id or None,
        )
    )


@app.command("tender-evaluate-json")
def tender_evaluate_json(
    path: str = typer.Argument(..., help="Path to a tender case directory or file."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Run tender bid evaluation with structured audit-result output and print metadata."""
    _ensure_cli_runtime()

    async def _run() -> tuple[dict | list, AgentRunMeta]:
        return await run_command_json(
            "tender-evaluate",
            path,
            conversation_id=conversation_id or new_conversation_id(),
            resume_session_id=resume_session_id or None,
            fork_from_session_id=fork_from_session_id or None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        )

    _invoke_json_command(_run())


@app.command("init-rules")
def init_rules(
    source: str = typer.Argument(..., help="Path to a source policy document."),
    domain: str = typer.Argument(..., help="Target domain name."),
) -> None:
    """Initialize structured rules from a source document."""
    _ensure_cli_runtime()
    try:
        canonical_source, proxy_path = prepare_text_proxy(source, INIT_RULES_PROXY_DIR)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="source") from exc

    readable_source = proxy_path if proxy_path else canonical_source

    async def _run() -> tuple[dict | list, AgentRunMeta]:
        return await run_command_json(
            "init-rules",
            readable_source,
            domain,
            conversation_id=new_conversation_id(),
            schema_name=INIT_RULES_REPORT_SCHEMA_NAME,
        )

    _invoke_json_command(_run())


@app.command()
def sessions(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List logged application sessions."""
    _echo_json(
        list_logged_sessions_admin(
            conversation_id=conversation_id or None,
            limit=limit,
            offset=offset,
        )
    )


@app.command()
def transcript(
    session_id: str = typer.Argument(..., help="Claude session id."),
    limit: int = typer.Option(100, help="Maximum messages."),
    offset: int = typer.Option(0, help="Message offset."),
) -> None:
    """Show Claude transcript messages for a saved session."""
    _echo_json(
        get_sdk_session_transcript(session_id=session_id, limit=limit, offset=offset)
    )


@app.command()
def conversations(
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List conversation summaries."""
    _echo_json(list_conversation_summaries_admin(limit=limit, offset=offset))


@app.command()
def requests(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    claude_session_id: str = typer.Option("", help="Filter by Claude session id."),
    route: str = typer.Option("", help="Filter by route."),
    status: str = typer.Option("", help="Filter by request status."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List serve-level request audits."""
    _echo_json(
        list_request_audits_admin(
            conversation_id=conversation_id or None,
            claude_session_id=claude_session_id or None,
            route=route or None,
            status=status or None,
            limit=limit,
            offset=offset,
        )
    )


@app.command("request-detail")
def request_detail(request_id: str = typer.Argument(..., help="Request id.")) -> None:
    """Show a single serve-level request audit."""
    record = get_request_audit_by_request_id_admin(request_id=request_id)
    if record is None:
        typer.echo("Request not found.")
        raise typer.Exit(code=1)
    _echo_json(record)


@app.command()
def results(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    claim_id: str = typer.Option("", help="Filter by claim id."),
    verdict: str = typer.Option("", help="Filter by verdict."),
    manual_review_reason: str = typer.Option("", help="Filter by manual review reason."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List archived structured results."""
    _echo_json(
        list_result_records_admin(
            conversation_id=conversation_id or None,
            claim_id=claim_id or None,
            verdict=verdict or None,
            manual_review_reason=manual_review_reason or None,
            limit=limit,
            offset=offset,
        )
    )


@app.command("result-detail")
def result_detail(request_id: str = typer.Argument(..., help="Request id.")) -> None:
    """Show one archived structured result."""
    record = get_result_record_by_request_id_admin(request_id=request_id)
    if record is None:
        typer.echo("Result not found.")
        raise typer.Exit(code=1)
    _echo_json(
        {
            "record": record,
            "payload": get_result_payload_by_request_id_admin(request_id=request_id),
            "linked_memories": list_memory_records(source_request_id=request_id, limit=100, offset=0),
            "review_delta": get_review_delta_payload_by_request_id_admin(request_id),
        }
    )


@app.command()
def memories(
    domain: str = typer.Option("", help="Filter by domain."),
    category: str = typer.Option("", help="Filter by category."),
    recommended_verdict: str = typer.Option("", help="Filter by recommended verdict."),
    manual_review_reason: str = typer.Option("", help="Filter by manual review reason."),
    source_request_id: str = typer.Option("", help="Filter by source request id."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List indexed memory assets."""
    _echo_json(
        list_memory_records(
            domain=domain or None,
            category=category or None,
            recommended_verdict=recommended_verdict or None,
            manual_review_reason=manual_review_reason or None,
            source_request_id=source_request_id or None,
            limit=limit,
            offset=offset,
        )
    )


@app.command("memory-detail")
def memory_detail(memory_id: str = typer.Argument(..., help="Memory id.")) -> None:
    """Show one indexed memory asset."""
    record = get_memory_record_by_id(memory_id)
    if record is None:
        typer.echo("Memory not found.")
        raise typer.Exit(code=1)
    _echo_json(record)


@app.command("review-deltas")
def review_deltas(
    claim_id: str = typer.Option("", help="Filter by claim id."),
    final_recommendation: str = typer.Option("", help="Filter by final recommendation."),
    reviewer_verdict: str = typer.Option("", help="Filter by reviewer verdict."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List indexed review delta records."""
    _echo_json(
        list_review_delta_records_admin(
            claim_id=claim_id or None,
            final_recommendation=final_recommendation or None,
            reviewer_verdict=reviewer_verdict or None,
            limit=limit,
            offset=offset,
        )
    )


@app.command("review-delta-detail")
def review_delta_detail(request_id: str = typer.Argument(..., help="Request id.")) -> None:
    """Show one indexed review delta payload."""
    record = get_review_delta_record_by_request_id_admin(request_id)
    if record is None:
        typer.echo("Review delta not found.")
        raise typer.Exit(code=1)
    _echo_json(
        {
            "record": record,
            "payload": get_review_delta_payload_by_request_id_admin(request_id),
        }
    )


@app.command("validate-assets")
def validate_assets() -> None:
    """Validate rule and memory assets under knowledge/."""
    report = validate_knowledge_assets()
    _echo_json(report)
    if report["status"] != "ok":
        raise typer.Exit(code=1)


@app.command()
def maintenance() -> None:
    """Run local maintenance tasks: rotate logs, archive sessions, clean up submissions."""
    report = run_maintenance()
    _echo_json(report)


@app.command()
def serve(
    host: str = typer.Option("", help="Bind host. Defaults to APP_SERVER_HOST."),
    port: int = typer.Option(0, help="Bind port. Defaults to APP_SERVER_PORT."),
) -> None:
    """Start the HTTP API server."""
    # 真实服务进程默认开启运行日志文件落盘（app.log/error.log）；env 显式设置可覆盖。
    os.environ.setdefault("LOG_TO_FILES", "true")
    settings = config_module.get_app_settings()
    resolved_host = host or settings.api_host
    resolved_port = port or settings.api_port
    uvicorn.run("server.api:app", host=resolved_host, port=resolved_port, reload=False)


@app.command("migrate-storage")
def migrate_storage_command() -> None:
    """一次性迁移：旧 logs/ 各域 SQLite + by-request payload → 统一库 platform.sqlite3（幂等可重复）。"""
    from server.stores.migrate import migrate_storage

    _echo_json(migrate_storage())


if __name__ == "__main__":
    app()
