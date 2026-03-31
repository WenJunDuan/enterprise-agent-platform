"""CLI entrypoints for the platform."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer
import uvicorn

from server.command_adapter import run_command_full, run_command_json
from server.core import (
    AgentRunMeta,
    ClaudeRuntimeError,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    DEFAULT_OUTPUT_SCHEMA_NAME,
    run_agent_full,
)
from server.platform.config import get_claude_runtime_report
from server.platform.source_proxy import prepare_text_proxy
from server.stores.request_store import get_request_audit_by_request_id, list_request_audits
from server.stores.result_store import (
    get_result_payload_by_request_id,
    get_result_record_by_request_id,
    list_result_records,
)
from server.stores.session_store import (
    get_sdk_session_transcript,
    list_conversation_summaries,
    list_logged_sessions,
    new_conversation_id,
)

app = typer.Typer(help="Enterprise agent platform CLI.")
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


@app.command("init-rules")
def init_rules(
    source: str = typer.Argument(..., help="Path to a source policy document."),
    domain: str = typer.Argument(..., help="Target domain name."),
) -> None:
    """Initialize structured rules from a source document."""
    _ensure_cli_runtime()
    try:
        canonical_source, _ = prepare_text_proxy(source, INIT_RULES_PROXY_DIR)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="source") from exc

    async def _run() -> tuple[dict | list, AgentRunMeta]:
        return await run_command_json(
            "init-rules",
            canonical_source,
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
        list_logged_sessions(
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
    _echo_json(list_conversation_summaries(limit=limit, offset=offset))


@app.command()
def requests(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    claude_session_id: str = typer.Option("", help="Filter by Claude session id."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List serve-level request audits."""
    _echo_json(
        list_request_audits(
            conversation_id=conversation_id or None,
            claude_session_id=claude_session_id or None,
            limit=limit,
            offset=offset,
        )
    )


@app.command("request-detail")
def request_detail(request_id: str = typer.Argument(..., help="Request id.")) -> None:
    """Show a single serve-level request audit."""
    record = get_request_audit_by_request_id(request_id=request_id)
    if record is None:
        typer.echo("Request not found.")
        raise typer.Exit(code=1)
    _echo_json(record)


@app.command()
def results(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    claim_id: str = typer.Option("", help="Filter by claim id."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List archived structured results."""
    _echo_json(
        list_result_records(
            conversation_id=conversation_id or None,
            claim_id=claim_id or None,
            limit=limit,
            offset=offset,
        )
    )


@app.command("result-detail")
def result_detail(request_id: str = typer.Argument(..., help="Request id.")) -> None:
    """Show one archived structured result."""
    record = get_result_record_by_request_id(request_id=request_id)
    if record is None:
        typer.echo("Result not found.")
        raise typer.Exit(code=1)
    _echo_json(
        {
            "record": record,
            "payload": get_result_payload_by_request_id(request_id=request_id),
        }
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
) -> None:
    """Start the HTTP API server."""
    uvicorn.run("server.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
