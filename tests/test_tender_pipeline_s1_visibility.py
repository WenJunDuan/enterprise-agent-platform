"""S1 · 可见性 + 主链路掉落修复（sprint 2026-08-15-tender-context-pipeline，AC1/AC2/AC3）。

TDD：本文件先于实现写成。三组断言对应三条验收：

- AC1：两层预热 ready 且能定位当前家时，评标必须命中 ``doc_layer_reuse``——含"前端漏传
  bid_id"这一实测掉落路径（服务端按 bidder_name 兜底解析）。
- AC2：任何降级（掉落 inline / criteria 失败 / 索引缺失）都产出用户可见信号，无静默分支。
- AC3：``criteria`` 结构不合格时返回**具体原因**，而不是一个 bool。
"""

from __future__ import annotations

import asyncio

import pytest

from server.tender import bid_resolve, doc_context, doc_layer
from server.tender.doc_pipeline import (
    criteria_usability_problem,
    criteria_usability_problem_message,
)

# ═══════════════════════════════════════════════════════════════════════════
# AC1 · 主链路掉落根因：前端漏传 bid_id 时服务端按 bidder_name 解析
# ═══════════════════════════════════════════════════════════════════════════


def _bid_row(bid_id: str, bidder_name: str | None) -> dict[str, object]:
    return {"bid_id": bid_id, "bidder_name": bidder_name, "ocr_status": "ready"}


def test_explicit_bid_id_is_returned_unchanged(monkeypatch):
    """前端传了 bid_id → 原样采用，不查库（显式值永远优先）。"""

    def boom(*_a, **_kw):
        raise AssertionError("must not query bid docs when bid_id was supplied")

    monkeypatch.setattr(bid_resolve, "list_bid_docs", boom)
    resolved, reason = bid_resolve.resolve_prewarm_bid_id(
        "tp-1", "acme", explicit_bid_id="bid-9", bidder_name="某公司"
    )
    assert resolved == "bid-9"
    assert reason is None


def test_missing_bid_id_is_resolved_from_bidder_name(monkeypatch):
    """KD5 根因：前端提交早于 uploadBid 返回 → bid_id 丢失，服务端按 bidder_name 兜底解析。

    实测症状「两层预热 ready 却 source=inline_ocr / bid_id=null」正是这条路径。
    """
    monkeypatch.setattr(
        bid_resolve,
        "list_bid_docs",
        lambda pid, tenant: [_bid_row("bid-a", "甲公司"), _bid_row("bid-b", "乙公司")],
    )
    resolved, reason = bid_resolve.resolve_prewarm_bid_id(
        "tp-1", "acme", explicit_bid_id=None, bidder_name=" 乙公司 "
    )
    assert resolved == "bid-b", "应按 bidder_name 精确定位当前家"
    assert reason is None


def test_ambiguous_bidder_name_refuses_to_guess(monkeypatch):
    """同名两家 → 绝不猜（猜错 = 拿别家材料评本家），返回原因待可见降级。"""
    monkeypatch.setattr(
        bid_resolve,
        "list_bid_docs",
        lambda pid, tenant: [_bid_row("bid-a", "甲公司"), _bid_row("bid-b", "甲公司")],
    )
    resolved, reason = bid_resolve.resolve_prewarm_bid_id(
        "tp-1", "acme", explicit_bid_id=None, bidder_name="甲公司"
    )
    assert resolved is None
    assert reason == "bidder_name_ambiguous"


def test_unmatched_bidder_name_reports_reason(monkeypatch):
    monkeypatch.setattr(
        bid_resolve, "list_bid_docs", lambda pid, tenant: [_bid_row("bid-a", "甲公司")]
    )
    resolved, reason = bid_resolve.resolve_prewarm_bid_id(
        "tp-1", "acme", explicit_bid_id=None, bidder_name="丙公司"
    )
    assert resolved is None
    assert reason == "bidder_name_unmatched"


def test_no_bidder_name_reports_reason(monkeypatch):
    monkeypatch.setattr(
        bid_resolve, "list_bid_docs", lambda pid, tenant: [_bid_row("bid-a", "甲公司")]
    )
    resolved, reason = bid_resolve.resolve_prewarm_bid_id(
        "tp-1", "acme", explicit_bid_id=None, bidder_name=None
    )
    assert resolved is None
    assert reason == "bidder_name_missing"


def test_no_project_id_reports_reason():
    """散单路径（无 project_id）不在 AC1 约束内，但仍须给出原因而不是静默 None。"""
    resolved, reason = bid_resolve.resolve_prewarm_bid_id(
        None, "acme", explicit_bid_id=None, bidder_name="甲公司"
    )
    assert resolved is None
    assert reason == "project_missing"


def test_store_failure_is_reported_not_swallowed(monkeypatch):
    """DB 故障不得拖垮提交，但必须留下可见原因（AC2：无静默分支）。"""

    def boom(*_a, **_kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(bid_resolve, "list_bid_docs", boom)
    resolved, reason = bid_resolve.resolve_prewarm_bid_id(
        "tp-1", "acme", explicit_bid_id=None, bidder_name="甲公司"
    )
    assert resolved is None
    assert reason == "bid_lookup_failed"


# ═══════════════════════════════════════════════════════════════════════════
# AC1 回归不变量：两层 ready + 可定位当前家 → 必须命中 doc_layer_reuse
# ═══════════════════════════════════════════════════════════════════════════


def test_ready_layers_with_bid_id_must_hit_doc_layer_reuse(monkeypatch):
    """机械断言：两层 ready 且传入 bid_id 时，读层必须产出底稿（不得回落 inline）。"""
    monkeypatch.setattr(
        doc_layer,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿"},
    )
    monkeypatch.setattr(
        doc_layer,
        "get_bid_doc",
        lambda pid, bid_id, tenant: {
            "bid_id": bid_id,
            "ocr_status": "ready",
            "ocr_text": "投标底稿",
            "bidder_name": "甲公司",
        },
    )
    assert doc_layer.load_doc_layer_context("tp-1", "bid-a", "acme") is not None
    assert doc_context.describe_doc_layer_gap("tp-1", "bid-a", "acme") is None


# ═══════════════════════════════════════════════════════════════════════════
# AC2 · 掉落原因可见
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("project_row", "bid_row", "bid_id", "expected"),
    [
        (
            {"ocr_status": "ready", "ocr_text": "招标底稿"},
            {"bid_id": "b", "ocr_status": "ready", "ocr_text": "投标底稿"},
            None,
            "missing_bid_id",
        ),
        (
            None,
            {"bid_id": "b", "ocr_status": "ready", "ocr_text": "投标底稿"},
            "b",
            "tender_doc_absent",
        ),
        (
            {"ocr_status": "running", "ocr_text": None},
            {"bid_id": "b", "ocr_status": "ready", "ocr_text": "投标底稿"},
            "b",
            "tender_doc_not_usable",
        ),
        (
            {"ocr_status": "ready", "ocr_text": "招标底稿"},
            None,
            "b",
            "bid_doc_absent",
        ),
        (
            {"ocr_status": "ready", "ocr_text": "招标底稿"},
            {"bid_id": "b", "ocr_status": "failed", "ocr_text": None},
            "b",
            "bid_doc_not_usable",
        ),
        (
            {"ocr_status": "ready", "ocr_text": "招标底稿"},
            {"bid_id": "b", "ocr_status": "ready", "ocr_text": ""},
            "b",
            "bid_doc_empty",
        ),
    ],
)
def test_describe_doc_layer_gap_names_every_fallback_cause(
    monkeypatch, project_row, bid_row, bid_id, expected
):
    """遍历每条掉落分支，断言都有具名原因——没有一条能静默走掉。"""
    monkeypatch.setattr(doc_layer, "get_project_doc", lambda pid, tenant: project_row)
    monkeypatch.setattr(doc_layer, "get_bid_doc", lambda pid, b, tenant: bid_row)
    assert doc_context.describe_doc_layer_gap("tp-1", bid_id, "acme") == expected


def test_doc_layer_fallback_emits_user_visible_warning(monkeypatch):
    """掉落 inline 时 ``_resolve_doc_layer`` 必须产出结论级 warning（AC2 核心）。"""
    monkeypatch.setattr(doc_layer, "get_project_doc", lambda pid, tenant: None)
    monkeypatch.setattr(doc_layer, "get_bid_doc", lambda pid, b, tenant: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)

    async def fake_wait(*_a, **_kw):
        return "terminal"

    monkeypatch.setattr(doc_layer, "wait_doc_layer_ready", fake_wait)

    outcome = asyncio.run(doc_context._resolve_doc_layer("tp-1", "bid-a", "acme"))
    text, warnings = outcome.text, outcome.warnings
    assert text is None
    fallback = [w for w in warnings if w["status"] == "doc_layer_fallback"]
    assert len(fallback) == 1, "掉落 inline 必须留下用户可见痕迹"
    assert "tender_doc_absent" in str(fallback[0]["reason"])
    assert "即时 OCR" in str(fallback[0]["message"])


def test_doc_layer_hit_emits_no_fallback_warning(monkeypatch):
    """反向守卫：主链路正常命中时不得凭空报警（否则 warning 会被无视）。"""
    monkeypatch.setattr(
        doc_layer,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿"},
    )
    monkeypatch.setattr(
        doc_layer,
        "get_bid_doc",
        lambda pid, b, tenant: {"bid_id": b, "ocr_status": "ready", "ocr_text": "投标底稿"},
    )
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: "底稿")
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: "底稿")

    async def fake_wait(*_a, **_kw):
        return "terminal"

    monkeypatch.setattr(doc_layer, "wait_doc_layer_ready", fake_wait)

    outcome = asyncio.run(doc_context._resolve_doc_layer("tp-1", "bid-a", "acme"))
    text, warnings = outcome.text, outcome.warnings
    assert text == "底稿"
    assert [w for w in warnings if w["status"] == "doc_layer_fallback"] == []


# ═══════════════════════════════════════════════════════════════════════════
# AC3 · criteria 失败给具体原因
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("criteria", "expected"),
    [
        ("not a dict", "criteria_not_object"),
        ({}, "items_missing"),
        ({"items": "第一项"}, "items_not_array"),
        ({"items": []}, "items_empty"),
        ({"items": ["文本项"]}, "item_not_object"),
        ({"items": [{"max": 10}]}, "item_name_missing"),
        ({"items": [{"item": "  ", "max": 10}]}, "item_name_missing"),
        ({"items": [{"item": "报价", "max": -1}]}, "item_max_invalid"),
        ({"items": [{"item": "报价", "max": float("inf")}]}, "item_max_invalid"),
        ({"items": [{"item": "报价", "max": "十分"}]}, "item_max_invalid"),
        (
            {"items": [{"item": "答辩", "max": None, "score_mode": "manual", "tag": "scored"}]},
            "item_max_invalid",
        ),
        (
            {
                "items": [
                    {
                        "item": "答辩",
                        "max": None,
                        "score_mode": "manual",
                        "tag": "requires_live_event",
                    }
                ]
            },
            "no_numeric_max",
        ),
    ],
)
def test_criteria_usability_problem_names_the_specific_defect(criteria, expected):
    assert criteria_usability_problem(criteria) == expected


def test_criteria_usability_problem_returns_none_when_usable():
    criteria = {
        "items": [
            {"item": "投标报价", "max": 40},
            {"item": "现场答辩", "max": None, "score_mode": "manual", "tag": "requires_live_event"},
        ]
    }
    assert criteria_usability_problem(criteria) is None


# ═══════════════════════════════════════════════════════════════════════════
# AC1 · 提交入口接线：form_json 缺 bid_id 时服务端回查，不再直接掉 inline
# ═══════════════════════════════════════════════════════════════════════════


_TOKEN = "test-fake-token-acme-s1"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def submit_client(monkeypatch):
    """TestClient + 记录 schedule 调用参数的探针。"""
    from fastapi.testclient import TestClient

    import server.api as api_module
    import server.routes.deps as deps_module
    import server.routes.tender.tasks as tasks_module

    monkeypatch.setattr(deps_module, "TENANT_KEYS", {"acme": _TOKEN})
    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    scheduled: dict[str, object] = {}
    monkeypatch.setattr(
        tasks_module, "schedule_tender_evaluation_task", lambda **kwargs: scheduled.update(kwargs)
    )
    return TestClient(api_module.app), scheduled


def test_submit_recovers_bid_id_from_bidder_name(submit_client, monkeypatch):
    """前端漏传 bid_id（提交早于 uploadBid 返回 / 刷新丢内存态）→ 服务端按投标人名回查。"""
    import io
    import json
    import uuid

    client, scheduled = submit_client
    tender_no = f"S1-{uuid.uuid4().hex[:8]}"
    project_id = client.post(
        "/tender/projects", json={"tender_no": tender_no}, headers=_AUTH
    ).json()["project_id"]
    monkeypatch.setattr(
        bid_resolve,
        "list_bid_docs",
        lambda pid, tenant: [{"bid_id": "bid-recovered", "bidder_name": "甲公司"}],
    )

    resp = client.post(
        f"/tender/projects/{project_id}/evaluate",
        data={
            "mode": "upload",
            "form_json": json.dumps({"bidder_name": "甲公司", "bidder_files": ["投标.pdf"]}),
        },
        files=[("files", ("投标.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"))],
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert scheduled["bid_id"] == "bid-recovered", "服务端必须补回 bid_id，否则主链路掉落"


def test_criteria_problem_message_is_human_readable():
    """AC3：原因要透传到任务状态与界面，故必须是可读中文而不是裸枚举。"""
    message = criteria_usability_problem_message("items_empty")
    assert "评分项" in message
    assert "items_empty" in message, "同时保留机器码，便于日志检索"
