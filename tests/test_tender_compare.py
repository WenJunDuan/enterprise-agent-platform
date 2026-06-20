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
    monkeypatch.setattr("server.routes.tender.schedule_compare_task", lambda **kw: None)
    return TestClient(api_module.app)


def _criteria(price_max: int = 40) -> dict:
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
    from server.routes.tender_compare_worker import collect_compare_input

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


def test_collect_returns_none_when_under_two():
    from server.routes.tender_compare_worker import collect_compare_input

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


def test_get_compare_before_run_404(client):
    pid = _new_project(client)
    assert client.get(f"/tender/projects/{pid}/compare", headers=_AUTH).status_code == 404


def test_get_compare_result_and_stale(client):
    from server.stores.tender_compare_store import (
        upsert_compare_result,
    )
    from server.routes.tender_compare_worker import collect_compare_input

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


def test_compare_does_not_pollute_results_or_roster(client):
    """compare 结果不进 results 表、不进 bid 名册（codex P1.1/P1.2）。"""
    from server.stores.tender_compare_store import (
        CompareSignature,
        compute_criteria_hash,
        upsert_compare_result,
    )

    pid = _new_project(client)
    _archive_bid(pid, "B1", 1000.0)
    _archive_bid(pid, "B2", 1200.0)
    # compare 结果存专表（不经 results）
    upsert_compare_result(
        project_id=pid, tenant="acme",
        payload={"recommended": "B1", "provisional": False, "bidders": [{"claim_id": "B1"}]},
        signature=CompareSignature(input_result_ids=["x"], criteria_hash=compute_criteria_hash({})),
    )
    # 名册仍只有 2 家真实投标人，没有 compare 伪投标人
    detail = client.get(f"/tender/projects/{pid}", headers=_AUTH).json()
    assert detail["bidder_count"] == 2
    claim_ids = [b["claim_id"] for b in detail["bids"]]
    assert sorted(claim_ids) == ["B1", "B2"]
    # /results 回看也只有 2 家
    results = client.get(f"/tender/projects/{pid}/results", headers=_AUTH).json()
    assert len(results) == 2


def test_compare_recommended_shows_in_detail_when_final(client):
    """compare 非 stale 且非 provisional → 详情展示 recommendedBidder（codex P1.5）。"""
    from server.stores.tender_compare_store import upsert_compare_result
    from server.routes.tender_compare_worker import collect_compare_input

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
    from server.routes.tender_compare_worker import collect_compare_input

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
