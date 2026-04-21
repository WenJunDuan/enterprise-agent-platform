from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from fastapi.testclient import TestClient

from server import api as api_module
from server import core as core_module
from server.platform import paths as paths_module
from server.stores import audit_task_store as audit_task_store_module
from server.stores import memory_store as memory_store_module
from server.stores import request_store as request_store_module
from server.stores import result_store as result_store_module
from server.stores import session_store as session_store_module


def build_valid_audit_payload(claim_id: str = "CLAIM-001") -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "verdict": "approved",
        "result": True,
        "conclusion": "合规",
        "explanation": "材料齐全，符合规则。",
        "reasons": ["票据完整"],
        "policy_refs": ["expense.policy.001"],
        "risk_score": 5,
        "extracted_data": {"amount": 128},
        "evidence_chain": [
            {
                "source": "receipt.png",
                "finding": "发票金额 128 元",
                "conclusion": "可报销",
            }
        ],
        "reviewed_by": "test-suite",
        "timestamp": "2026-04-20T00:00:00+00:00",
    }


class QueryRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_session_id: str | None = None

    async def __call__(self, prompt: str, options: Any):
        resume = getattr(options, "resume", None)
        fork_session = bool(getattr(options, "fork_session", False))
        continue_conversation = bool(getattr(options, "continue_conversation", False))

        if fork_session and resume:
            session_id = f"{resume}-fork"
        elif resume:
            session_id = str(resume)
        elif continue_conversation and self.last_session_id:
            session_id = self.last_session_id
        else:
            session_id = f"session-{len(self.calls) + 1}"

        self.calls.append(
            {
                "prompt": prompt,
                "resume": resume,
                "fork_session": fork_session,
                "continue_conversation": continue_conversation,
                "session_id": session_id,
                "output_format": getattr(options, "output_format", None),
            }
        )
        self.last_session_id = session_id

        yield AssistantMessage(
            content=[TextBlock(text="ok")],
            model="test-model",
            session_id=session_id,
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id=session_id,
            total_cost_usd=0.01,
            result="ok",
            structured_output=build_valid_audit_payload(claim_id=f"CLAIM-{len(self.calls):03d}"),
        )


@pytest.fixture
def isolated_local_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    project_root = tmp_path
    logs_root = project_root / "logs"
    service_log_dir = logs_root / "service"
    service_request_dir = service_log_dir / "requests"
    service_request_db = service_request_dir / "index.sqlite3"
    audit_task_dir = service_log_dir / "audit-tasks"
    audit_task_file = audit_task_dir / "tasks.json"
    session_log_dir = logs_root / "sessions"
    session_index_dir = session_log_dir / "index"
    session_index_db = session_log_dir / "index.sqlite3"
    session_event_dir = session_log_dir / "events"
    result_log_dir = logs_root / "results"
    result_index_dir = result_log_dir / "index"
    result_index_db = result_log_dir / "index.sqlite3"
    result_by_request_dir = result_log_dir / "by-request"
    runtime_log_dir = logs_root / "runtime"
    app_server_dir = runtime_log_dir / "app-server"
    knowledge_log_dir = logs_root / "knowledge"
    memory_index_db = knowledge_log_dir / "memory-index.sqlite3"
    submissions_root = project_root / "data" / "submissions"
    memory_root = project_root / "knowledge" / "memory"

    replacements = {
        "PROJECT_ROOT": project_root,
        "LOGS_ROOT": logs_root,
        "SERVICE_LOG_DIR": service_log_dir,
        "SERVICE_REQUEST_SHARD_DIR": service_request_dir,
        "SERVICE_REQUEST_DB_FILE": service_request_db,
        "AUDIT_TASK_DIR": audit_task_dir,
        "AUDIT_TASK_FILE": audit_task_file,
        "SESSION_LOG_DIR": session_log_dir,
        "SESSION_INDEX_SHARD_DIR": session_index_dir,
        "SESSION_INDEX_DB_FILE": session_index_db,
        "SESSION_EVENT_DIR": session_event_dir,
        "RESULT_LOG_DIR": result_log_dir,
        "RESULT_INDEX_SHARD_DIR": result_index_dir,
        "RESULT_INDEX_DB_FILE": result_index_db,
        "RESULT_BY_REQUEST_DIR": result_by_request_dir,
        "RUNTIME_LOG_DIR": runtime_log_dir,
        "APP_SERVER_DIR": app_server_dir,
        "APP_SERVER_PID_FILE": app_server_dir / "server.pid",
        "APP_SERVER_STATUS_FILE": app_server_dir / "server.status.json",
        "APP_SERVER_STDOUT_LOG": app_server_dir / "stdout.log",
        "APP_SERVER_STDERR_LOG": app_server_dir / "stderr.log",
        "KNOWLEDGE_LOG_DIR": knowledge_log_dir,
        "MEMORY_INDEX_DB_FILE": memory_index_db,
        "SUBMISSION_ROOT_DIR": submissions_root,
    }
    for name, value in replacements.items():
        monkeypatch.setattr(paths_module, name, value)

    paths_module.ensure_local_layout()

    monkeypatch.setattr(core_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(api_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(api_module, "SUBMISSION_ROOT_DIR", submissions_root)
    monkeypatch.setattr(api_module, "ALLOWED_DIRECTORY_ROOT", (project_root / "data").resolve())
    monkeypatch.setattr(audit_task_store_module, "AUDIT_TASK_FILE", audit_task_file)
    monkeypatch.setattr(result_store_module, "RESULT_BY_REQUEST_DIR", result_by_request_dir)
    monkeypatch.setattr(result_store_module, "RESULT_INDEX_SHARD_DIR", result_index_dir)
    monkeypatch.setattr(request_store_module, "SERVICE_REQUEST_DB_FILE", service_request_db)
    monkeypatch.setattr(session_store_module, "SESSION_INDEX_DB_FILE", session_index_db)
    monkeypatch.setattr(result_store_module, "RESULT_INDEX_DB_FILE", result_index_db)
    monkeypatch.setattr(memory_store_module, "MEMORY_INDEX_DB_FILE", memory_index_db)
    monkeypatch.setattr(memory_store_module, "KNOWLEDGE_MEMORY_ROOT", memory_root)
    monkeypatch.setattr(
        session_store_module,
        "SESSION_STORE",
        session_store_module.SQLiteSessionStore(session_index_db, session_index_dir),
    )
    monkeypatch.setattr(
        request_store_module,
        "REQUEST_AUDIT_STORE",
        request_store_module.SQLiteRequestAuditStore(service_request_db, service_request_dir),
    )
    monkeypatch.setattr(
        result_store_module,
        "RESULT_STORE",
        result_store_module.SQLiteResultStore(result_index_db, result_by_request_dir, result_index_dir),
    )
    monkeypatch.setattr(
        memory_store_module,
        "MEMORY_STORE",
        memory_store_module.SQLiteMemoryStore(memory_index_db, memory_root),
    )
    monkeypatch.setattr(session_store_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(memory_store_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(session_store_module, "list_sessions", lambda **_: [])
    monkeypatch.setattr(session_store_module, "get_session_messages", lambda **_: [])
    monkeypatch.setattr(api_module, "_schedule_directory_audit_task", lambda **_: None)
    monkeypatch.setattr(api_module, "recover_stale_audit_tasks", lambda _timeout: [])

    (memory_root / "expense").mkdir(parents=True, exist_ok=True)
    (memory_root / "hr").mkdir(parents=True, exist_ok=True)
    (memory_root / "legal").mkdir(parents=True, exist_ok=True)

    return {
        "project_root": project_root,
        "logs_root": logs_root,
        "service_request_dir": service_request_dir,
        "service_request_db": service_request_db,
        "audit_task_file": audit_task_file,
        "session_index_dir": session_index_dir,
        "session_index_db": session_index_db,
        "session_event_dir": session_event_dir,
        "result_index_dir": result_index_dir,
        "result_index_db": result_index_db,
        "result_by_request_dir": result_by_request_dir,
        "memory_index_db": memory_index_db,
        "memory_root": memory_root,
        "submissions_root": submissions_root,
    }


@pytest.fixture
def tenant_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    keys = {
        "tenantA": "sk-A",
        "tenantB": "sk-B",
    }
    monkeypatch.setattr(api_module, "TENANT_KEYS", keys)
    return keys


@pytest.fixture
def auth_headers(tenant_keys: dict[str, str]) -> dict[str, dict[str, str]]:
    return {
        tenant: {"Authorization": f"Bearer {token}"}
        for tenant, token in tenant_keys.items()
    }


@pytest.fixture
def query_recorder(monkeypatch: pytest.MonkeyPatch) -> QueryRecorder:
    recorder = QueryRecorder()
    monkeypatch.setattr(core_module, "query", recorder)
    return recorder


@pytest.fixture
def client(
    isolated_local_layout: dict[str, Path],
    tenant_keys: dict[str, str],
) -> TestClient:
    return TestClient(api_module.app)
