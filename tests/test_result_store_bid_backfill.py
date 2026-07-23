"""X2: results 归档链 bid_id + bidder_name 拍平（design A3.1）。

TDD：先写测试锁 ResultRecord 新字段 + archive_result_payload 拍平逻辑，覆盖：
- archive → list_results_by_project 读回非空（防 slots-dataclass 白名单静默丢字段）。
- archive → get_record_by_request_id 读回非空。
- bid_id=None（散单/非 prewarm 场景）不崩，字段留空。
- 无 extracted_data.bidder_info 时 bidder_name 留空，不报错。
"""

from __future__ import annotations

import uuid

from server.stores.result_store import (
    archive_result_payload,
    get_result_record_by_request_id,
    list_results_by_project,
)
from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME as EVAL_SCHEMA


def _rid() -> str:
    return f"r-{uuid.uuid4().hex[:16]}"


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _archive(*, request_id, tenant, project_id, bid_id, response):
    return archive_result_payload(
        request_id=request_id,
        tenant=tenant,
        project_id=project_id,
        bid_id=bid_id,
        conversation_id="c1",
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=EVAL_SCHEMA,
        request_mode="structured",
        result_subtype="success",
        cost_usd=0.0,
        prompt_preview="x",
        response=response,
    )


def test_archive_flattens_bid_id_and_bidder_name_roundtrip_by_project():
    """archive → list_results_by_project 读回 bid_id + bidder_name 非空（往返测试）。"""
    rid = _rid()
    pid = _pid()
    record = _archive(
        request_id=rid,
        tenant="acme",
        project_id=pid,
        bid_id="bd-0001",
        response={
            "verdict": "approved",
            "claim_id": "BID-A",
            "extracted_data": {"bidder_info": {"bidder_name": "某某建设工程有限公司"}},
        },
    )
    assert record.bid_id == "bd-0001"
    assert record.bidder_name == "某某建设工程有限公司"

    rows = list_results_by_project("acme", pid)
    row = next(r for r in rows if r["request_id"] == rid)
    assert row["bid_id"] == "bd-0001"
    assert row["bidder_name"] == "某某建设工程有限公司"


def test_archive_flattens_bid_id_and_bidder_name_roundtrip_by_request_id():
    """archive → get_result_record_by_request_id 读回非空（同一往返测试的另一路径）。"""
    rid = _rid()
    pid = _pid()
    _archive(
        request_id=rid,
        tenant="acme",
        project_id=pid,
        bid_id="bd-0002",
        response={
            "verdict": "approved",
            "claim_id": "BID-B",
            "extracted_data": {"bidder_info": {"bidder_name": "华远建设"}},
        },
    )
    row = get_result_record_by_request_id(rid, "acme")
    assert row is not None
    assert row["bid_id"] == "bd-0002"
    assert row["bidder_name"] == "华远建设"


def test_archive_without_bid_id_degrades_safely():
    """bid_id=None（散单 / 非 prewarm 场景）：字段留空，不崩。"""
    rid = _rid()
    record = _archive(
        request_id=rid,
        tenant="acme",
        project_id=None,
        bid_id=None,
        response={"verdict": "approved", "claim_id": "BID-C"},
    )
    assert record.bid_id is None
    row = get_result_record_by_request_id(rid, "acme")
    assert row is not None
    assert row["bid_id"] is None
    assert row["bidder_name"] is None


def test_archive_without_bidder_info_leaves_bidder_name_none():
    """无 extracted_data.bidder_info 时 bidder_name 留空，不报错（agent 未识别到时不编造）。"""
    rid = _rid()
    record = _archive(
        request_id=rid,
        tenant="acme",
        project_id=_pid(),
        bid_id="bd-0003",
        response={"verdict": "manual_review", "claim_id": "BID-D", "extracted_data": {}},
    )
    assert record.bid_id == "bd-0003"
    assert record.bidder_name is None
