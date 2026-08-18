"""P0.5 · 总分由服务端按 ``scoring[]`` 汇总，且待定量与得分同时给出。

4/4 条线上结论的 ``total_score`` / ``total_max`` 恒为 ``null``——``extracted_data`` 是
``additionalProperties:true``，schema 不强制，模型也就不给。前端拿不到总分。

**为什么不能只给 total_score/total_max**：评标里 ``score=null`` 是常态（等横比、需外部数据、
需现场答辩、证据未核实……）。一份 12 项里 10 项待定的结论，只给"12/100"会被读成"这家得了
12 分"，实际是"88 分还没判"。所以 ``pending_count`` / ``pending_max`` 与总分是**同一组
不可拆的字段**，本文件把这条钉死。

``score=null`` 绝不当 0 计——那等于服务端替模型判了 0 分，正是 tender-evaluate 判分仲裁
决策表反复禁止的动作。
"""

from __future__ import annotations

from typing import Any

from server.common.output_contracts import enrich_audit_decision


def _result(scoring: list[dict[str, Any]] | Any) -> dict[str, Any]:
    return {"verdict": "manual_review", "extracted_data": {"scoring": scoring}}


def _totals(scoring: list[dict[str, Any]] | Any) -> dict[str, Any]:
    return enrich_audit_decision(_result(scoring))["extracted_data"]


# ── 汇总本身 ─────────────────────────────────────────────────────────────────


def test_total_score_sums_only_the_items_that_have_a_score():
    extracted = _totals(
        [
            {"item": "投标报价", "max": 40, "score": 36},
            {"item": "技术方案", "max": 30, "score": 22.5},
            {"item": "类似业绩", "max": 30, "score": None, "pending_reason": "evidence_unresolved"},
        ]
    )

    assert extracted["total_score"] == 58.5
    assert extracted["total_max"] == 100


def test_pending_items_are_reported_alongside_the_total():
    """AC：``pending_count``/``pending_max`` 必须与总分同时给出。"""
    extracted = _totals(
        [
            {"item": "投标报价", "max": 40, "score": 12},
            {"item": "类似业绩", "max": 30, "score": None, "pending_reason": "cross_bid"},
            {"item": "团队人员", "max": 30, "score": None, "pending_reason": "live_event"},
        ]
    )

    assert extracted["total_score"] == 12
    assert extracted["total_max"] == 100
    assert extracted["pending_count"] == 2
    assert extracted["pending_max"] == 60, "「12/100」必须能被读成「88 分待定」而不是「得了 12 分」"


def test_a_null_score_is_never_counted_as_zero():
    """全待定的一单：总分 0 是"还没判"，不是"判了 0 分"——靠 pending 字段把两者分开。"""
    extracted = _totals(
        [
            {"item": "投标报价", "max": 40, "score": None, "pending_reason": "cross_bid"},
            {"item": "技术方案", "max": 60, "score": None, "pending_reason": "manual_mode"},
        ]
    )

    assert extracted["total_score"] == 0
    assert extracted["pending_count"] == 2
    assert extracted["pending_max"] == 100


def test_a_real_zero_is_distinguishable_from_an_undecided_item():
    """判据句：同样是 total_score=0，判了 0 分与还没判必须能分辨。"""
    scored_zero = _totals([{"item": "技术方案", "max": 60, "score": 0}])
    undecided = _totals(
        [{"item": "技术方案", "max": 60, "score": None, "pending_reason": "manual_mode"}]
    )

    assert scored_zero["total_score"] == undecided["total_score"] == 0
    assert scored_zero["pending_count"] == 0
    assert undecided["pending_count"] == 1
    assert scored_zero["pending_max"] == 0
    assert undecided["pending_max"] == 60


def test_totals_do_not_trust_the_model_supplied_values():
    """模型自报的总分一律以服务端重算为准——它算错过，而这是个纯算术。"""
    payload = {
        "verdict": "manual_review",
        "extracted_data": {
            "total_score": 999,
            "total_max": 999,
            "pending_count": 999,
            "pending_max": 999,
            "scoring": [{"item": "投标报价", "max": 40, "score": 36}],
        },
    }

    extracted = enrich_audit_decision(payload)["extracted_data"]

    assert extracted["total_score"] == 36
    assert extracted["total_max"] == 40
    assert extracted["pending_count"] == 0
    assert extracted["pending_max"] == 0


# ── 边界与非污染 ─────────────────────────────────────────────────────────────


def test_items_without_a_numeric_max_do_not_corrupt_the_totals():
    """``max=null`` 只在 manual 且需外部输入的项上合法，它不参与满分算术（criteria 契约原文）。"""
    extracted = _totals(
        [
            {"item": "投标报价", "max": 40, "score": 36},
            {"item": "现场答辩", "max": None, "score": None, "pending_reason": "live_event"},
        ]
    )

    assert extracted["total_max"] == 40
    assert extracted["total_score"] == 36
    assert extracted["pending_count"] == 0, "满分未知的项计不进待定分——它连量纲都没有"
    assert extracted["pending_max"] == 0


def test_garbage_scoring_entries_are_skipped_not_crashed():
    """信任边界：scoring 来自模型，混进非对象项时跳过即可，不得让取结论的端点 500。"""
    extracted = _totals([{"item": "投标报价", "max": 40, "score": 36}, "坏数据", None])

    assert extracted["total_score"] == 36
    assert extracted["total_max"] == 40


def test_results_without_scoring_are_left_untouched():
    """expense / audit 结论没有 scoring——不得凭空长出四个字段。"""
    payload = {"verdict": "approved", "extracted_data": {"invoice_no": "X-1"}}

    extracted = enrich_audit_decision(payload)["extracted_data"]

    assert "total_score" not in extracted
    assert "total_max" not in extracted
    assert "pending_count" not in extracted
    assert "pending_max" not in extracted


def test_empty_scoring_adds_no_totals():
    """空评分表不是"总分 0 分"，是"还没有评分表"——不得渲染成 0/0。"""
    assert "total_score" not in _totals([])


def test_enrich_stays_idempotent():
    """两个出口都会 enrich（任务结果 / 项目结论），重复跑不得把数字滚雪球。"""
    payload = _result([{"item": "投标报价", "max": 40, "score": 36}])

    once = enrich_audit_decision(payload)["extracted_data"]
    twice = enrich_audit_decision(payload)["extracted_data"]

    assert once == twice


def test_structured_totals_agree_with_the_explanation_summary():
    """漂移守卫：``tender.output._score_summary`` 也在算同一笔账（渲染成得分小结文本）。

    两处算术**目前是两份代码**（本项不得改 ``server/tender/output.py``，那个文件另有写者）。
    数字一旦分家，用户会同时看到"得分小结：合计 58.5 分"和一个不同的 ``total_score``，
    而没人能说清哪个对。本条把两者钉在一起，等哪次能合并时它就是回归闸。
    """
    from server.tender.output import _format_score, _score_summary

    scoring = [
        {"item": "投标报价", "max": 40, "score": 36},
        {"item": "技术方案", "max": 30, "score": 22.5},
        {"item": "类似业绩", "max": 30, "score": None, "pending_reason": "cross_bid"},
    ]
    extracted = _totals(scoring)
    summary = _score_summary({"scoring": scoring})

    assert summary is not None
    assert f"满分 {_format_score(extracted['total_max'])} 分" in summary
    assert f"合计 {_format_score(extracted['total_score'])} 分" in summary
    assert f"还有 {extracted['pending_count']} 项" in summary
    assert f"共 {_format_score(extracted['pending_max'])} 分" in summary


# ── 出口可达性：前端真的拿得到 ───────────────────────────────────────────────


def test_totals_reach_the_task_result_endpoint(monkeypatch):
    """AC 的落点：``GET /tender/tasks/{id}/result`` 必须把四个字段吐给前端。"""
    import uuid

    from fastapi.testclient import TestClient

    import server.api as api_module
    import server.routes.deps as deps_module
    from server.stores.result_store import archive_result_payload
    from server.stores.tender_task_store import upsert_tender_task
    from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME

    token = "test-fake-token-acme-totals"
    monkeypatch.setattr(deps_module, "TENANT_KEYS", {"acme": token})
    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    client = TestClient(api_module.app)

    request_id = f"req-totals-{uuid.uuid4().hex[:12]}"
    upsert_tender_task(
        {
            "request_id": request_id,
            "tenant": "acme",
            "status": "completed",
            "mode": "directory",
            "case_path": "/fake/tender-case",
            "updated_at": "2026-08-18T00:00:00+00:00",
        }
    )
    archive_result_payload(
        request_id=request_id,
        tenant="acme",
        project_id=None,
        conversation_id="conv-totals",
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=TENDER_OUTPUT_SCHEMA_NAME,
        request_mode="structured",
        result_subtype="success",
        cost_usd=0.0,
        prompt_preview="x",
        response={
            "verdict": "manual_review",
            "claim_id": "BID-T",
            "extracted_data": {
                "scoring": [
                    {"item": "投标报价", "max": 40, "score": 12},
                    {"item": "类似业绩", "max": 60, "score": None, "pending_reason": "cross_bid"},
                ]
            },
        },
    )

    body = client.get(
        f"/tender/tasks/{request_id}/result", headers={"Authorization": f"Bearer {token}"}
    ).json()

    extracted = body["extracted_data"]
    assert extracted["total_score"] == 12
    assert extracted["total_max"] == 100
    assert extracted["pending_count"] == 1
    assert extracted["pending_max"] == 60
