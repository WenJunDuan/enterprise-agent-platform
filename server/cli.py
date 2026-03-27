"""CLI entrypoints for the platform."""

from __future__ import annotations

import asyncio
import json

import typer
import uvicorn

from server.core import (
    AgentRunMeta,
    INIT_RULES_REPORT_SCHEMA_NAME,
    run_agent_full,
    run_agent_json,
)
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


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="Raw prompt text."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Run one prompt and print the final output."""
    typer.echo(
        asyncio.run(
            run_agent_full(
                prompt,
                conversation_id=conversation_id or new_conversation_id(),
                resume_session_id=resume_session_id or None,
                fork_from_session_id=fork_from_session_id or None,
            )
        )
    )


@app.command()
def audit(
    path: str = typer.Argument(..., help="Path to a source payload."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Trigger the built-in single item workflow."""
    typer.echo(
        asyncio.run(
            run_agent_full(
                f"/audit {path}",
                conversation_id=conversation_id or new_conversation_id(),
                resume_session_id=resume_session_id or None,
                fork_from_session_id=fork_from_session_id or None,
            )
        )
    )


@app.command("audit-json")
def audit_json(
    path: str = typer.Argument(..., help="Path to a source payload."),
    conversation_id: str = typer.Option("", help="Application conversation id."),
    resume_session_id: str = typer.Option("", help="Resume a specific Claude session id."),
    fork_from_session_id: str = typer.Option("", help="Fork from a previous Claude session."),
) -> None:
    """Run audit with structured output and print metadata."""

    async def _run() -> tuple[dict | list, AgentRunMeta]:
        return await run_agent_json(
            f"/audit {path}",
            conversation_id=conversation_id or new_conversation_id(),
            resume_session_id=resume_session_id or None,
            fork_from_session_id=fork_from_session_id or None,
        )

    payload, meta = asyncio.run(_run())
    typer.echo(
        json.dumps(
            {
                "request_id": meta.request_id,
                "conversation_id": meta.conversation_id,
                "claude_session_id": meta.claude_session_id,
                "schema_name": meta.schema_name,
                "result_file": meta.result_file,
                "cost": meta.cost_usd,
                "response": payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("init-rules")
def init_rules(
    source: str = typer.Argument(..., help="Path to a source policy document."),
    domain: str = typer.Argument(..., help="Target domain name."),
) -> None:
    """Initialize structured rules from a source document."""

    async def _run() -> tuple[dict | list, AgentRunMeta]:
        return await run_agent_json(
            f"/init-rules {source} {domain}",
            conversation_id=new_conversation_id(),
            schema_name=INIT_RULES_REPORT_SCHEMA_NAME,
        )

    payload, meta = asyncio.run(_run())
    typer.echo(
        json.dumps(
            {
                "request_id": meta.request_id,
                "conversation_id": meta.conversation_id,
                "claude_session_id": meta.claude_session_id,
                "schema_name": meta.schema_name,
                "result_file": meta.result_file,
                "cost": meta.cost_usd,
                "response": payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def chat() -> None:
    """Start an interactive chat session."""
    from server.chat import interactive_chat

    asyncio.run(interactive_chat())


@app.command()
def sessions(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List logged application sessions."""
    typer.echo(
        json.dumps(
            list_logged_sessions(
                conversation_id=conversation_id or None,
                limit=limit,
                offset=offset,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def transcript(
    session_id: str = typer.Argument(..., help="Claude session id."),
    limit: int = typer.Option(100, help="Maximum messages."),
    offset: int = typer.Option(0, help="Message offset."),
) -> None:
    """Show Claude transcript messages for a saved session."""
    typer.echo(
        json.dumps(
            get_sdk_session_transcript(session_id=session_id, limit=limit, offset=offset),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def conversations(
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List conversation summaries."""
    typer.echo(
        json.dumps(
            list_conversation_summaries(limit=limit, offset=offset),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def requests(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    claude_session_id: str = typer.Option("", help="Filter by Claude session id."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List serve-level request audits."""
    typer.echo(
        json.dumps(
            list_request_audits(
                conversation_id=conversation_id or None,
                claude_session_id=claude_session_id or None,
                limit=limit,
                offset=offset,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("request-detail")
def request_detail(request_id: str = typer.Argument(..., help="Request id.")) -> None:
    """Show a single serve-level request audit."""
    record = get_request_audit_by_request_id(request_id=request_id)
    if record is None:
        typer.echo("Request not found.")
        raise typer.Exit(code=1)
    typer.echo(json.dumps(record, ensure_ascii=False, indent=2))


@app.command()
def results(
    conversation_id: str = typer.Option("", help="Filter by application conversation id."),
    claim_id: str = typer.Option("", help="Filter by claim id."),
    limit: int = typer.Option(20, help="Maximum records."),
    offset: int = typer.Option(0, help="Starting offset."),
) -> None:
    """List archived structured results."""
    typer.echo(
        json.dumps(
            list_result_records(
                conversation_id=conversation_id or None,
                claim_id=claim_id or None,
                limit=limit,
                offset=offset,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("result-detail")
def result_detail(request_id: str = typer.Argument(..., help="Request id.")) -> None:
    """Show one archived structured result."""
    record = get_result_record_by_request_id(request_id=request_id)
    if record is None:
        typer.echo("Result not found.")
        raise typer.Exit(code=1)
    typer.echo(
        json.dumps(
            {
                "record": record,
                "payload": get_result_payload_by_request_id(request_id=request_id),
            },
            ensure_ascii=False,
            indent=2,
        )
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
