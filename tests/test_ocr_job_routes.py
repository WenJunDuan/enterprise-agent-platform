"""D9 streaming-ocr T2：jobs 端点集成测试（POST /ocr/jobs, GET /ocr/jobs/{request_id}）。

用 native 文本文件（route=native，无需 OCR 引擎）驱动真实识别流水线。提交经真实 HTTP
路由（落盘 + TaskStore upsert queued），但 fastapi TestClient 的每次请求各自起停一个
event loop —— 提交请求返回后其 ``asyncio.create_task`` 调度的后台 job 会随该请求的 loop
一起被销毁，无法跨请求异步跑完（非本功能缺陷，是 TestClient 的已知限制）。故这里把
``schedule_ocr_job`` monkeypatch 成 no-op，在提交后用与生产同一份 ``execute_ocr_job``
直接跑到底，再用 GET 校验结果——route→store→pipeline 全链路仍是真实代码，只是去掉了
"真异步后台调度"这一层测试基础设施噪音。
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from server.routes import ocr_job_worker
from server.stores.ocr_job_store import upsert_ocr_job

_TOKEN = "test-fake-token-acme-ocr-jobs"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_OTHER_TOKEN = "test-fake-token-other-ocr-jobs"
_OTHER_AUTH = {"Authorization": f"Bearer {_OTHER_TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        "server.routes.deps.TENANT_KEYS", {"acme": _TOKEN, "other-tenant": _OTHER_TOKEN}
    )
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    # 见模块 docstring：不让 submit 端点真调度后台 task，改由测试显式跑同一份 worker 函数。
    monkeypatch.setattr("server.routes.ocr_jobs.schedule_ocr_job", lambda **kwargs: None)
    return TestClient(api_module.app)


def _run_job_to_completion(request_id: str, tenant: str = "acme") -> None:
    asyncio.run(ocr_job_worker.execute_ocr_job(request_id=request_id, tenant=tenant))


def test_jobs_submit_returns_202_with_request_id_and_status_url(client):
    files = [("files", ("note.txt", "差旅费 880 元".encode(), "text/plain"))]
    resp = client.post("/ocr/jobs", files=files, headers=_AUTH)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["request_id"]
    assert body["status"] == "queued"
    assert body["task_status_url"] == f"/ocr/jobs/{body['request_id']}"


def test_jobs_submit_requires_auth(client):
    files = [("files", ("a.txt", b"x", "text/plain"))]
    resp = client.post("/ocr/jobs", files=files)
    assert resp.status_code == 401


def test_jobs_submit_empty_upload_rejected(client):
    resp = client.post("/ocr/jobs", files=[("other", ("x.txt", b"x", "text/plain"))], headers=_AUTH)
    assert resp.status_code == 400


def test_jobs_submit_unsupported_content_type(client):
    resp = client.post(
        "/ocr/jobs", content=b"raw payload", headers={**_AUTH, "Content-Type": "text/plain"}
    )
    assert resp.status_code == 415


def test_jobs_status_before_worker_runs_is_queued_with_no_results(client):
    files = [("files", ("a.txt", b"content", "text/plain"))]
    submit = client.post("/ocr/jobs", files=files, headers=_AUTH)
    request_id = submit.json()["request_id"]

    resp = client.get(f"/ocr/jobs/{request_id}", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["results"] == []
    assert body["progress"] is None  # progress_message 尚未写入（queued 态）


def test_jobs_get_after_worker_completes_returns_progressive_results(client):
    files = [
        ("files", ("a.txt", "第一份文件内容".encode(), "text/plain")),
        ("files", ("b.txt", "第二份文件内容".encode(), "text/plain")),
    ]
    submit = client.post("/ocr/jobs", files=files, headers=_AUTH)
    assert submit.status_code == 202
    request_id = submit.json()["request_id"]

    _run_job_to_completion(request_id)

    resp = client.get(f"/ocr/jobs/{request_id}", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["progress"] == {"done": 2, "total": 2}
    assert len(body["results"]) == 2
    names = {unit["file"].split("/")[-1] for unit in body["results"]}
    assert names == {"a.txt", "b.txt"}
    assert all(unit["status"] == "ok" for unit in body["results"])


def test_jobs_unknown_request_id_returns_404(client):
    resp = client.get("/ocr/jobs/does-not-exist", headers=_AUTH)
    assert resp.status_code == 404


def test_jobs_cross_tenant_request_id_returns_404(client):
    files = [("files", ("a.txt", b"content", "text/plain"))]
    submit = client.post("/ocr/jobs", files=files, headers=_AUTH)
    request_id = submit.json()["request_id"]
    _run_job_to_completion(request_id)

    resp = client.get(f"/ocr/jobs/{request_id}", headers=_OTHER_AUTH)
    assert resp.status_code == 404  # F4：不泄漏存在性


def test_jobs_malformed_progress_message_does_not_500(client):
    files = [("files", ("a.txt", b"content", "text/plain"))]
    submit = client.post("/ocr/jobs", files=files, headers=_AUTH)
    request_id = submit.json()["request_id"]
    _run_job_to_completion(request_id)

    # 直接污染 progress_message 为非法格式（G2①契约之外），GET 端应容错而非 500。
    upsert_ocr_job({"request_id": request_id, "status": "completed", "progress_message": "not-json"})
    resp = client.get(f"/ocr/jobs/{request_id}", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["progress"] is None


def test_jobs_progress_message_wrong_shape_does_not_500(client):
    files = [("files", ("a.txt", b"content", "text/plain"))]
    submit = client.post("/ocr/jobs", files=files, headers=_AUTH)
    request_id = submit.json()["request_id"]
    _run_job_to_completion(request_id)

    upsert_ocr_job(
        {
            "request_id": request_id,
            "status": "completed",
            "progress_message": json.dumps(["not", "a", "dict"]),
        }
    )
    resp = client.get(f"/ocr/jobs/{request_id}", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["progress"] is None


def test_jobs_zero_pending_files_case_completes_with_empty_results(client, monkeypatch):
    # F4 边界：job worker 起点若判定 0 待处理文件（不可能经真实 multipart 提交触发，
    # materialize_ocr_upload 要求至少一个文件）——直接走 worker 单测覆盖（见
    # tests/test_ocr_job_worker.py::test_execute_ocr_job_zero_files_completes_immediately）；
    # 此处只回归 GET 端在 0 单元 completed 态下的响应形状不因 results 为空而出错。
    files = [("files", ("a.txt", b"content", "text/plain"))]
    submit = client.post("/ocr/jobs", files=files, headers=_AUTH)
    request_id = submit.json()["request_id"]
    upsert_ocr_job(
        {
            "request_id": request_id,
            "status": "completed",
            "progress_message": json.dumps({"done": 0, "total": 0}),
        }
    )
    resp = client.get(f"/ocr/jobs/{request_id}", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["progress"] == {"done": 0, "total": 0}
