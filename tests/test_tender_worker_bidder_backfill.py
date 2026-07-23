"""X2：tender worker completed 分支挂靠 _backfill_bidder_name（仿 _backfill_criteria 先例）。

覆盖：
- 直调 _backfill_bidder_name：成功路径调用 tender_doc_store 回填；异常不崩主流程。
- _execute_inner completed 分支：payload 带 bidder_info 时触发回填，写入正确的
  project_id/bid_id/tenant/bidder_name。
- bid_id=None（散单/非 prewarm）退化：不调回填，不崩。
- payload 无 bidder_info：跳过，不崩。
"""

from __future__ import annotations

import asyncio

import server.tender.worker as tw


def _fake_meta():
    class _Meta:
        result_file = "logs/test-result.json"
        claude_session_id = "sess-test"

    return _Meta()


def test_backfill_bidder_name_calls_store_on_success(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        tw,
        "backfill_bid_doc_bidder_name",
        lambda pid, bid, tenant, name: captured.update(
            {"project_id": pid, "bid_id": bid, "tenant": tenant, "bidder_name": name}
        ),
    )
    tw._backfill_bidder_name("tp-1", "bd-1", "acme", "某某建设工程有限公司")
    assert captured == {
        "project_id": "tp-1",
        "bid_id": "bd-1",
        "tenant": "acme",
        "bidder_name": "某某建设工程有限公司",
    }


def test_backfill_bidder_name_swallows_store_exception(monkeypatch):
    def _boom(*_a, **_kw):
        raise RuntimeError("db locked")

    monkeypatch.setattr(tw, "backfill_bid_doc_bidder_name", _boom)
    # 不抛：异常不崩主流程（评标 completed 状态机不受回填失败影响）。
    tw._backfill_bidder_name("tp-1", "bd-1", "acme", "某某建设工程有限公司")


def test_backfill_bidder_name_skips_without_project_or_bid_id(monkeypatch):
    calls: list = []
    monkeypatch.setattr(tw, "backfill_bid_doc_bidder_name", lambda *a, **k: calls.append(a))
    tw._backfill_bidder_name(None, "bd-1", "acme", "名称")
    tw._backfill_bidder_name("tp-1", None, "acme", "名称")
    assert calls == []


def test_backfill_bidder_name_skips_without_name(monkeypatch):
    calls: list = []
    monkeypatch.setattr(tw, "backfill_bid_doc_bidder_name", lambda *a, **k: calls.append(a))
    tw._backfill_bidder_name("tp-1", "bd-1", "acme", None)
    assert calls == []


def test_execute_inner_completed_triggers_bidder_name_backfill(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(tw, "upsert_tender_task", lambda payload: None)
    monkeypatch.setattr(tw, "update_tender_progress", lambda *a, **k: None)
    monkeypatch.setattr(tw, "get_project_doc", lambda *_a, **_kw: {"criteria": "x"})
    monkeypatch.setattr(tw, "update_project_doc_criteria", lambda *a, **k: None)
    monkeypatch.setattr(
        tw,
        "_backfill_bidder_name",
        lambda pid, bid, tenant, name: captured.update(
            {"project_id": pid, "bid_id": bid, "tenant": tenant, "bidder_name": name}
        ),
    )

    async def _fake_run_evaluation(**kwargs):
        return (
            {
                "verdict": "approved",
                "extracted_data": {"bidder_info": {"bidder_name": "某某建设工程有限公司"}},
            },
            _fake_meta(),
        )

    monkeypatch.setattr(tw, "_run_evaluation", _fake_run_evaluation)

    asyncio.run(
        tw._execute_inner(
            request_id="r-backfill-wire",
            tenant="acme",
            directory_path="/tmp/case",
            source_mode="directory",
            project_id="tp-wire",
            bid_id="bd-wire",
        )
    )
    assert captured == {
        "project_id": "tp-wire",
        "bid_id": "bd-wire",
        "tenant": "acme",
        "bidder_name": "某某建设工程有限公司",
    }


def test_execute_inner_without_bid_id_degrades_safely(monkeypatch):
    """散单 / 非 prewarm：bid_id=None → 不调回填，不崩（退化路径）。"""
    calls: list = []
    monkeypatch.setattr(tw, "upsert_tender_task", lambda payload: None)
    monkeypatch.setattr(tw, "update_tender_progress", lambda *a, **k: None)
    monkeypatch.setattr(tw, "_backfill_bidder_name", lambda *a, **k: calls.append(a))

    async def _fake_run_evaluation(**kwargs):
        return (
            {
                "verdict": "approved",
                "extracted_data": {"bidder_info": {"bidder_name": "某某建设工程有限公司"}},
            },
            _fake_meta(),
        )

    monkeypatch.setattr(tw, "_run_evaluation", _fake_run_evaluation)

    asyncio.run(
        tw._execute_inner(
            request_id="r-no-bid-id",
            tenant="acme",
            directory_path="/tmp/case",
            source_mode="directory",
        )
    )
    assert calls == []


def test_execute_inner_without_bidder_info_skips_backfill(monkeypatch):
    """无 bidder_info 时 completed 分支仍可挂靠调用，但 _backfill_bidder_name 内部对
    bidder_name=None 早退（同 _backfill_criteria 对空 criteria 的既有纪律），底层
    store 写入函数不应被触发。"""
    calls: list = []
    monkeypatch.setattr(tw, "upsert_tender_task", lambda payload: None)
    monkeypatch.setattr(tw, "update_tender_progress", lambda *a, **k: None)
    monkeypatch.setattr(tw, "backfill_bid_doc_bidder_name", lambda *a, **k: calls.append(a))

    async def _fake_run_evaluation(**kwargs):
        return ({"verdict": "approved", "extracted_data": {}}, _fake_meta())

    monkeypatch.setattr(tw, "_run_evaluation", _fake_run_evaluation)

    asyncio.run(
        tw._execute_inner(
            request_id="r-no-bidder-info",
            tenant="acme",
            directory_path="/tmp/case",
            source_mode="directory",
            project_id="tp-x",
            bid_id="bd-x",
        )
    )
    assert calls == []
