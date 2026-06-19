"""Integration tests for contract review routes (/contract/review, /contract/tasks/*).

镜像 test_tender_routes：后台 worker 被 monkeypatch（单测不触发真实 Claude）。
worker 转发 + 落库逻辑单独用 mock 的 run_command_json 验证。
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.common.agent_bridge import AgentRunMeta
from server.routes.upload_helpers import ALLOWED_DIRECTORY_ROOT
from server.stores.contract_store import get_contract_by_request_id_admin
from server.stores.contract_task_store import get_contract_task_admin, upsert_contract_task

_TOKEN = "test-fake-token-acme-contract"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
EVAL_SCHEMA = "common/audit-result.schema.json"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.contract.schedule_contract_review_task", lambda **kwargs: None
    )
    return TestClient(api_module.app)


def _make_dir_case(name: str) -> Path:
    case = ALLOWED_DIRECTORY_ROOT / name
    case.mkdir(parents=True, exist_ok=True)
    (case / "contract.txt").write_text("合同正文", encoding="utf-8")
    return case


def _submit(client: TestClient, case: Path) -> str:
    resp = client.post(
        "/contract/review",
        json={"mode": "directory", "directory_path": str(case)},
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["request_id"]


def test_submit_directory_returns_accepted(client):
    case = _make_dir_case("test-contract-route-accept")
    try:
        resp = client.post(
            "/contract/review",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["mode"] == "directory"
        assert body["task_status_url"] == f"/contract/tasks/{body['request_id']}"
        record = get_contract_task_admin(body["request_id"])
        assert record is not None and record["status"] == "accepted"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_query_task_and_result_lifecycle(client, monkeypatch):
    case = _make_dir_case("test-contract-route-life")
    try:
        request_id = _submit(client, case)
        assert client.get(f"/contract/tasks/{request_id}", headers=_AUTH).json()["status"] == "accepted"
        # 未完成 → 409
        assert client.get(f"/contract/tasks/{request_id}/result", headers=_AUTH).status_code == 409
        # 模拟完成
        upsert_contract_task(
            {
                "request_id": request_id,
                "status": "completed",
                "updated_at": "2026-06-19T00:00:00+00:00",
            }
        )
        monkeypatch.setattr(
            "server.routes.contract.get_result_payload_by_request_id",
            lambda request_id, tenant: {"response": {"verdict": "approved", "summary": "条款合规"}},
        )
        resp = client.get(f"/contract/tasks/{request_id}/result", headers=_AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["verdict"] == "approved"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_task_not_found_returns_404(client):
    assert client.get("/contract/tasks/nope", headers=_AUTH).status_code == 404


def test_submit_requires_auth(client):
    case = _make_dir_case("test-contract-route-auth")
    try:
        resp = client.post(
            "/contract/review", json={"mode": "directory", "directory_path": str(case)}
        )
        assert resp.status_code == 401
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_directory_outside_root_rejected(client):
    resp = client.post(
        "/contract/review", json={"mode": "directory", "directory_path": "/etc"}, headers=_AUTH
    )
    assert resp.status_code == 400


def test_unsupported_content_type(client):
    resp = client.post(
        "/contract/review", content=b"raw", headers={**_AUTH, "Content-Type": "text/plain"}
    )
    assert resp.status_code == 415


def test_worker_forwards_to_review_contract_and_persists(monkeypatch, tmp_path):
    import server.routes.contract_worker as worker

    case = tmp_path / "contract-case"
    case.mkdir()
    (case / "main.pdf").write_text("合同", encoding="utf-8")
    request_id = f"req-contract-{uuid.uuid4().hex}"
    calls: dict = {}

    async def fake_json(command_name, *arguments, schema_name, **opts):
        calls["command_name"] = command_name
        calls["arguments"] = arguments
        calls["schema_name"] = schema_name
        calls["opts"] = opts
        meta = AgentRunMeta(
            request_id=opts["request_id"],
            conversation_id="c",
            claude_session_id="s",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=schema_name,
            log_file="l",
            result_file="rf.json",
            result_subtype="success",
            cost_usd=0.0,
            finished_at=None,
        )
        payload = {"verdict": "approved", "extracted_data": {"contract": {"contract_meta": {"title": "采购合同"}}}}
        return payload, meta

    monkeypatch.setattr(worker, "run_command_json", fake_json)

    # 落库走真实 persist 但关掉文件 copy，避免测试往 data/contracts/ 累积真实目录。
    import server.stores.contract_store as contract_store_module

    def _persist_no_copy(payload, *, request_id, tenant, source_path):
        return contract_store_module.persist_contract_from_result(
            payload,
            request_id=request_id,
            tenant=tenant,
            source_path=source_path,
            copy_source=False,
        )

    monkeypatch.setattr(worker, "persist_contract_from_result", _persist_no_copy)

    asyncio.run(
        worker.execute_contract_review_task(
            request_id=request_id, tenant="acme", directory_path=str(case), source_mode="directory"
        )
    )

    assert calls["command_name"] == "review-contract"
    assert calls["arguments"] == (str(case),)
    assert calls["schema_name"] == EVAL_SCHEMA
    assert calls["opts"]["request_id"] == request_id
    assert calls["opts"]["tenant"] == "acme"
    # 任务完成
    record = get_contract_task_admin(request_id)
    assert record is not None and record["status"] == "completed"
    # 合同结构已落库（worker 复用 persist_contract_from_result）
    contract = get_contract_by_request_id_admin(request_id)
    assert contract is not None and contract["title"] == "采购合同"
