"""Python process manager for starting and maintaining the local serve API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import typer

from server.ops.diagnostics import collect_runtime_diagnostics
from server.ops.maintenance import run_maintenance
from server.platform.config import get_app_settings
from server.platform.logging_setup import configure_logging
from server.platform.paths import (
    APP_SERVER_STDERR_LOG,
    APP_SERVER_STDOUT_LOG,
    PROJECT_ROOT,
    ensure_local_layout,
)
from server.stores.runtime_store import (
    build_runtime_record,
    process_is_running,
    read_runtime_pid,
    read_runtime_record,
    runtime_status_snapshot,
    stop_process,
    utc_now,
    write_runtime_record,
)

ensure_local_layout()
configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="kv" if os.getenv("DEV", "").lower() in {"1", "true", "yes", "on"} or os.getenv("LOG_FORMAT") == "kv" else "json",
)

app = typer.Typer(help="Manage the local Enterprise Agent API process.")


def _build_server_command(host: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "server.api:app",
        "--host",
        host,
        "--port",
        str(port),
        "--no-server-header",
    ]


def _build_service_urls(host: str, port: int) -> dict[str, str]:
    base_url = f"http://{host}:{port}"
    return {
        "base_url": base_url,
        "health": f"{base_url}/health",
        "audit_submit": f"{base_url}/audit/submit",
        "audit_task_template": f"{base_url}/audit/tasks/{{request_id}}",
        "audit_result_template": f"{base_url}/audit/tasks/{{request_id}}/result",
    }


def _probe_json_endpoint(url: str, timeout_seconds: float = 1.5) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"raw": body}
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "payload": payload,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw": body} if body else None
        return {
            "ok": False,
            "status_code": exc.code,
            "payload": payload,
            "error": str(exc),
        }
    except Exception as exc:  # pragma: no cover - network failure details vary
        return {
            "ok": False,
            "status_code": None,
            "payload": None,
            "error": str(exc),
        }


def _service_http_snapshot(runtime_snapshot: dict[str, object]) -> dict[str, object]:
    record = runtime_snapshot.get("record") or {}
    settings = get_app_settings()
    host = str((record or {}).get("host") or settings.api_host)
    port = int((record or {}).get("port") or settings.api_port)
    urls = _build_service_urls(host, port)
    running = bool(runtime_snapshot.get("running"))
    if not running:
        return {
            "running": False,
            "urls": urls,
            "health": {"ok": False, "status_code": None, "payload": None, "error": "app-server is not running"},
        }
    return {
        "running": True,
        "urls": urls,
        "health": _probe_json_endpoint(urls["health"]),
    }


def _status_payload() -> dict[str, object]:
    runtime = runtime_status_snapshot()
    service_http = _service_http_snapshot(runtime)
    return {
        "runtime": runtime,
        "service_http": service_http,
    }


def _write_running_record(*, pid: int, host: str, port: int, command: list[str], started_at: str) -> None:
    settings = get_app_settings()
    write_runtime_record(
        build_runtime_record(
            process_name=settings.app_server_name,
            status="running",
            pid=pid,
            host=host,
            port=port,
            command=command,
            started_at=started_at,
            stopped_at=None,
            cwd=str(PROJECT_ROOT),
        )
    )


def _write_stopped_record(*, host: str, port: int, command: list[str], error: str | None = None) -> None:
    settings = get_app_settings()
    record = read_runtime_record()
    write_runtime_record(
        build_runtime_record(
            process_name=settings.app_server_name,
            status="stopped" if error is None else "error",
            pid=None,
            host=host,
            port=port,
            command=command,
            started_at=record.get("started_at") if record else None,
            stopped_at=utc_now(),
            cwd=str(PROJECT_ROOT),
            last_error=error,
        )
    )


@app.command()
def start(
    host: str = typer.Option("", help="Bind host. Defaults to APP_SERVER_HOST."),
    port: int = typer.Option(0, help="Bind port. Defaults to APP_SERVER_PORT."),
) -> None:
    """Start the API in the background and persist runtime state."""
    settings = get_app_settings()
    resolved_host = host or settings.api_host
    resolved_port = port or settings.api_port
    command = _build_server_command(resolved_host, resolved_port)

    current_pid = read_runtime_pid()
    if process_is_running(current_pid):
        typer.echo(f"app-server is already running with PID {current_pid}.")
        raise typer.Exit(code=1)

    maintenance = run_maintenance()
    stdout_handle = APP_SERVER_STDOUT_LOG.open("a", encoding="utf-8")
    stderr_handle = APP_SERVER_STDERR_LOG.open("a", encoding="utf-8")
    started_at = utc_now()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
            # 托管服务进程默认开启运行日志文件落盘（app.log/error.log）；env 显式设置可覆盖。
            env={
                "LOG_TO_FILES": "true",
                **os.environ,
                "PYTHONUNBUFFERED": "1",
            },
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    time.sleep(1)
    return_code = process.poll()
    if return_code is not None:
        error = f"app-server exited early with code {return_code}"
        _write_stopped_record(host=resolved_host, port=resolved_port, command=command, error=error)
        typer.echo(error)
        typer.echo(json.dumps(maintenance, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    _write_running_record(
        pid=process.pid,
        host=resolved_host,
        port=resolved_port,
        command=command,
        started_at=started_at,
    )
    typer.echo(f"app-server started on {resolved_host}:{resolved_port} with PID {process.pid}.")
    typer.echo(json.dumps({"maintenance": maintenance}, ensure_ascii=False, indent=2))


@app.command()
def stop(timeout: float = typer.Option(10.0, help="Graceful stop timeout in seconds.")) -> None:
    """Stop the background API process."""
    record = read_runtime_record() or {}
    pid = read_runtime_pid()
    if not process_is_running(pid):
        typer.echo("app-server is not running.")
        _write_stopped_record(
            host=str(record.get("host") or get_app_settings().api_host),
            port=int(record.get("port") or get_app_settings().api_port),
            command=list(record.get("command") or _build_server_command(get_app_settings().api_host, get_app_settings().api_port)),
        )
        return

    success = stop_process(pid, timeout_seconds=timeout)
    _write_stopped_record(
        host=str(record.get("host") or get_app_settings().api_host),
        port=int(record.get("port") or get_app_settings().api_port),
        command=list(record.get("command") or _build_server_command(get_app_settings().api_host, get_app_settings().api_port)),
        error=None if success else f"failed to stop pid {pid}",
    )
    if success:
        typer.echo(f"app-server stopped (PID {pid}).")
        return
    typer.echo(f"Failed to stop app-server PID {pid}.")
    raise typer.Exit(code=1)


@app.command()
def restart(
    host: str = typer.Option("", help="Bind host. Defaults to APP_SERVER_HOST."),
    port: int = typer.Option(0, help="Bind port. Defaults to APP_SERVER_PORT."),
    timeout: float = typer.Option(10.0, help="Graceful stop timeout in seconds."),
) -> None:
    """Restart the background API process."""
    stop(timeout=timeout)
    start(host=host, port=port)


@app.command()
def status() -> None:
    """Show current app-server runtime state."""
    typer.echo(json.dumps(_status_payload(), ensure_ascii=False, indent=2))


@app.command()
def logs(
    lines: int = typer.Option(50, help="How many lines to show."),
    stderr: bool = typer.Option(False, help="Show stderr instead of stdout."),
    follow: bool = typer.Option(False, help="Follow the log until interrupted."),
) -> None:
    """Print runtime logs from the managed API process."""
    path = APP_SERVER_STDERR_LOG if stderr else APP_SERVER_STDOUT_LOG
    if not path.exists():
        typer.echo(f"No log file yet: {path}")
        raise typer.Exit(code=1)

    for line in _tail_lines(path, lines):
        typer.echo(line.rstrip("\n"))

    if not follow:
        return

    with path.open("r", encoding="utf-8") as handle:
        handle.seek(0, 2)
        try:
            while True:
                line = handle.readline()
                if line:
                    typer.echo(line.rstrip("\n"))
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            return


@app.command()
def maintain() -> None:
    """Run lightweight local maintenance tasks."""
    typer.echo(json.dumps(run_maintenance(), ensure_ascii=False, indent=2))


@app.command()
def doctor(
    strict: bool = typer.Option(False, help="Exit non-zero when diagnostics are degraded."),
    require_running: bool = typer.Option(False, help="Also fail when app-server is not running."),
) -> None:
    """Run shared runtime diagnostics for local operations."""
    report = collect_runtime_diagnostics()
    service_http = _service_http_snapshot(runtime_status_snapshot())
    report["service_http"] = service_http
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))

    should_fail = False
    if strict and report["status"] != "ok":
        should_fail = True
    if require_running and not bool(report["checks"]["app_server"]["running"]):
        should_fail = True

    if should_fail:
        raise typer.Exit(code=1)


def _tail_lines(path: Path, lines: int) -> list[str]:
    with path.open("r", encoding="utf-8") as handle:
        content = handle.readlines()
    return content[-lines:]


if __name__ == "__main__":
    app()
