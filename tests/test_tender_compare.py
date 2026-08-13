"""Phase 2 价格横比：契约 + 端点生命周期（KD2）+ 自动触发 + codex P1.1/P1.2 污染回归。

判据与护栏的单测在 ``tests/test_tender_compare_input.py``（collect / 价格项 / 报价护栏）。
本文件锁定：
- ``GET /projects/{id}/compare`` **恒 200** 的状态机（none/pending/running/failed/ready + stale）；
- 失败态对前端可见且**脱敏**（无 stack trace / 无服务器路径）；
- 评标终态后由服务端**自动**入队横比（前端不在场也能出结果），并且不重复入队；
- compare 结果不进 ``results`` 表、不进投标人名册（codex P1.1/P1.2）。
"""

from __future__ import annotations

import json
import uuid

import jsonschema
import pytest
from fastapi.testclient import TestClient

from server.common.contract import load_output_schema
from server.routes.upload_helpers import tenant_submission_root
from server.stores.result_store import archive_result_payload
from server.stores.tender_compare_store import compute_criteria_hash
from server.stores.tender_compare_task_store import upsert_compare_task
from server.stores.tender_doc_store import upsert_project_doc
from server.stores.tender_project_store import get_or_create_project

_TOKEN = "test-fake-token-acme-compare"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_CASE_ROOT = tenant_submission_root("acme")
COMPARE_SCHEMA = "tender/compare-result.schema.json"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr("server.routes.tender.compare.schedule_compare_task", lambda **kw: None)
    return TestClient(api_module.app)


def _criteria(price_max: int | None = 40) -> dict:
    return {
        "source_ref": "招标文件.pdf 评标办法 p.18",
        "method": "综合评估法",
        "total_max": 100,
        "items": [
            {"item": "技术", "max": 60, "scoring_rule": "技术评分", "source_ref": "p.19",
             "tag": "scored"},
            {"item": "价格分", "max": price_max, "scoring_rule": "最低价/本价×40",
             "source_ref": "p.18", "tag": "requires_cross_bid_comparison",
             "score_mode": "formula"},
        ],
    }


def _seed_project_criteria(project_id: str, criteria: dict | None = None) -> dict:
    """给项目写权威 criteria（KD1：结论必须引用该版本才可比）。"""
    criteria = criteria if criteria is not None else _criteria()
    upsert_project_doc(
        project_id=project_id,
        tenant="acme",
        tender_files=json.dumps([f"{project_id}.pdf"], ensure_ascii=False),
        criteria=json.dumps(criteria, ensure_ascii=False),
    )
    return criteria


def _archive_bid(
    project_id: str,
    claim_id: str,
    amount: float,
    criteria: dict | None = None,
) -> str:
    """归档一份 completed 投标结论（带 project_id + bid_price + 权威版本 criteria_ref）。"""
    criteria = criteria if criteria is not None else _criteria()
    request_id = f"bid-{uuid.uuid4().hex[:8]}"
    archive_result_payload(
        request_id=request_id,
        tenant="acme",
        project_id=project_id,
        bid_id=f"bd-{claim_id}",
        conversation_id="c1",
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        request_mode="structured",
        result_subtype="success",
        cost_usd=0.0,
        prompt_preview="x",
        response={
            "verdict": "manual_review",
            "claim_id": claim_id,
            "extracted_data": {
                "criteria": criteria,
                "criteria_ref": {
                    "version": compute_criteria_hash(criteria),
                    "source": "project",
                },
                "bid_price": {"amount": amount, "currency": "CNY"},
                "scoring": [{"item": "技术", "max": 60, "score": 50, "status": "scored"}],
            },
        },
    )
    return request_id


def _new_project(client: TestClient, **kw) -> str:
    project_id = client.post(
        "/tender/projects",
        json={"tender_no": f"R-{uuid.uuid4().hex[:8]}", **kw},
        headers=_AUTH,
    ).json()["project_id"]
    _seed_project_criteria(project_id)
    return project_id


def _compare_task(
    project_id: str,
    status: str,
    *,
    error_detail: str | None = None,
    request_id: str | None = None,
) -> None:
    row = {
        "request_id": request_id or f"cmp-{uuid.uuid4().hex[:8]}",
        "tenant": "acme",
        "status": status,
        "mode": "compare",
        "source_mode": "compare",
        "case_path": "-",
        "group_id": project_id,
        "updated_at": "2026-08-11T00:00:00+00:00",
    }
    if error_detail is not None:
        row["error_detail"] = error_detail
    upsert_compare_task(row)


# ── 契约 ──────────────────────────────────────────────────────────────────────


def test_compare_schema_loads_and_validates():
    schema = load_output_schema(COMPARE_SCHEMA)
    assert schema["title"] == "tender_compare_result"
    jsonschema.validate(
        {
            "project_id": "tp-1",
            "method": "综合评估法",
            "bidders": [
                {"claim_id": "B1", "price_score": 40.0, "other_score": 50.0,
                 "total_score": 90.0, "rank": 1, "status": "scored", "note": "最优"}
            ],
            "recommended": None,
            "provisional": True,
            "warnings": ["非国有资金，供参考"],
            "explanation": "排名供参考",
            "policy_refs": ["tender_evalmethod_004"],
        },
        schema,
    )


def test_compare_prompt_declares_new_input_contract():
    """契约链：服务端判据字段改名后，命令 prompt 必须同步（0730 教训）。"""
    from pathlib import Path

    prompt = Path(".claude/commands/tender-compare.md").read_text(encoding="utf-8")
    for token in (
        "criteria_version",
        "comparable",
        "exclusion_reason",
        "insufficient_comparable_bidders",
        "price_max_unknown",
        "no_price_item",
        "bid_price_unit_mismatch",
    ):
        assert token in prompt, token
    assert "criteria_inconsistent" not in prompt  # 旧判据已废除


# ── 触发端点 ──────────────────────────────────────────────────────────────────


def test_trigger_compare_requires_two_bidders(client):
    project_id = _new_project(client)
    _archive_bid(project_id, "B1", 1000.0)
    resp = client.post(f"/tender/projects/{project_id}/compare", headers=_AUTH)
    assert resp.status_code == 400  # 不足 2 家


def test_trigger_compare_accepted(client):
    project_id = _new_project(client, funding_type="state_funded")
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    resp = client.post(f"/tender/projects/{project_id}/compare", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "compare"


def test_trigger_compare_unknown_project_404(client):
    assert client.post("/tender/projects/nope/compare", headers=_AUTH).status_code == 404


def test_trigger_compare_duplicate_returns_409(client):
    """cc C1：同 project 已有在途 compare → 409，防并发双击重复算。"""
    project_id = _new_project(client, funding_type="state_funded")
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    _compare_task(project_id, "running")
    resp = client.post(f"/tender/projects/{project_id}/compare", headers=_AUTH)
    assert resp.status_code == 409  # 在途，拒绝重复


# ── KD2 GET 生命周期（恒 200）─────────────────────────────────────────────────


def test_get_compare_before_run_returns_none_status(client):
    project_id = _new_project(client)
    resp = client.get(f"/tender/projects/{project_id}/compare", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "none"
    assert body["result"] is None
    assert body["stale"] is False


@pytest.mark.parametrize(
    ("task_status", "expected"), [("accepted", "pending"), ("running", "running")]
)
def test_get_compare_reports_in_flight_status(client, task_status, expected):
    project_id = _new_project(client)
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    _compare_task(project_id, task_status)
    body = client.get(f"/tender/projects/{project_id}/compare", headers=_AUTH).json()
    assert body["status"] == expected


def test_get_compare_exposes_known_business_failure(client):
    """AC2：已登记的业务失败原因原文可见（用户看得懂、知道下一步）。"""
    from server.tender.compare_guard import COMPARE_TIMEOUT_REASON

    project_id = _new_project(client)
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    _compare_task(project_id, "failed", error_detail=COMPARE_TIMEOUT_REASON)
    body = client.get(f"/tender/projects/{project_id}/compare", headers=_AUTH).json()
    assert body["status"] == "failed"
    assert body["error_detail"] == COMPARE_TIMEOUT_REASON


def test_get_compare_masks_unknown_internal_failure(client):
    """F6：未登记的内部异常一律固定文案，不泄露 traceback / 路径 / SQL 细节。"""
    from server.tender.compare_guard import GENERIC_ERROR_DETAIL

    project_id = _new_project(client)
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    _compare_task(
        project_id,
        "failed",
        error_detail=(
            "Traceback (most recent call last):\n"
            '  File "/Users/dev/workspace/server/tender/compare_worker.py", line 9, in run\n'
            "sqlite3.OperationalError: no such column: foo"
        ),
    )
    body = client.get(f"/tender/projects/{project_id}/compare", headers=_AUTH).json()
    assert body["status"] == "failed"
    assert body["error_detail"] == GENERIC_ERROR_DETAIL
    assert "Traceback" not in body["error_detail"]
    assert "/Users/dev" not in body["error_detail"]


def test_get_compare_result_and_stale(client):
    from server.stores.tender_compare_store import upsert_compare_result
    from server.tender.compare_input import collect_compare_input

    project_id = _new_project(client)
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    _input, signature = collect_compare_input("acme", project_id, {})
    upsert_compare_result(
        project_id=project_id, tenant="acme",
        payload={"recommended": None, "provisional": True, "bidders": []},
        signature=signature,
    )
    got = client.get(f"/tender/projects/{project_id}/compare", headers=_AUTH).json()
    assert got["status"] == "ready"
    assert got["stale"] is False  # 参与集未变
    # 追加第 3 家 → 旧 compare 应 stale（codex P2.6）
    _archive_bid(project_id, "B3", 1100.0)
    got2 = client.get(f"/tender/projects/{project_id}/compare", headers=_AUTH).json()
    assert got2["stale"] is True


# ── KD2 自动触发（前端不在场也能出横比）────────────────────────────────────────


def test_auto_schedule_compare_when_two_bidders_complete(monkeypatch):
    import asyncio as _asyncio

    import server.tender.compare_worker as worker

    scheduled: list[str] = []
    monkeypatch.setattr(
        worker, "schedule_compare_task", lambda **kw: scheduled.append(kw["request_id"])
    )
    project_id = get_or_create_project(
        tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}"
    )["project_id"]
    _seed_project_criteria(project_id)
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)

    assert _asyncio.run(worker.maybe_schedule_compare("acme", project_id)) is not None
    assert len(scheduled) == 1


def test_auto_schedule_skips_when_single_bidder_or_active_or_unchanged(monkeypatch):
    import asyncio as _asyncio

    import server.tender.compare_worker as worker
    from server.stores.tender_compare_store import upsert_compare_result
    from server.tender.compare_input import collect_compare_input

    monkeypatch.setattr(worker, "schedule_compare_task", lambda **kw: None)
    project_id = get_or_create_project(
        tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}"
    )["project_id"]
    _seed_project_criteria(project_id)
    _archive_bid(project_id, "B1", 1000.0)
    assert _asyncio.run(worker.maybe_schedule_compare("acme", project_id)) is None  # 仅 1 家

    _archive_bid(project_id, "B2", 1200.0)
    _compare_task(project_id, "running", request_id="cmp-inflight")
    assert _asyncio.run(worker.maybe_schedule_compare("acme", project_id)) is None  # 在途
    _compare_task(project_id, "completed", request_id="cmp-inflight")  # 同一任务落终态

    _input, signature = collect_compare_input("acme", project_id, {})
    upsert_compare_result(
        project_id=project_id, tenant="acme",
        payload={"recommended": None, "provisional": True, "bidders": []},
        signature=signature,
    )
    # 签名未变 → 不重复算；第三家到达（签名变）→ 恰好再算一次
    assert _asyncio.run(worker.maybe_schedule_compare("acme", project_id)) is None
    _archive_bid(project_id, "B3", 1100.0)
    assert _asyncio.run(worker.maybe_schedule_compare("acme", project_id)) is not None


def test_eval_worker_triggers_compare_on_terminal_state(monkeypatch):
    """AC1：一家 failed 后重评 completed → 无前端参与，评标 worker 自行入队横比。"""
    import asyncio as _asyncio

    import server.tender.worker as tender_worker

    triggered: list[str] = []
    monkeypatch.setattr(
        tender_worker, "maybe_schedule_compare",
        lambda tenant, project_id: triggered.append(project_id),
    )
    project_id = get_or_create_project(
        tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}"
    )["project_id"]
    criteria = _seed_project_criteria(project_id)

    async def fake_eval(**kwargs):
        from server.common.agent_bridge import AgentRunMeta

        if kwargs["request_id"].endswith("-fail"):
            raise RuntimeError("模型网关拥塞")
        return (
            {"verdict": "manual_review", "claim_id": "B1",
             "extracted_data": {"criteria": criteria}},
            AgentRunMeta(
                request_id=kwargs["request_id"], conversation_id="c",
                claude_session_id="s", resume_session_id=None, fork_from_session_id=None,
                schema_name="tender/audit-result.schema.json", log_file="l",
                result_file="r", result_subtype="ok", cost_usd=0.0, finished_at=None,
            ),
        )

    monkeypatch.setattr(tender_worker, "_run_evaluation", fake_eval)

    for suffix in ("-fail", "-ok"):
        _asyncio.run(
            tender_worker.execute_tender_evaluation_task(
                request_id=f"rid-{uuid.uuid4().hex[:6]}{suffix}",
                tenant="acme",
                directory_path="/fake/dir",
                source_mode="directory",
                project_id=project_id,
            )
        )

    assert triggered == [project_id, project_id]  # failed 与 completed 都要复查


def test_eval_worker_auto_compare_runs_end_to_end(monkeypatch):
    """F1 回归：**不 mock 调度链**——评标终态 → 自动入队 → compare 真跑完并落库。

    只 mock 两个外部边界（模型调用 ``_run_evaluation`` / ``run_command_json``），
    生产真实链路 worker → maybe_schedule_compare → schedule_compare_task → create_task
    全程真跑。旧实现把判定放 ``asyncio.to_thread``，``create_task`` 在无 loop 的工作线程
    抛 RuntimeError：评标任务从 finally 冲出异常、accepted 幽灵行把项目永久锁在"横比进行中"。
    """
    import asyncio as _asyncio

    import server.tender.worker as tender_worker
    from server.common.agent_bridge import AgentRunMeta
    from server.stores.tender_compare_store import get_compare_result
    from server.stores.tender_compare_task_store import list_compare_tasks
    from server.tender import compare_worker

    project_id = get_or_create_project(
        tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}"
    )["project_id"]
    criteria = _seed_project_criteria(project_id)
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)

    def _meta(request_id: str, schema_name: str) -> AgentRunMeta:
        return AgentRunMeta(
            request_id=request_id, conversation_id="c", claude_session_id="s",
            resume_session_id=None, fork_from_session_id=None, schema_name=schema_name,
            log_file="l", result_file="r", result_subtype="ok", cost_usd=0.0,
            finished_at=None,
        )

    async def fake_eval(**kwargs):
        return (
            {"verdict": "manual_review", "claim_id": "B3",
             "extracted_data": {"criteria": criteria}},
            _meta(kwargs["request_id"], "tender/audit-result.schema.json"),
        )

    async def fake_compare(command_name, *args, schema_name, **opts):
        return (
            {"project_id": project_id, "bidders": [], "recommended": None,
             "provisional": True, "warnings": [], "explanation": "横比完成",
             "policy_refs": []},
            _meta(opts["request_id"], schema_name),
        )

    monkeypatch.setattr(tender_worker, "_run_evaluation", fake_eval)
    monkeypatch.setattr(compare_worker, "run_command_json", fake_compare)

    leftovers: list[object] = []

    async def scenario() -> None:
        before = set(_asyncio.all_tasks())
        await tender_worker.execute_tender_evaluation_task(
            request_id=f"rid-{uuid.uuid4().hex[:6]}",
            tenant="acme",
            directory_path="/fake/dir",
            source_mode="directory",
            project_id=project_id,
        )
        background = list(compare_worker._BACKGROUND_TASKS)
        assert background, "评标终态后应有 compare 后台任务在跑"
        await _asyncio.gather(*background)
        # flusher 已 cancel：除本协程与 compare 任务外不应留在途任务
        leftovers.extend(
            task
            for task in _asyncio.all_tasks()
            if not task.done()
            and task is not _asyncio.current_task()
            and task not in before
            and task not in background
        )

    _asyncio.run(scenario())  # 评标任务本身不得抛异常

    assert leftovers == []
    stored = get_compare_result(project_id, "acme")
    assert stored is not None and stored["payload"]["explanation"] == "横比完成"
    statuses = [t.get("status") for t in list_compare_tasks("acme", group_id=project_id, limit=10)]
    assert "completed" in statuses
    assert "accepted" not in statuses  # 不留幽灵在途行


# ── codex P1.1 / P1.2 污染回归（最关键）────────────────────────────────────────


def test_compare_does_not_pollute_results_or_roster(client, monkeypatch):
    """compare **真链路**不污染 results/名册（codex P1.1/P1.2 + P2.3 真覆盖）。"""
    import asyncio as _asyncio

    import server.tender.compare_worker as worker

    project_id = _new_project(client)
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    results_before = len(
        client.get(f"/tender/projects/{project_id}/results", headers=_AUTH).json()
    )

    captured: dict = {}

    async def fake_json(command_name, *args, schema_name, **opts):
        captured["archive_to_results"] = opts.get("archive_to_results")
        captured["input"] = json.loads(args[0])
        from server.common.agent_bridge import AgentRunMeta

        meta = AgentRunMeta(
            request_id=opts["request_id"], conversation_id="c", claude_session_id="s",
            resume_session_id=None, fork_from_session_id=None, schema_name=schema_name,
            log_file="l", result_file="r", result_subtype="ok", cost_usd=0.0, finished_at=None,
        )
        return {"project_id": project_id, "bidders": [], "recommended": None,
                "provisional": True, "warnings": [], "explanation": "x", "policy_refs": []}, meta

    monkeypatch.setattr(worker, "run_command_json", fake_json)
    _asyncio.run(
        worker.execute_compare_task(request_id="cmp-real", tenant="acme", project_id=project_id)
    )

    # archive flag 确实以 False 透传（compare 不进 results）
    assert captured["archive_to_results"] is False
    # 服务端判据随输入下发给命令（KD1/KD3/KD4）
    assert captured["input"]["criteria_version"]
    assert captured["input"]["criteria_price_item"]["item"] == "价格分"
    # results 表无新增（compare 没污染）；名册仍 2 家
    results_after = client.get(f"/tender/projects/{project_id}/results", headers=_AUTH).json()
    assert len(results_after) == results_before == 2
    detail = client.get(f"/tender/projects/{project_id}", headers=_AUTH).json()
    assert detail["bidder_count"] == 2
    assert sorted(b["claim_id"] for b in detail["bids"]) == ["B1", "B2"]
    # compare 结果已存专表
    got = client.get(f"/tender/projects/{project_id}/compare", headers=_AUTH).json()
    assert got["status"] == "ready"


def test_compare_recommended_shows_in_detail_when_final(client):
    """compare 非 stale 且非 provisional → 详情展示 recommendedBidder（codex P1.5）。"""
    from server.stores.tender_compare_store import upsert_compare_result
    from server.tender.compare_input import collect_compare_input

    project_id = _new_project(client, funding_type="state_funded")
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    _input, signature = collect_compare_input("acme", project_id, {})
    upsert_compare_result(
        project_id=project_id, tenant="acme",
        payload={"recommended": "B1", "provisional": False, "bidders": []},
        signature=signature,
    )
    detail = client.get(f"/tender/projects/{project_id}", headers=_AUTH).json()
    assert detail["recommended_bidder"] == "B1"
    assert detail["compare_stale"] is False


def test_compare_provisional_hidden_in_detail(client):
    """provisional 推荐不在详情展示 recommendedBidder（codex P1.5）。"""
    from server.stores.tender_compare_store import upsert_compare_result
    from server.tender.compare_input import collect_compare_input

    project_id = _new_project(client, funding_type="other")
    _archive_bid(project_id, "B1", 1000.0)
    _archive_bid(project_id, "B2", 1200.0)
    _input, signature = collect_compare_input("acme", project_id, {})
    upsert_compare_result(
        project_id=project_id, tenant="acme",
        payload={"recommended": None, "provisional": True, "bidders": []},
        signature=signature,
    )
    detail = client.get(f"/tender/projects/{project_id}", headers=_AUTH).json()
    assert detail["recommended_bidder"] is None
