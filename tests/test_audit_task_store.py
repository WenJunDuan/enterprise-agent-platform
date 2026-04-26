from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Any

from server.stores.audit_task_store import (
    get_audit_task,
    list_audit_tasks,
    recover_stale_audit_tasks,
    upsert_audit_task,
)


def _task(request_id: str, tenant: str = "tenantA", status: str = "accepted") -> dict[str, Any]:
    return {
        "request_id": request_id,
        "tenant": tenant,
        "session_id": None,
        "status": status,
        "mode": "upload",
        "source_mode": "upload",
        "case_path": "/tmp/test",
        "claim_id": None,
        "result_file": None,
        "error_detail": None,
        "progress_message": "测试",
        "submitted_at": "2026-04-20T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "updated_at": "2026-04-20T00:00:00+00:00",
    }


def test_create_and_get_task(isolated_local_layout: dict[str, Path]) -> None:
    upsert_audit_task(_task("req-001"))
    record = get_audit_task("req-001", tenant="tenantA")
    assert record is not None
    assert record["request_id"] == "req-001"
    assert record["status"] == "accepted"


def test_update_task_status(isolated_local_layout: dict[str, Path]) -> None:
    upsert_audit_task(_task("req-002"))
    upsert_audit_task({
        "request_id": "req-002",
        "status": "running",
        "updated_at": "2026-04-20T01:00:00+00:00",
    })
    record = get_audit_task("req-002", tenant="tenantA")
    assert record is not None
    assert record["status"] == "running"


def test_get_task_wrong_tenant_returns_none(isolated_local_layout: dict[str, Path]) -> None:
    upsert_audit_task(_task("req-003", tenant="tenantA"))
    assert get_audit_task("req-003", tenant="tenantB") is None


def test_get_nonexistent_task_returns_none(isolated_local_layout: dict[str, Path]) -> None:
    assert get_audit_task("does-not-exist", tenant="tenantA") is None


def test_list_tasks_scoped_by_tenant(isolated_local_layout: dict[str, Path]) -> None:
    upsert_audit_task(_task("req-004", tenant="tenantA"))
    upsert_audit_task(_task("req-005", tenant="tenantB"))
    ids_a = {r["request_id"] for r in list_audit_tasks("tenantA")}
    assert "req-004" in ids_a
    assert "req-005" not in ids_a


def test_list_tasks_status_filter(isolated_local_layout: dict[str, Path]) -> None:
    upsert_audit_task(_task("req-006", status="accepted"))
    upsert_audit_task(_task("req-007", status="running"))
    running = list_audit_tasks("tenantA", status="running")
    assert all(r["status"] == "running" for r in running)
    accepted = list_audit_tasks("tenantA", status="accepted")
    assert all(r["status"] == "accepted" for r in accepted)


def test_list_tasks_pagination(isolated_local_layout: dict[str, Path]) -> None:
    for i in range(6):
        upsert_audit_task(_task(f"req-page-{i:03d}"))
    page1 = list_audit_tasks("tenantA", limit=3, offset=0)
    page2 = list_audit_tasks("tenantA", limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 3
    assert {r["request_id"] for r in page1}.isdisjoint({r["request_id"] for r in page2})


def test_recover_stale_tasks(isolated_local_layout: dict[str, Path]) -> None:
    upsert_audit_task({**_task("req-stale"), "status": "running", "started_at": "2020-01-01T00:00:00+00:00"})
    upsert_audit_task({**_task("req-fresh"), "status": "running", "started_at": "2099-01-01T00:00:00+00:00"})
    recovered = recover_stale_audit_tasks(timeout_seconds=60)
    assert "req-stale" in recovered
    assert "req-fresh" not in recovered
    assert get_audit_task("req-stale", tenant="tenantA")["status"] == "failed"


def test_concurrent_writes_no_data_loss(isolated_local_layout: dict[str, Path]) -> None:
    def write(i: int) -> None:
        upsert_audit_task(_task(f"req-conc-{i:03d}"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(write, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    all_records = list_audit_tasks("tenantA", limit=100)
    conc_ids = {r["request_id"] for r in all_records if r["request_id"].startswith("req-conc-")}
    assert len(conc_ids) == 20
