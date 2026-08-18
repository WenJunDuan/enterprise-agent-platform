"""P0.4 · criteria 未就绪时服务端拒绝评标，而不是收下一个注定作废的任务。

线上实测：评标可在 criteria 抽取仍 ``running`` 时启动（相差 24 秒）。后果链条是确定的——
证据层（S3）只在有 criteria 时接管 → 跳过 → 整份底稿退回全量注入 → 超预算被截断 →
截断即转人工。**整单作废，而用户已经等完了全程**。

``doc_layer.wait_doc_layer_ready`` 早就多等了一档 criteria，但等待上限到点后仍**放行降级**，
于是那条注定作废的路照走不误。本项把归宿从"放行"改成"提交时就拒"：

- 拒在 ``_submit_bid_evaluation`` 的最前面 → **不建任务、不落上传文件、不烧一个 token**；
- 消息必须可执行，且"还在解析"（稍后重试）与"解析不会有结果了"（重新上传）要分开说——
  这两种情况用户要做的事完全不同。

``criteria_status=ready`` 时**行为逐字不变**：本闸只在项目确实有预热底稿记录时生效，
散单 / directory 模式 / 未上传招标文件的项目一律照旧放行（它们本来就不走证据层）。
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.routes.upload_helpers import tenant_submission_root
from server.stores.tender_doc_store import upsert_project_doc
from server.stores.tender_task_store import list_tender_tasks

_TOKEN = "test-fake-token-acme-gate"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_CASE_ROOT = tenant_submission_root("acme")


@pytest.fixture
def gate_client(monkeypatch):
    """TestClient + schedule 探针：任何被排程的评标都会留痕，便于断言"没烧 token"。"""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    scheduled: list[dict] = []
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task",
        lambda **kwargs: scheduled.append(kwargs),
    )
    return TestClient(api_module.app), scheduled


def _project(client: TestClient) -> str:
    resp = client.post(
        "/tender/projects", json={"tender_no": f"G-{uuid.uuid4().hex[:8]}"}, headers=_AUTH
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["project_id"]


def _prewarmed(project_id: str, criteria_status: str) -> None:
    """给项目挂一份预热底稿记录（评标会走证据层的那种项目）。"""
    upsert_project_doc(
        project_id=project_id,
        tenant="acme",
        tender_files='["招标.pdf"]',
        ocr_status="ready",
        ocr_text="招标文件底稿",
        criteria_status=criteria_status,
    )


def _case_dir(name: str, project_id: str) -> Path:
    case = _CASE_ROOT / "tender" / project_id / name
    case.mkdir(parents=True, exist_ok=True)
    (case / "bid.txt").write_text("投标文件内容", encoding="utf-8")
    return case


def _submit(client: TestClient, project_id: str, case: Path):
    return client.post(
        f"/tender/projects/{project_id}/evaluate",
        json={"mode": "directory", "directory_path": str(case)},
        headers=_AUTH,
    )


# ── 未就绪 → 4xx，且什么都没发生 ────────────────────────────────────────────


@pytest.mark.parametrize("status", ["pending", "running"])
def test_submit_is_rejected_while_criteria_is_still_being_parsed(gate_client, status):
    """AC：criteria ∈ {pending, running} → 4xx，不建任务、不烧 token。"""
    client, scheduled = gate_client
    pid = _project(client)
    _prewarmed(pid, status)
    case = _case_dir(f"gate-{status}", pid)
    try:
        resp = _submit(client, pid, case)

        assert 400 <= resp.status_code < 500, resp.text
        assert scheduled == [], "不得排程——那一单注定作废，烧的 token 全是白烧"
        assert list_tender_tasks("acme", limit=100) == [] or all(
            task.get("group_id") != pid for task in list_tender_tasks("acme", limit=100)
        ), "不得建任务：任务一旦落库，前端就会去轮询一个永远不会有结论的 request_id"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_still_parsing_message_tells_the_user_to_retry_shortly(gate_client):
    """还在解析 → 用户该做的是稍等再提交，不是重新上传。"""
    client, _ = gate_client
    pid = _project(client)
    _prewarmed(pid, "running")
    case = _case_dir("gate-running-msg", pid)
    try:
        detail = _submit(client, pid, case).json()["detail"]

        assert "评分标准" in detail
        assert "稍后" in detail or "稍候" in detail
        assert "重新上传" not in detail, "还在解析时叫人重传是把人往回赶"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_failed_criteria_is_rejected_with_reupload_guidance(gate_client):
    """AC：criteria_status=failed → 4xx 且消息含重新上传指引（等下去不会变好）。"""
    client, scheduled = gate_client
    pid = _project(client)
    _prewarmed(pid, "failed")
    case = _case_dir("gate-failed", pid)
    try:
        resp = _submit(client, pid, case)

        assert 400 <= resp.status_code < 500, resp.text
        assert scheduled == []
        assert "重新上传" in resp.json()["detail"]
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_stalled_extraction_is_rejected_with_reupload_guidance(gate_client, monkeypatch):
    """等待上限到点也不会有结果（心跳陈旧的僵尸 running）→ 与 failed 同一处置。

    这正是 ``doc_layer`` 那条 ``wait_cap_reached`` 分支此前放行降级的场景。
    """
    client, scheduled = gate_client
    monkeypatch.setenv("OCR_PREWARM_STALE_SEC", "0.001")  # 刚写的行也算陈旧
    pid = _project(client)
    _prewarmed(pid, "running")
    case = _case_dir("gate-stalled", pid)
    try:
        resp = _submit(client, pid, case)

        assert 400 <= resp.status_code < 500, resp.text
        assert scheduled == []
        assert "重新上传" in resp.json()["detail"]
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_rejection_happens_before_any_upload_is_materialized(gate_client):
    """multipart 提交同样在落盘之前就拒——否则拒了还是留下一坨没人清理的上传文件。"""
    import json as _json

    client, scheduled = gate_client
    pid = _project(client)
    _prewarmed(pid, "running")
    before = {p.name for p in (_CASE_ROOT / "tender" / pid).glob("*")} if (
        _CASE_ROOT / "tender" / pid
    ).is_dir() else set()

    resp = client.post(
        f"/tender/projects/{pid}/evaluate",
        data={"mode": "upload", "form_json": _json.dumps({"bidder_name": "甲方建设有限公司"})},
        files=[("files", ("投标.pdf", b"%PDF-1.4 fake", "application/pdf"))],
        headers=_AUTH,
    )

    assert 400 <= resp.status_code < 500, resp.text
    assert scheduled == []
    after = {p.name for p in (_CASE_ROOT / "tender" / pid).glob("*")} if (
        _CASE_ROOT / "tender" / pid
    ).is_dir() else set()
    assert after == before, "拒之前不得落盘上传文件"


# ── 就绪 / 无预热记录 → 行为逐字不变 ────────────────────────────────────────


def test_ready_criteria_submits_exactly_as_before(gate_client):
    """AC：criteria_status=ready → 行为与现状一致（这条闸只挡未就绪）。"""
    client, scheduled = gate_client
    pid = _project(client)
    _prewarmed(pid, "ready")
    case = _case_dir("gate-ready", pid)
    try:
        resp = _submit(client, pid, case)

        assert resp.status_code == 200, resp.text
        assert len(scheduled) == 1
        assert scheduled[0]["project_id"] == pid
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_project_without_prewarmed_docs_is_untouched(gate_client):
    """没有预热底稿记录的项目（directory / legacy 散单）本来就不走证据层，不得被误拒。"""
    client, scheduled = gate_client
    pid = _project(client)
    case = _case_dir("gate-nodocs", pid)
    try:
        assert _submit(client, pid, case).status_code == 200
        assert len(scheduled) == 1
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_legacy_unbound_evaluate_is_untouched(gate_client):
    """legacy ``/tender/evaluate``（无 project_id）没有招标层可查，必须原样放行。"""
    from server.routes.upload_helpers import UNBOUND_PROJECT

    client, scheduled = gate_client
    case = _case_dir("gate-legacy", UNBOUND_PROJECT)
    try:
        resp = client.post(
            "/tender/evaluate",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )

        assert resp.status_code == 200, resp.text
        assert len(scheduled) == 1
    finally:
        shutil.rmtree(case, ignore_errors=True)
