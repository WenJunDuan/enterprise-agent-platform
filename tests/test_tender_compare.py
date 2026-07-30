"""Phase 2 价格横比测试：契约 + 收集/签名 + 端点 + codex P1.1/P1.2 污染回归。

compare 调 Claude（异步）被 monkeypatch（schedule no-op / archive_result_payload 直接喂）。
重点锁定：compare 结果**不进 results 表、不进 bid 名册**（codex P1.1/P1.2），stale 检测，
criteria 一致性签名，端点 ≥2 家校验。
"""

from __future__ import annotations

import uuid

import jsonschema
import pytest
from fastapi.testclient import TestClient

from server.common.contract import load_output_schema
from server.routes.upload_helpers import tenant_submission_root
from server.stores.result_store import archive_result_payload
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


def _criteria(price_max: int | None = 40, *, price_mode: str = "formula") -> dict:
    return {
        "source_ref": "招标文件.pdf 评标办法 p.18",
        "method": "综合评估法",
        "total_max": 100,
        "items": [
            {"item": "技术", "max": 60, "scoring_rule": "技术评分", "source_ref": "p.19", "tag": "scored"},
            {
                "item": "价格分",
                "max": price_max,
                "scoring_rule": "最低价/本价×40",
                "source_ref": "p.18",
                "tag": "requires_cross_bid_comparison",
                "score_mode": price_mode,
            },
        ],
    }


def _archive_bid(project_id: str, claim_id: str, amount: float, criteria: dict | None = None) -> str:
    """直接归档一份 completed 投标结论（带 project_id + bid_price + criteria）。"""
    rid = f"bid-{uuid.uuid4().hex[:8]}"
    archive_result_payload(
        request_id=rid,
        tenant="acme",
        project_id=project_id,
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
                "criteria": criteria if criteria is not None else _criteria(),
                "bid_price": {"amount": amount, "currency": "CNY"},
                "scoring": [{"item": "技术", "max": 60, "score": 50, "status": "scored"}],
            },
        },
    )
    return rid


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


# ── 收集 + 签名（worker 纯函数）────────────────────────────────────────────────


def test_collect_compare_input_and_signature():
    from server.tender.compare_worker import collect_compare_input

    pid = get_or_create_project(tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    collected = collect_compare_input("acme", pid, {"funding_type": "state_funded"})
    assert collected is not None
    compare_input, sig = collected
    assert len(compare_input["bidders"]) == 2
    assert compare_input["funding_type"] == "state_funded"
    # 价格项被识别
    assert compare_input["criteria_price_item"]["item"] == "价格分"
    assert len(sig.input_result_ids) == 2


def test_collect_blocks_manual_null_price_item_from_comparison_and_ranking():
    from server.tender.compare_worker import collect_compare_input

    pid = get_or_create_project(tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}")[
        "project_id"
    ]
    criteria = _criteria(price_max=None, price_mode="manual")
    _archive_bid(pid, "B1", 1000.0, criteria=criteria)
    _archive_bid(pid, "B2", 1200.0, criteria=criteria)

    compare_input, _sig = collect_compare_input("acme", pid, {})

    assert compare_input["criteria_price_item"] is None
    assert compare_input["price_comparison_blocked"] is True
    assert compare_input["price_comparison_blocked_reason"] == "price_item_missing_or_invalid"


@pytest.mark.parametrize("second_criteria", [_criteria(price_max=None), _criteria(price_max=40)])
def test_collect_checks_every_bidder_price_item_and_criteria_consistency(second_criteria):
    from server.tender.compare_worker import collect_compare_input

    if second_criteria["items"][-1]["max"] == 40:
        second_criteria = {**second_criteria, "method": "其他"}
    pid = get_or_create_project(tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}")[
        "project_id"
    ]
    _archive_bid(pid, "B1", 1000.0, criteria=_criteria())
    _archive_bid(pid, "B2", 1200.0, criteria=second_criteria)

    compare_input, _sig = collect_compare_input("acme", pid, {})

    assert compare_input["price_comparison_blocked"] is True
    assert compare_input["criteria_price_item"] is None


def test_collect_blocks_when_any_bidder_has_no_price_item():
    from server.tender.compare_worker import collect_compare_input

    criteria_without_price = _criteria()
    criteria_without_price["items"] = criteria_without_price["items"][:1]
    pid = get_or_create_project(tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}")[
        "project_id"
    ]
    _archive_bid(pid, "B1", 1000.0, criteria=_criteria())
    _archive_bid(pid, "B2", 1200.0, criteria=criteria_without_price)

    compare_input, _sig = collect_compare_input("acme", pid, {})

    assert compare_input["price_comparison_blocked"] is True
    assert compare_input["criteria_price_item"] is None


def test_unknown_price_max_forces_manual_result_even_if_model_returns_rank():
    from server.tender.compare_worker import enforce_price_comparison_block

    payload = {
        "bidders": [
            {
                "claim_id": "B1",
                "price_score": 40,
                "other_score": 50,
                "total_score": 90,
                "rank": 1,
                "status": "scored",
            }
        ],
        "recommended": "B1",
        "provisional": False,
        "warnings": [],
        "explanation": "B1 排名第一",
    }
    compare_input = {
        "price_comparison_blocked": True,
        "bidders": [{"claim_id": "B1", "bid_price": {"amount": 1000, "currency": "CNY"}}],
    }

    enforce_price_comparison_block(payload, compare_input)

    assert payload["recommended"] is None
    assert payload["provisional"] is True
    assert payload["bidders"][0]["rank"] is None
    assert payload["bidders"][0]["price_score"] is None
    assert payload["bidders"][0]["total_score"] is None
    assert payload["bidders"][0]["status"] == "manual_review"


def test_inconsistent_criteria_forces_manual_result_even_if_model_returns_rank():
    from server.tender.compare_worker import enforce_price_comparison_block

    payload = {
        "bidders": [
            {
                "claim_id": "B1",
                "price_score": 40,
                "total_score": 90,
                "rank": 1,
                "status": "scored",
            }
        ],
        "recommended": "B1",
        "provisional": False,
        "warnings": [],
    }
    compare_input = {
        "price_comparison_blocked": True,
        "price_comparison_blocked_reason": "criteria_inconsistent",
        "bidders": [{"claim_id": "B1", "bid_price": None}],
    }

    enforce_price_comparison_block(payload, compare_input)

    assert payload["bidders"][0]["price_score"] is None
    assert payload["bidders"][0]["total_score"] is None
    assert payload["bidders"][0]["rank"] is None
    assert payload["recommended"] is None


def test_collect_returns_none_when_under_two():
    from server.tender.compare_worker import collect_compare_input

    pid = get_or_create_project(tenant="acme", tender_no=f"R-{uuid.uuid4().hex[:8]}")["project_id"]
    _archive_bid(pid, "B1", 1000.0)
    assert collect_compare_input("acme", pid, {}) is None  # 仅 1 家


# ── 端点 ──────────────────────────────────────────────────────────────────────


def _new_project(client: TestClient, **kw) -> str:
    return client.post(
        "/tender/projects",
        json={"tender_no": f"R-{uuid.uuid4().hex[:8]}", **kw},
        headers=_AUTH,
    ).json()["project_id"]


def test_trigger_compare_requires_two_bidders(client):
    pid = _new_project(client)
    _archive_bid(pid, "B1", 1000.0)
    resp = client.post(f"/tender/projects/{pid}/compare", headers=_AUTH)
    assert resp.status_code == 400  # 不足 2 家


def test_trigger_compare_accepted(client):
    pid = _new_project(client, funding_type="state_funded")
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    resp = client.post(f"/tender/projects/{pid}/compare", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "compare"


def test_trigger_compare_unknown_project_404(client):
    assert client.post("/tender/projects/nope/compare", headers=_AUTH).status_code == 404


def test_trigger_compare_duplicate_returns_409(client):
    """cc C1：同 project 已有在途 compare → 409，防并发双击重复算。"""
    from server.stores.tender_compare_task_store import upsert_compare_task

    pid = _new_project(client, funding_type="state_funded")
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    # 手动放一个在途(running) compare task（绕过 fixture 的 schedule no-op）
    upsert_compare_task(
        {
            "request_id": "cmp-active",
            "tenant": "acme",
            "status": "running",
            "mode": "compare",
            "source_mode": "compare",
            "case_path": "-",
            "group_id": pid,
            "updated_at": "2026-06-20T00:00:00+00:00",
        }
    )
    resp = client.post(f"/tender/projects/{pid}/compare", headers=_AUTH)
    assert resp.status_code == 409  # 在途，拒绝重复


def test_get_compare_before_run_404(client):
    pid = _new_project(client)
    assert client.get(f"/tender/projects/{pid}/compare", headers=_AUTH).status_code == 404


def test_get_compare_result_and_stale(client):
    from server.stores.tender_compare_store import (
        upsert_compare_result,
    )
    from server.tender.compare_worker import collect_compare_input

    pid = _new_project(client)
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    # 存一份 compare 结果，签名匹配当前 2 家
    _input, sig = collect_compare_input("acme", pid, {})
    upsert_compare_result(
        project_id=pid, tenant="acme",
        payload={"recommended": None, "provisional": True, "bidders": []},
        signature=sig,
    )
    got = client.get(f"/tender/projects/{pid}/compare", headers=_AUTH).json()
    assert got["stale"] is False  # 参与集未变
    # 追加第 3 家 → 旧 compare 应 stale（codex P2.6）
    _archive_bid(pid, "B3", 1100.0)
    got2 = client.get(f"/tender/projects/{pid}/compare", headers=_AUTH).json()
    assert got2["stale"] is True


# ── codex P1.1 / P1.2 污染回归（最关键）────────────────────────────────────────


def test_compare_does_not_pollute_results_or_roster(client, monkeypatch):
    """compare **真链路**不污染 results/名册（codex P1.1/P1.2 + P2.3 真覆盖）。

    跑 execute_compare_task → run_command_json，断言 archive_to_results=False 被透传，
    且 compare 完成后 results 表无新增（名册/回看仍只 2 家真实投标人）。
    """
    import asyncio as _asyncio

    import server.tender.compare_worker as worker

    pid = _new_project(client)
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    results_before = len(client.get(f"/tender/projects/{pid}/results", headers=_AUTH).json())

    captured: dict = {}

    async def fake_json(command_name, *args, schema_name, **opts):
        captured["archive_to_results"] = opts.get("archive_to_results")
        from server.common.agent_bridge import AgentRunMeta

        meta = AgentRunMeta(
            request_id=opts["request_id"], conversation_id="c", claude_session_id="s",
            resume_session_id=None, fork_from_session_id=None, schema_name=schema_name,
            log_file="l", result_file="r", result_subtype="ok", cost_usd=0.0, finished_at=None,
        )
        return {"project_id": pid, "bidders": [], "recommended": None,
                "provisional": True, "warnings": [], "explanation": "x", "policy_refs": []}, meta

    monkeypatch.setattr(worker, "run_command_json", fake_json)
    _asyncio.run(worker.execute_compare_task(request_id="cmp-real", tenant="acme", project_id=pid))

    # archive flag 确实以 False 透传（compare 不进 results）
    assert captured["archive_to_results"] is False
    # results 表无新增（compare 没污染）；名册仍 2 家
    results_after = client.get(f"/tender/projects/{pid}/results", headers=_AUTH).json()
    assert len(results_after) == results_before == 2
    detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
    assert detail["bidder_count"] == 2
    assert sorted(b["claim_id"] for b in detail["bids"]) == ["B1", "B2"]
    # compare 结果已存专表
    assert client.get(f"/tender/projects/{pid}/compare", headers=_AUTH).status_code == 200


def test_collect_flags_criteria_inconsistent(client):
    """codex P1.1：各家 criteria 不一致 → compare 输入标 criteria_inconsistent=true。"""
    from server.tender.compare_worker import collect_compare_input

    pid = _new_project(client)
    _archive_bid(pid, "B1", 1000.0, criteria=_criteria(price_max=40))
    _archive_bid(pid, "B2", 1200.0, criteria=_criteria(price_max=30))  # 不同满分→不同 hash
    compare_input, _sig = collect_compare_input("acme", pid, {})
    assert compare_input["criteria_inconsistent"] is True


def test_collect_criteria_consistent_when_same(client):
    """各家 criteria 相同 → criteria_inconsistent=false。"""
    from server.tender.compare_worker import collect_compare_input

    pid = _new_project(client)
    same = _criteria()
    _archive_bid(pid, "B1", 1000.0, criteria=same)
    _archive_bid(pid, "B2", 1200.0, criteria=same)
    compare_input, _sig = collect_compare_input("acme", pid, {})
    assert compare_input["criteria_inconsistent"] is False


def test_compare_recommended_shows_in_detail_when_final(client):
    """compare 非 stale 且非 provisional → 详情展示 recommendedBidder（codex P1.5）。"""
    from server.stores.tender_compare_store import upsert_compare_result
    from server.tender.compare_worker import collect_compare_input

    pid = _new_project(client, funding_type="state_funded")
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    _input, sig = collect_compare_input("acme", pid, {})
    upsert_compare_result(
        project_id=pid, tenant="acme",
        payload={"recommended": "B1", "provisional": False, "bidders": []},
        signature=sig,
    )
    detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
    assert detail["recommended_bidder"] == "B1"
    assert detail["compare_stale"] is False


def test_compare_provisional_hidden_in_detail(client):
    """provisional 推荐不在详情展示 recommendedBidder（codex P1.5）。"""
    from server.stores.tender_compare_store import upsert_compare_result
    from server.tender.compare_worker import collect_compare_input

    pid = _new_project(client, funding_type="other")
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    _input, sig = collect_compare_input("acme", pid, {})
    upsert_compare_result(
        project_id=pid, tenant="acme",
        payload={"recommended": None, "provisional": True, "bidders": []},
        signature=sig,
    )
    detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
    assert detail["recommended_bidder"] is None
