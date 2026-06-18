"""audit_task_store (SQLite)：upsert 合并、租户隔离、状态过滤、删除、超时回收。

锁定从 tasks.json 全量重写迁到单库表后行为不变。各用例用唯一 request_id 前缀避免
与共享 platform.sqlite3 里的其他数据相互干扰。
"""

from __future__ import annotations

import uuid

import pytest

from server.stores import audit_task_store as store


@pytest.fixture
def rid():
    return f"test-{uuid.uuid4().hex}"


def _new_task(request_id: str, tenant: str = "acme", **over) -> dict:
    base = {
        "request_id": request_id,
        "tenant": tenant,
        "session_id": None,
        "status": "running",
        "mode": "directory",
        "source_mode": "directory",
        "case_path": "data/submissions/x",
        "submitted_at": "2026-06-19T00:00:00+00:00",
        "updated_at": "2026-06-19T00:00:00+00:00",
    }
    base.update(over)
    return base


def test_upsert_then_get_roundtrip(rid):
    store.upsert_audit_task(_new_task(rid))
    got = store.get_audit_task(rid, tenant="acme")
    assert got is not None
    assert got["status"] == "running"
    assert got["case_path"] == "data/submissions/x"


def test_partial_upsert_merges_existing_fields(rid):
    store.upsert_audit_task(_new_task(rid))
    # 部分更新：只给 status/finished，case_path/mode 应被保留（合并语义）
    store.upsert_audit_task(
        {"request_id": rid, "status": "completed", "finished_at": "2026-06-19T01:00:00+00:00"}
    )
    got = store.get_audit_task(rid, tenant="acme")
    assert got["status"] == "completed"
    assert got["finished_at"] == "2026-06-19T01:00:00+00:00"
    assert got["case_path"] == "data/submissions/x"  # 保留
    assert got["mode"] == "directory"  # 保留


def test_tenant_isolation(rid):
    store.upsert_audit_task(_new_task(rid, tenant="acme"))
    assert store.get_audit_task(rid, tenant="other") is None
    assert store.delete_audit_task(rid, tenant="other") is False
    assert store.get_audit_task(rid, tenant="acme") is not None


def test_list_filters_by_tenant_and_status(rid):
    store.upsert_audit_task(_new_task(rid + "-a", status="running"))
    store.upsert_audit_task(_new_task(rid + "-b", status="completed"))
    running = store.list_audit_tasks("acme", status="running", limit=100)
    ids = {r["request_id"] for r in running}
    assert (rid + "-a") in ids
    assert (rid + "-b") not in ids


def test_delete_returns_true_when_removed(rid):
    store.upsert_audit_task(_new_task(rid))
    assert store.delete_audit_task(rid, tenant="acme") is True
    assert store.get_audit_task(rid, tenant="acme") is None


def test_recover_stale_marks_running_as_failed(rid):
    store.upsert_audit_task(
        _new_task(rid, status="running", started_at="2026-06-19T00:00:00+00:00")
    )
    recovered = store.recover_stale_audit_tasks(
        timeout_seconds=60, now="2026-06-19T02:00:00+00:00"
    )
    assert rid in recovered
    got = store.get_audit_task_admin(rid)
    assert got["status"] == "failed"
