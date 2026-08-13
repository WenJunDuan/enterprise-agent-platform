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
from server.routes.upload_helpers import UNBOUND_PROJECT, tenant_submission_root
from server.stores.tender_task_store import get_tender_task_admin, upsert_tender_task
from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME as EVAL_SCHEMA

_TOKEN = "test-fake-token-acme-tender"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
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
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    return TestClient(api_module.app)


def _make_dir_case(name: str, project_id: str = UNBOUND_PROJECT) -> Path:
    """建 tender 案件目录：``<tenant>/tender/<project_id>/<name>``（新存储结构）。

    legacy /tender/evaluate 用默认 ``unbound`` 段；/projects/{id}/evaluate 传真实 project_id。
    """
    case = _CASE_ROOT / "tender" / project_id / name
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
            "server.routes.tender.tasks.get_result_payload_by_request_id",
            lambda request_id, tenant: {
                "response": {"verdict": "manual_review", "summary": "需要人工复核"}
            },
        )
        resp = client.get(f"/tender/tasks/{request_id}/result", headers=_AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["verdict"] == "manual_review"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_update_tender_progress_only_running(client):
    # 思考流式：update_tender_progress 只更 running 行的 progress_message；completed 不被覆盖。
    from server.stores.tender_task_store import (
        get_tender_task_admin,
        update_tender_progress,
        upsert_tender_task,
    )

    upsert_tender_task(
        {
            "request_id": "tp-progress-run",
            "tenant": "acme",
            "status": "running",
            "mode": "directory",
            "source_mode": "directory",
            "case_path": "/tmp/case",
            "progress_message": "评标 Agent 正在运行中",
        }
    )
    update_tender_progress("tp-progress-run", "S1 正在定位评标办法…")
    assert get_tender_task_admin("tp-progress-run")["progress_message"] == "S1 正在定位评标办法…"

    upsert_tender_task(
        {
            "request_id": "tp-progress-done",
            "tenant": "acme",
            "status": "completed",
            "mode": "directory",
            "source_mode": "directory",
            "case_path": "/tmp/case",
            "progress_message": "评标完成",
        }
    )
    update_tender_progress("tp-progress-done", "不应覆盖已完成")
    assert get_tender_task_admin("tp-progress-done")["progress_message"] == "评标完成"


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
    """worker 转发逻辑：execute_tender_evaluation_task（调度壳，留 tender_worker）→
    run_tender_evaluation（评标核心，D1 T2 下沉 server.tender.runner）→ run_command_json。
    调度壳 monkeypatch 在 worker 模块，核心的 run_command_json 需 monkeypatch 在其下沉后的
    新家（server.tender.runner），否则真实网关调用会被触发（D1 T2 接缝）。
    """
    from server.tender import runner, worker

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

    monkeypatch.setattr(runner, "run_command_json", fake_json)

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
    monkeypatch.setattr("server.routes.tender.tasks.admission_available", lambda: False)
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
    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-eval", pid)
    try:
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

    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-recall", pid)
    try:
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


def test_project_result_detail_survives_task_deletion(client):
    """cc-impl-review P1 修复：删任务后仍能取该招标下**完整**结论（不依赖 tender_tasks）。"""
    from server.stores.result_store import archive_result_payload

    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-detail-recall", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
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
            response={"verdict": "manual_review", "claim_id": "BID-Y", "extracted_data": {"scoring": []}},
        )
        assert client.delete(f"/tender/tasks/{rid}", headers=_AUTH).status_code == 200
        # 旧 /tasks/{id}/result 删任务后 404（已知）；新 project 详情端点仍取得完整结论。
        assert client.get(f"/tender/tasks/{rid}/result", headers=_AUTH).status_code == 404
        detail = client.get(f"/tender/projects/{pid}/results/{rid}", headers=_AUTH)
        assert detail.status_code == 200, detail.text
        assert detail.json()["verdict"] == "manual_review"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_cross_tenant_project_denied(client):
    """跨租户隔离：acme 不能访问其他租户的招标项目（404）。"""
    from server.stores.tender_project_store import get_or_create_project

    other = get_or_create_project(tenant="other-co", tender_no=f"R-{uuid.uuid4().hex[:8]}")
    pid = other["project_id"]
    assert client.get(f"/tender/projects/{pid}", headers=_AUTH).status_code == 404
    assert client.get(f"/tender/projects/{pid}/results", headers=_AUTH).status_code == 404


def test_delete_project_cascades_all(client):
    """删项目级联清掉投标任务 + 结论 + 项目自身；删后 detail 404、任务/结论均不可达。"""
    from server.stores.result_store import (
        archive_result_payload,
        get_result_payload_by_request_id,
    )

    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-del-cascade", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        upsert_tender_task(
            {"request_id": rid, "status": "completed", "updated_at": "2026-06-20T00:00:00+00:00"}
        )
        archive_result_payload(
            request_id=rid, tenant="acme", project_id=pid, conversation_id="c1",
            claude_session_id=None, resume_session_id=None, fork_from_session_id=None,
            schema_name=EVAL_SCHEMA, request_mode="structured", result_subtype="success",
            cost_usd=0.0, prompt_preview="x",
            response={"verdict": "approved", "claim_id": "BID-D"},
        )
        resp = client.delete(f"/tender/projects/{pid}", headers=_AUTH)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["deleted"]["tender_projects"] == 1
        assert body["deleted"]["tender_tasks"] >= 1
        assert body["deleted"]["results"] >= 1
        # 级联确认：项目 404、任务没了、结论没了
        assert client.get(f"/tender/projects/{pid}", headers=_AUTH).status_code == 404
        assert get_tender_task_admin(rid) is None
        assert get_result_payload_by_request_id(request_id=rid, tenant="acme") is None
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_delete_project_with_running_bid_returns_409(client):
    """项目下有 running 投标任务 → 删项目回 409（防与执行中 worker 竞态），项目保留。"""
    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-del-running", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        upsert_tender_task(
            {"request_id": rid, "status": "running", "updated_at": "2026-06-20T00:00:00+00:00"}
        )
        resp = client.delete(f"/tender/projects/{pid}", headers=_AUTH)
        assert resp.status_code == 409
        assert client.get(f"/tender/projects/{pid}", headers=_AUTH).status_code == 200
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_delete_project_with_accepted_bid_returns_409(client):
    """codex P1-1：项目下有 accepted（已受理未排程）投标任务 → 删项目回 409（防孤儿竞态）。"""
    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-del-accepted", pid)
    try:
        # /evaluate 提交后任务即 accepted（schedule 被 mock no-op，不进 running/completed）。
        client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        resp = client.delete(f"/tender/projects/{pid}", headers=_AUTH)
        assert resp.status_code == 409  # accepted 也算在途（非终态）
        assert client.get(f"/tender/projects/{pid}", headers=_AUTH).status_code == 200
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_delete_project_with_active_compare_returns_409(client, monkeypatch):
    """codex P1-2：项目下有在途价格横比 → 删项目回 409（复用 has_active_compare 守卫）。"""
    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    monkeypatch.setattr("server.routes.tender.projects.has_active_compare", lambda tenant, project_id: True)
    resp = client.delete(f"/tender/projects/{pid}", headers=_AUTH)
    assert resp.status_code == 409
    assert client.get(f"/tender/projects/{pid}", headers=_AUTH).status_code == 200


def test_delete_project_unknown_and_cross_tenant_404(client):
    """删未知项目 404；跨租户项目对 acme 不可见亦不可删（404）。"""
    from server.stores.tender_project_store import get_or_create_project

    assert client.delete("/tender/projects/nope-pid", headers=_AUTH).status_code == 404
    other = get_or_create_project(tenant="other-co", tender_no=f"R-{uuid.uuid4().hex[:8]}")
    assert (
        client.delete(f"/tender/projects/{other['project_id']}", headers=_AUTH).status_code == 404
    )


def test_worker_threads_project_id(monkeypatch):
    """codex P1.3 透传链：worker 把 project_id 传给 run_command_json（端到端透传未断）。

    D1 T2 接缝：run_command_json 现只在 server.tender.runner 内被调用（评标核心下沉），
    调度壳仍在 tender_worker——两个模块各 monkeypatch 各自需要的一半。
    """
    from server.tender import runner, worker

    calls: dict = {}

    async def fake_json(command_name, *arguments, schema_name, **opts):
        calls["opts"] = opts
        meta = AgentRunMeta(
            request_id=opts["request_id"],
            conversation_id="c",
            claude_session_id="s",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=schema_name,
            log_file="l",
            result_file="r",
            result_subtype="success",
            cost_usd=0.0,
            finished_at=None,
        )
        return {"verdict": "manual_review", "claim_id": "T-2"}, meta

    monkeypatch.setattr(runner, "run_command_json", fake_json)
    asyncio.run(
        worker.execute_tender_evaluation_task(
            request_id="rid-pid-thread",
            tenant="acme",
            directory_path=str(_CASE_ROOT),
            source_mode="directory",
            project_id="tp-thread-test",
        )
    )
    assert calls["opts"]["project_id"] == "tp-thread-test"


def test_evaluate_and_retry_pass_project_id_to_schedule(client, monkeypatch):
    """codex P1.1 回归：/projects/{id}/evaluate 与 retry 都把 project_id 传给 schedule
    （retry 丢 project_id 会让 worker 以 None 归档，覆盖原 project-scoped 结论）。"""
    calls: list = []
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task",
        lambda **kw: calls.append(kw),
    )
    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-schedule-spy", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        assert calls[-1]["project_id"] == pid  # evaluate 透传 project_id
        client.post(f"/tender/tasks/{rid}/retry", headers=_AUTH)
        assert calls[-1]["project_id"] == pid  # retry 保留 project_id（codex P1.1）
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_evaluate_upload_passes_prewarm_bid_id_to_schedule(client, monkeypatch):
    """R6-R2 回归：evaluate(mode=upload) 解析 form_json.bid_id → 透传 schedule(bid_id=...)，
    供 worker 复用预热 OCR、免重 OCR。"""
    import json as _json

    calls: list = []
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task",
        lambda **kw: calls.append(kw),
    )
    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    resp = client.post(
        f"/tender/projects/{pid}/evaluate",
        data={
            "mode": "upload",
            "form_json": _json.dumps({"bidder_name": "X", "bid_id": "bd-prewarm123"}),
        },
        files=[("files", ("招标.pdf", b"%PDF-fake", "application/pdf"))],
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert calls[-1]["bid_id"] == "bd-prewarm123"  # 预热 bid_id 透传 worker


def test_evaluate_upload_without_bid_id_passes_none(client, monkeypatch):
    """无 bid_id → schedule 收 None（向后兼容，走原 inline OCR 路径）。"""
    import json as _json

    calls: list = []
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task",
        lambda **kw: calls.append(kw),
    )
    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    client.post(
        f"/tender/projects/{pid}/evaluate",
        data={"mode": "upload", "form_json": _json.dumps({"bidder_name": "X"})},
        files=[("files", ("招标.pdf", b"%PDF-1.4 fake", "application/pdf"))],
        headers=_AUTH,
    )
    assert calls[-1]["bid_id"] is None


def test_create_project_blank_tender_no_anonymous(client):
    """codex P1.2 回归：空 / 空白 tender_no 当匿名处理，重复提交不 500（各自新建）。"""
    p1 = client.post("/tender/projects", json={"tender_no": "", "title": "匿名1"}, headers=_AUTH)
    p2 = client.post("/tender/projects", json={"tender_no": "  ", "title": "匿名2"}, headers=_AUTH)
    assert p1.status_code == 200 and p2.status_code == 200, (p1.text, p2.text)
    assert p1.json()["project_id"] != p2.json()["project_id"]  # 匿名允许多条
    assert p1.json()["tender_no"] is None  # 空串归一为 None


# ── X2: 案卷头信息（投标单位名称/项目名）留存与展示 ────────────────────────────


def test_results_endpoint_exposes_agent_bidder_name(client):
    """GET /projects/{id}/results 的 bidder_name = agent 从结论识别的名称（results 行拍平值）。"""
    from server.stores.result_store import archive_result_payload

    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-bidder-name", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        archive_result_payload(
            request_id=rid,
            tenant="acme",
            project_id=pid,
            bid_id="bd-agent-1",
            conversation_id="c1",
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=EVAL_SCHEMA,
            request_mode="structured",
            result_subtype="success",
            cost_usd=0.0,
            prompt_preview="x",
            response={
                "verdict": "approved",
                "claim_id": "BID-AGENT-1",
                "extracted_data": {"bidder_info": {"bidder_name": "AI识别建设有限公司"}},
            },
        )
        results = client.get(f"/tender/projects/{pid}/results", headers=_AUTH).json()
        row = next(r for r in results if r["request_id"] == rid)
        assert row["bidder_name"] == "AI识别建设有限公司"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_roster_hand_filled_bidder_name_overrides_agent_name(client):
    """手填优先端到端：roster 的 bidder_name 手填非空时以手填为准（非默认值路径断言）。"""
    from server.stores.result_store import archive_result_payload
    from server.stores.tender_doc_store import upsert_bid_doc

    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-bidder-hand", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        archive_result_payload(
            request_id=rid,
            tenant="acme",
            project_id=pid,
            bid_id="bd-hand-1",
            conversation_id="c1",
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=EVAL_SCHEMA,
            request_mode="structured",
            result_subtype="success",
            cost_usd=0.0,
            prompt_preview="x",
            response={
                "verdict": "approved",
                "claim_id": "BID-HAND-1",
                "extracted_data": {"bidder_info": {"bidder_name": "AI识别的公司名"}},
            },
        )
        upsert_bid_doc(
            project_id=pid,
            bid_id="bd-hand-1",
            tenant="acme",
            bidder_name="用户手填公司名",
            bid_files="[]",
        )
        detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
        bid = next(b for b in detail["bids"] if b["request_id"] == rid)
        assert bid["bidder_name"] == "用户手填公司名"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_roster_falls_back_to_agent_name_without_hand_fill(client):
    """无手填时 roster 回退到 agent 识别名称（非空转分支的另一半：agent baseline 可达）。"""
    from server.stores.result_store import archive_result_payload

    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-bidder-noHand", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        archive_result_payload(
            request_id=rid,
            tenant="acme",
            project_id=pid,
            bid_id="bd-nohand-1",
            conversation_id="c1",
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=EVAL_SCHEMA,
            request_mode="structured",
            result_subtype="success",
            cost_usd=0.0,
            prompt_preview="x",
            response={
                "verdict": "approved",
                "claim_id": "BID-NOHAND-1",
                "extracted_data": {"bidder_info": {"bidder_name": "AI识别公司无手填"}},
            },
        )
        detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
        bid = next(b for b in detail["bids"] if b["request_id"] == rid)
        assert bid["bidder_name"] == "AI识别公司无手填"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_roster_bid_id_none_degrades_without_crash(client):
    """退化路径：结论 bid_id=None（非 prewarm 直提场景）时 roster 正常退化，不崩，bidder_name 为空。"""
    from server.stores.result_store import archive_result_payload

    pid = _create_project(client, tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    case = _make_dir_case("test-proj-bidder-noBidId", pid)
    try:
        rid = client.post(
            f"/tender/projects/{pid}/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        ).json()["request_id"]
        archive_result_payload(
            request_id=rid,
            tenant="acme",
            project_id=pid,
            bid_id=None,
            conversation_id="c1",
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=EVAL_SCHEMA,
            request_mode="structured",
            result_subtype="success",
            cost_usd=0.0,
            prompt_preview="x",
            response={"verdict": "approved", "claim_id": "BID-NOBID-1"},
        )
        detail = client.get(f"/tender/projects/{pid}", headers=_AUTH)
        assert detail.status_code == 200, detail.text
        bid = next(b for b in detail.json()["bids"] if b["request_id"] == rid)
        assert bid["bidder_name"] is None
    finally:
        shutil.rmtree(case, ignore_errors=True)
