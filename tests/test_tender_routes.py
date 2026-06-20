"""Integration tests for tender evaluation routes (/tender/evaluate, /tender/tasks/*).

镜像 test_ocr_routes / audit 路由：后台 worker 被 monkeypatch（单测不触发真实 Claude/评标）。
worker 转发逻辑单独用 mock 的 run_command_json 验证。
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.common.agent_bridge import AgentRunMeta
from server.routes.upload_helpers import tenant_submission_root
from server.stores.tender_task_store import get_tender_task_admin, upsert_tender_task

_TOKEN = "test-fake-token-acme-tender"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
EVAL_SCHEMA = "common/audit-result.schema.json"
_CASE_ROOT = tenant_submission_root("acme")  # 测试租户提交子树根（F2 隔离边界）


@pytest.fixture
def client(monkeypatch):
    """TestClient with patched tenant key; 后台调度默认 no-op（不跑真实评标）。"""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    return TestClient(api_module.app)


def _make_dir_case(name: str) -> Path:
    case = _CASE_ROOT / name
    case.mkdir(parents=True, exist_ok=True)
    (case / "bid.txt").write_text("投标文件内容", encoding="utf-8")
    return case


def _submit_directory(client: TestClient, case: Path) -> str:
    resp = client.post(
        "/tender/evaluate",
        json={"mode": "directory", "directory_path": str(case)},
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["request_id"]


def test_submit_directory_returns_accepted(client):
    case = _make_dir_case("test-tender-route-accept")
    try:
        resp = client.post(
            "/tender/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["mode"] == "directory"
        assert body["request_id"]
        assert body["task_status_url"] == f"/tender/tasks/{body['request_id']}"
        record = get_tender_task_admin(body["request_id"])
        assert record is not None and record["status"] == "accepted"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_query_task_status(client):
    case = _make_dir_case("test-tender-route-query")
    try:
        request_id = _submit_directory(client, case)
        resp = client.get(f"/tender/tasks/{request_id}", headers=_AUTH)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_task_not_found_returns_404(client):
    resp = client.get("/tender/tasks/nonexistent-rid", headers=_AUTH)
    assert resp.status_code == 404


def test_result_not_completed_returns_409(client):
    case = _make_dir_case("test-tender-route-409")
    try:
        request_id = _submit_directory(client, case)
        resp = client.get(f"/tender/tasks/{request_id}/result", headers=_AUTH)
        assert resp.status_code == 409
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_result_completed_returns_payload(client, monkeypatch):
    case = _make_dir_case("test-tender-route-result")
    try:
        request_id = _submit_directory(client, case)
        upsert_tender_task(
            {
                "request_id": request_id,
                "status": "completed",
                "progress_message": "评标完成",
                "finished_at": "2026-06-19T00:00:00+00:00",
                "updated_at": "2026-06-19T00:00:00+00:00",
            }
        )
        monkeypatch.setattr(
            "server.routes.tender.get_result_payload_by_request_id",
            lambda request_id, tenant: {
                "response": {"verdict": "manual_review", "summary": "需要人工复核"}
            },
        )
        resp = client.get(f"/tender/tasks/{request_id}/result", headers=_AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["verdict"] == "manual_review"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_submit_requires_auth(client):
    case = _make_dir_case("test-tender-route-auth")
    try:
        resp = client.post(
            "/tender/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
        )
        assert resp.status_code == 401
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_directory_outside_root_rejected(client):
    resp = client.post(
        "/tender/evaluate",
        json={"mode": "directory", "directory_path": "/etc"},
        headers=_AUTH,
    )
    assert resp.status_code == 400


def test_evaluate_directory_cross_tenant_rejected(client):
    # round4 F2 / approach b 核心：acme 不能 directory-读其他租户的提交子树。
    other = tenant_submission_root("other-tenant") / "case"
    other.mkdir(parents=True, exist_ok=True)
    (other / "bid.txt").write_text("OTHER TENANT BID", encoding="utf-8")
    try:
        resp = client.post(
            "/tender/evaluate",
            json={"mode": "directory", "directory_path": str(other)},
            headers=_AUTH,
        )
        assert resp.status_code == 400  # 跨租户子树被拒
    finally:
        shutil.rmtree(other, ignore_errors=True)


def test_unsupported_content_type(client):
    resp = client.post(
        "/tender/evaluate",
        content=b"raw payload",
        headers={**_AUTH, "Content-Type": "text/plain"},
    )
    assert resp.status_code == 415


def test_worker_forwards_to_evaluate_bid_and_persists(monkeypatch):
    import server.routes.tender_worker as worker

    calls: dict = {}

    async def fake_json(command_name, *arguments, schema_name, **opts):
        calls["command_name"] = command_name
        calls["arguments"] = arguments
        calls["schema_name"] = schema_name
        calls["opts"] = opts
        meta = AgentRunMeta(
            request_id=opts["request_id"],
            conversation_id="conv-tender",
            claude_session_id="sess-tender",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=schema_name,
            log_file="logs/service/tender.log",
            result_file="logs/service/tender-result.json",
            result_subtype="success",
            cost_usd=0.0,
            finished_at=None,
        )
        return {"verdict": "manual_review", "claim_id": "T-1"}, meta

    monkeypatch.setattr(worker, "run_command_json", fake_json)

    request_id = "test-tender-worker-rid"
    asyncio.run(
        worker.execute_tender_evaluation_task(
            request_id=request_id,
            tenant="acme",
            directory_path=str(_CASE_ROOT),
            source_mode="directory",
        )
    )

    assert calls["command_name"] == "tender-evaluate"
    assert calls["schema_name"] == EVAL_SCHEMA
    assert calls["arguments"] == (str(_CASE_ROOT),)
    assert calls["opts"]["request_id"] == request_id
    assert calls["opts"]["tenant"] == "acme"
    record = get_tender_task_admin(request_id)
    assert record is not None and record["status"] == "completed"
    assert record["result_file"] == "logs/service/tender-result.json"
    assert record["claim_id"] == "T-1"


# ── 任务列表 / retry / delete / 准入闸（本 sprint 补齐，对齐 audit 三件套）────────


def test_list_tasks_returns_submitted(client):
    case = _make_dir_case("test-tender-list")
    try:
        rid = _submit_directory(client, case)
        resp = client.get("/tender/tasks", headers=_AUTH)
        assert resp.status_code == 200, resp.text
        assert rid in [t["request_id"] for t in resp.json()]
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_list_tasks_filter_by_status(client):
    case = _make_dir_case("test-tender-list-filter")
    try:
        rid = _submit_directory(client, case)
        accepted = client.get("/tender/tasks?status=accepted", headers=_AUTH).json()
        assert rid in [t["request_id"] for t in accepted]
        completed = client.get("/tender/tasks?status=completed", headers=_AUTH).json()
        assert rid not in [t["request_id"] for t in completed]
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_list_requires_auth(client):
    assert client.get("/tender/tasks").status_code == 401


def test_retry_idle_task_reschedules(client):
    case = _make_dir_case("test-tender-retry")
    try:
        rid = _submit_directory(client, case)  # accepted
        resp = client.post(f"/tender/tasks/{rid}/retry", headers=_AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "running"  # 原子转移占位
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_retry_running_task_returns_409(client):
    case = _make_dir_case("test-tender-retry-running")
    try:
        rid = _submit_directory(client, case)
        upsert_tender_task(
            {"request_id": rid, "status": "running", "updated_at": "2026-06-19T00:00:00+00:00"}
        )
        resp = client.post(f"/tender/tasks/{rid}/retry", headers=_AUTH)
        assert resp.status_code == 409  # 正在跑，不可重试（原子守卫）
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_retry_unknown_returns_404(client):
    assert client.post("/tender/tasks/nope-rid/retry", headers=_AUTH).status_code == 404


def test_delete_idle_task_removes_it(client):
    case = _make_dir_case("test-tender-delete")
    try:
        rid = _submit_directory(client, case)
        resp = client.delete(f"/tender/tasks/{rid}", headers=_AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "deleted"
        assert client.get(f"/tender/tasks/{rid}", headers=_AUTH).status_code == 404
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_delete_running_task_returns_409(client):
    case = _make_dir_case("test-tender-delete-running")
    try:
        rid = _submit_directory(client, case)
        upsert_tender_task(
            {"request_id": rid, "status": "running", "updated_at": "2026-06-19T00:00:00+00:00"}
        )
        resp = client.delete(f"/tender/tasks/{rid}", headers=_AUTH)
        assert resp.status_code == 409  # running 删不动（与并发 retry 竞态守护）
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_delete_unknown_returns_404(client):
    assert client.delete("/tender/tasks/nope-rid", headers=_AUTH).status_code == 404


def test_evaluate_queue_full_returns_503(client, monkeypatch):
    # round4 F5 准入闸：在途任务满 → 503，不再无界接单。
    monkeypatch.setattr("server.routes.tender.admission_available", lambda: False)
    case = _make_dir_case("test-tender-503")
    try:
        resp = client.post(
            "/tender/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 503
    finally:
        shutil.rmtree(case, ignore_errors=True)


# ── 招标项目资源（数据模型优化：多投标人追加 / 按招标查看 / 结果回看）──────────


def _create_project(client: TestClient, tender_no: str | None = None, **kw) -> dict:
    resp = client.post("/tender/projects", json={"tender_no": tender_no, **kw}, headers=_AUTH)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_create_project_idempotent(client):
    # get-or-create 幂等(codex P1.2)：同 tenant+tender_no 两次建 → 同一 project_id。
    tn = f"R-{uuid.uuid4().hex[:8]}"
    p1 = _create_project(client, tender_no=tn, title="烛照标段一", method="综合评估法")
    p2 = _create_project(client, tender_no=tn, title="重复提交")
    assert p1["project_id"] == p2["project_id"]
    assert p1["status"] == "doing" and p1["title"] == "烛照标段一"


def test_list_projects(client):
    p = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")
    rows = client.get("/tender/projects", headers=_AUTH).json()
    assert p["project_id"] in [x["project_id"] for x in rows]


def test_project_detail_not_found(client):
    assert client.get("/tender/projects/nope-pid", headers=_AUTH).status_code == 404


def test_evaluate_under_project_appears_in_roster(client):
    case = _make_dir_case("test-proj-eval")
    try:
        pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
        resp = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 200, resp.text
        rid = resp.json()["request_id"]
        detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
        assert detail["bidder_count"] == 1
        assert rid in [b["request_id"] for b in detail["bids"]]
        assert detail["bids"][0]["status"] == "accepted"  # 在途(schedule 被 mock no-op)
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_evaluate_unknown_project_404(client):
    case = _make_dir_case("test-proj-404")
    try:
        resp = client.post(
            "/tender/projects/nope-pid/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 404
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_results_recall_survives_task_deletion(client):
    """codex P1.1 回归：删任务后该招标下已完成结论仍可回看(走 results.project_id)。"""
    from server.stores.result_store import archive_result_payload

    case = _make_dir_case("test-proj-recall")
    try:
        pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        # 模拟评标完成 + 归档结论(带 project_id)
        upsert_tender_task(
            {
                "request_id": rid,
                "status": "completed",
                "claim_id": "BID-X",
                "finished_at": "2026-06-20T00:00:00+00:00",
                "updated_at": "2026-06-20T00:00:00+00:00",
            }
        )
        archive_result_payload(
            request_id=rid,
            tenant="acme",
            project_id=pid,
            conversation_id="c1",
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=EVAL_SCHEMA,
            request_mode="structured",
            result_subtype="success",
            cost_usd=0.0,
            prompt_preview="x",
            response={"verdict": "manual_review", "claim_id": "BID-X"},
        )
        # 删任务后：任务没了，但结论回看 + 名册仍在(durable)
        assert client.delete(f"/tender/tasks/{rid}", headers=_AUTH).status_code == 200
        assert client.get(f"/tender/tasks/{rid}", headers=_AUTH).status_code == 404
        results = client.get(f"/tender/projects/{pid}/results", headers=_AUTH).json()
        assert rid in [r["request_id"] for r in results]
        assert results[0]["verdict"] == "manual_review"
        detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
        assert "BID-X" in [b["claim_id"] for b in detail["bids"]]
    finally:
        shutil.rmtree(case, ignore_errors=True)
