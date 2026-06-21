"""Runtime state persistence for the app-server process manager."""

from __future__ import annotations

import os
import signal
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import (
    APP_SERVER_PID_FILE,
    APP_SERVER_STATUS_FILE,
    latest_app_server_log_path,
    ensure_local_layout,
)
from server.platform.storage import append_json_file, load_json_file

ensure_local_layout()


@dataclass(slots=True)
class RuntimeProcessRecord:
    process_name: str
    status: str
    pid: int | None
    host: str
    port: int
    command: list[str]
    started_at: str | None
    stopped_at: str | None
    updated_at: str
    pid_file: str
    stdout_log: str
    stderr_log: str
    cwd: str
    last_error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_runtime_record(record: RuntimeProcessRecord) -> None:
    append_json_file(APP_SERVER_STATUS_FILE, asdict(record))
    if record.pid is None:
        remove_pid_file()
    else:
        APP_SERVER_PID_FILE.write_text(str(record.pid), encoding="utf-8")


def read_runtime_record() -> dict[str, Any] | None:
    return load_json_file(APP_SERVER_STATUS_FILE)


def read_runtime_pid() -> int | None:
    if not APP_SERVER_PID_FILE.exists():
        return None
    raw = APP_SERVER_PID_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return int(raw)


def remove_pid_file() -> None:
    if APP_SERVER_PID_FILE.exists():
        APP_SERVER_PID_FILE.unlink()


def process_is_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def build_runtime_record(
    *,
    process_name: str,
    status: str,
    pid: int | None,
    host: str,
    port: int,
    command: list[str],
    started_at: str | None,
    stopped_at: str | None,
    cwd: str,
    last_error: str | None = None,
) -> RuntimeProcessRecord:
    return RuntimeProcessRecord(
        process_name=process_name,
        status=status,
        pid=pid,
        host=host,
        port=port,
        command=command,
        started_at=started_at,
        stopped_at=stopped_at,
        updated_at=utc_now(),
        pid_file=str(APP_SERVER_PID_FILE),
        stdout_log=str(latest_app_server_log_path(False)),
        stderr_log=str(latest_app_server_log_path(True)),
        cwd=cwd,
        last_error=last_error,
    )


def stop_process(pid: int, timeout_seconds: float = 10.0) -> bool:
    """Terminate a process gracefully, then force kill if needed."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True

    deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
    while datetime.now(timezone.utc).timestamp() < deadline:
        if not process_is_running(pid):
            return True
        time.sleep(0.2)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    return not process_is_running(pid)


def runtime_status_snapshot() -> dict[str, Any]:
    record = read_runtime_record()
    pid = read_runtime_pid()
    running = process_is_running(pid)
    return {
        "record": record,
        "pid": pid,
        "running": running,
        "status_file": str(APP_SERVER_STATUS_FILE),
        "stdout_log": str(latest_app_server_log_path(False)),
        "stderr_log": str(latest_app_server_log_path(True)),
    }
