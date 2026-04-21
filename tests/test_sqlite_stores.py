from __future__ import annotations
from pathlib import Path

from server.platform.storage import append_json_file, append_jsonl_record
from server.stores import memory_store as memory_store_module
from server.stores import request_store as request_store_module
from server.stores import result_store as result_store_module
from server.stores import session_store as session_store_module


def test_default_query_stores_use_sqlite() -> None:
    assert type(session_store_module.SESSION_STORE).__name__ == "SQLiteSessionStore"
    assert type(request_store_module.REQUEST_AUDIT_STORE).__name__ == "SQLiteRequestAuditStore"
    assert type(result_store_module.RESULT_STORE).__name__ == "SQLiteResultStore"


def test_sqlite_session_store_appends_and_queries_records(tmp_path: Path) -> None:
    store = session_store_module.SQLiteSessionStore(
        db_path=tmp_path / "sessions.sqlite3",
        legacy_shard_dir=None,
    )
    record = session_store_module.SessionRecord(
        request_id="req-1",
        conversation_id="conv-1",
        claude_session_id="sess-1",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        request_mode="structured",
        prompt_preview="/audit tests/fixtures/x",
        log_file="logs/sessions/events/1.jsonl",
        status="success",
        result_subtype="success",
        cost_usd=0.12,
        started_at="2026-04-21T09:00:00+00:00",
        finished_at="2026-04-21T09:00:02+00:00",
        tenant="tenantA",
        result_file="results/by-request/2026/04/21/req-1.json",
    )

    store.append_record(record)

    loaded = store.load_records(tenant="tenantA")
    assert len(loaded) == 1
    assert loaded[0]["request_id"] == "req-1"
    assert store.get_record_by_request_id("req-1", tenant="tenantA") is not None
    assert store.resolve_latest_session_id("conv-1", tenant="tenantA") == "sess-1"
    summaries = store.list_conversation_summaries(tenant="tenantA")
    assert summaries[0]["conversation_id"] == "conv-1"


def test_sqlite_session_store_backfills_legacy_jsonl(tmp_path: Path) -> None:
    shard_dir = tmp_path / "sessions"
    shard_path = shard_dir / "sessions-2026-04.jsonl"
    append_jsonl_record(
        shard_path,
        {
            "request_id": "req-legacy",
            "conversation_id": "conv-legacy",
            "claude_session_id": "sess-legacy",
            "resume_session_id": None,
            "fork_from_session_id": None,
            "schema_name": None,
            "request_mode": "structured",
            "prompt_preview": "legacy",
            "log_file": "logs/sessions/events/legacy.jsonl",
            "status": "success",
            "result_subtype": "success",
            "cost_usd": 0.01,
            "started_at": "2026-04-21T08:00:00+00:00",
            "finished_at": "2026-04-21T08:00:01+00:00",
            "tenant": "tenantA",
            "result_file": None,
        },
    )

    store = session_store_module.SQLiteSessionStore(
        db_path=tmp_path / "sessions.sqlite3",
        legacy_shard_dir=shard_dir,
    )

    loaded = store.load_records(tenant="tenantA")
    assert len(loaded) == 1
    assert loaded[0]["request_id"] == "req-legacy"


def test_sqlite_result_store_archives_and_queries_records(tmp_path: Path) -> None:
    archive_root = tmp_path / "results" / "by-request"
    store = result_store_module.SQLiteResultStore(
        db_path=tmp_path / "results.sqlite3",
        archive_root=archive_root,
        legacy_shard_dir=None,
    )
    record = result_store_module.ResultRecord(
        request_id="req-1",
        created_at="2026-04-21T09:00:00+00:00",
        conversation_id="conv-1",
        request_mode="structured",
        schema_name="common/audit-result.schema.json",
        result_file="results/by-request/2026/04/21/req-1.json",
        tenant="tenantA",
        claude_session_id="sess-1",
        session_id="sess-1",
        resume_session_id=None,
        fork_from_session_id=None,
        result_subtype="success",
        claim_id="CLAIM-1",
        verdict="approved",
        cost_usd=0.2,
        prompt_preview="/audit x",
    )

    store.archive_result(record, {"response": {"claim_id": "CLAIM-1"}})

    loaded = store.list_records(tenant="tenantA", claim_id="CLAIM-1")
    assert len(loaded) == 1
    assert loaded[0]["request_id"] == "req-1"
    assert store.get_record_by_request_id("req-1", tenant="tenantA") is not None
    assert store.get_payload_by_request_id("req-1", tenant="tenantA") == {
        "response": {"claim_id": "CLAIM-1"}
    }


def test_sqlite_result_store_backfills_legacy_jsonl(tmp_path: Path) -> None:
    shard_dir = tmp_path / "results" / "index"
    archive_root = tmp_path / "results" / "by-request"
    archive_file = archive_root / "2026" / "04" / "21" / "req-legacy.json"
    append_json_file(archive_file, {"response": {"claim_id": "CLAIM-LEGACY"}})
    append_jsonl_record(
        shard_dir / "results-2026-04.jsonl",
        {
            "request_id": "req-legacy",
            "created_at": "2026-04-21T08:00:00+00:00",
            "conversation_id": "conv-legacy",
            "request_mode": "structured",
            "schema_name": "common/audit-result.schema.json",
            "result_file": "results/by-request/2026/04/21/req-legacy.json",
            "tenant": "tenantA",
            "claude_session_id": "sess-legacy",
            "session_id": "sess-legacy",
            "resume_session_id": None,
            "fork_from_session_id": None,
            "result_subtype": "success",
            "claim_id": "CLAIM-LEGACY",
            "verdict": "manual_review",
            "cost_usd": 0.1,
            "prompt_preview": "/audit legacy",
        },
    )

    store = result_store_module.SQLiteResultStore(
        db_path=tmp_path / "results.sqlite3",
        archive_root=archive_root,
        legacy_shard_dir=shard_dir,
    )

    record = store.get_record_by_request_id("req-legacy", tenant="tenantA")
    assert record is not None
    assert record["claim_id"] == "CLAIM-LEGACY"
    payload = store.get_payload_by_request_id("req-legacy", tenant="tenantA")
    assert payload == {"response": {"claim_id": "CLAIM-LEGACY"}}


def test_sqlite_request_store_dual_writes_jsonl_and_queries_from_sqlite(tmp_path: Path) -> None:
    shard_dir = tmp_path / "requests"
    db_path = shard_dir / "index.sqlite3"
    store = request_store_module.SQLiteRequestAuditStore(db_path, shard_dir)

    record = request_store_module.RequestAuditRecord(
        request_id="req-1",
        route="/audit",
        method="POST",
        status_code=200,
        status="success",
        duration_ms=12,
        created_at="2026-04-21T10:00:00+00:00",
        tenant="tenantA",
        conversation_id="conv-1",
        claude_session_id="sess-1",
        session_id="sess-1",
        request_payload={"path": "tests/fixtures/x"},
    )
    store.append_record(record)

    assert any(shard_dir.glob("requests-*.jsonl"))
    loaded = store.list_records(tenant="tenantA", route="/audit", status="success")
    assert len(loaded) == 1
    assert loaded[0]["request_payload"] == {"path": "tests/fixtures/x"}


def test_sqlite_memory_store_indexes_memory_files(tmp_path: Path) -> None:
    memory_root = tmp_path / "knowledge" / "memory"
    (memory_root / "expense").mkdir(parents=True, exist_ok=True)
    payload = {
        "memory_id": "expense.travel.pre-approval-mismatch.manual-review.v1",
        "domain": "expense",
        "memory_type": "exception_pattern",
        "title": "差旅报销：事后补提出差申请的拒绝模式",
        "summary": "示例摘要",
        "category": "travel",
        "applicable_when": ["缺少出差申请单"],
        "checkpoints": ["检查是否事前申请"],
        "policy_refs": ["expense.travel.016"],
        "recommended_verdict": "manual_review",
        "manual_review_reason": "pre_approval_mismatch",
        "rationale": "示例原因",
        "tags": ["travel", "pre-approval"],
        "source_trace": {
            "request_id": "req-1",
            "result_file": "results/by-request/2026/04/21/req-1.json",
            "claim_id": "EXP-1",
            "conversation_id": "conv-1",
            "claude_session_id": "sess-1",
            "review_delta_file": None,
        },
        "distilled_by": "system-memory-distill",
        "distilled_at": "2026-04-21T10:00:00+00:00",
    }
    append_json_file(
        memory_root / "expense" / "expense.travel.pre-approval-mismatch.manual-review.v1.json",
        payload,
    )

    store = memory_store_module.SQLiteMemoryStore(tmp_path / "logs" / "memory-index.sqlite3", memory_root)
    records = store.list_records(domain="expense", manual_review_reason="pre_approval_mismatch")

    assert len(records) == 1
    assert records[0]["memory_id"] == payload["memory_id"]
    assert records[0]["payload"]["source_trace"]["request_id"] == "req-1"
