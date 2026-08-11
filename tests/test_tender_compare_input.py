"""KD1 判据 / KD3 价格项 / KD4 报价护栏：``server.tender.compare_input`` 的横比输入组装。

锁定四条：
- 可比性只看 ``criteria_ref.version`` 是否等于项目权威版本（快照漂移无关，self_parsed 排除不封池）；
- 价格项与 method 从**权威副本单源**提取，遍历全部 cross-bid 项、非法项跳过继续找（0730 自锁回归）；
- ``bid_price`` 缺失 / 非有限 / ≤0 一律非法，仅缺席该家不封锁其余；数量级差 ≥100 倍整池转人工；
- 比较池按投标人取**最新**一条结论（同家重评不双行入池）。
"""

from __future__ import annotations

import json
import math
import uuid

from server.stores.result_store import archive_result_payload
from server.stores.tender_compare_store import compute_criteria_hash
from server.stores.tender_doc_store import upsert_project_doc
from server.stores.tender_project_store import get_or_create_project
from server.tender.compare_guard import (
    GENERIC_ERROR_DETAIL,
    enforce_compare_guardrails,
    sanitize_error_detail,
)
from server.tender.compare_input import collect_compare_input, find_price_item

TENANT = "acme"


def _criteria(price_max: int | None = 40, *, extra_items: list | None = None) -> dict:
    return {
        "source_ref": "招标文件.pdf 评标办法 p.18",
        "method": "综合评估法",
        "total_max": 100,
        "items": [
            {"item": "技术", "max": 60, "scoring_rule": "技术评分", "source_ref": "p.19",
             "tag": "scored"},
            *(extra_items or []),
            {"item": "价格分", "max": price_max, "scoring_rule": "最低价/本价×40",
             "source_ref": "p.18", "tag": "requires_cross_bid_comparison",
             "score_mode": "formula"},
        ],
    }


def _new_project(criteria: dict | None) -> str:
    project_id = get_or_create_project(
        tenant=TENANT, tender_no=f"R-{uuid.uuid4().hex[:8]}"
    )["project_id"]
    upsert_project_doc(
        project_id=project_id,
        tenant=TENANT,
        tender_files=json.dumps([f"{project_id}.pdf"], ensure_ascii=False),
        criteria=json.dumps(criteria, ensure_ascii=False) if criteria else None,
    )
    return project_id


def _archive_bid(
    project_id: str,
    claim_id: str,
    *,
    amount: float | None = 1000.0,
    criteria: dict | None = None,
    criteria_ref: dict | None = None,
    bid_id: str | None = None,
    created_at: str | None = None,
    scoring: list | None = None,
) -> str:
    request_id = f"bid-{uuid.uuid4().hex[:8]}"
    extracted: dict = {
        "criteria": criteria if criteria is not None else _criteria(),
        "scoring": scoring
        if scoring is not None
        else [{"item": "技术", "max": 60, "score": 50, "status": "scored"}],
    }
    if amount is not None:
        extracted["bid_price"] = {"amount": amount, "currency": "CNY"}
    if criteria_ref is not None:
        extracted["criteria_ref"] = criteria_ref
    archive_result_payload(
        request_id=request_id,
        tenant=TENANT,
        project_id=project_id,
        bid_id=bid_id,
        conversation_id="c1",
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        request_mode="text",
        result_subtype="success",
        cost_usd=0.0,
        prompt_preview="x",
        created_at=created_at,
        response={"verdict": "manual_review", "claim_id": claim_id,
                  "extracted_data": extracted},
    )
    return request_id


def _project_ref(criteria: dict) -> dict:
    return {"version": compute_criteria_hash(criteria), "source": "project"}


def _bidder(compare_input: dict, claim_id: str) -> dict:
    return next(b for b in compare_input["bidders"] if b["claim_id"] == claim_id)


# ── KD1 判据：只看 ref 版本 ─────────────────────────────────────────────────────


def test_same_criteria_version_is_comparable_even_when_snapshot_drifts():
    criteria = _criteria()
    project_id = _new_project(criteria)
    drifted = {**criteria, "items": [*criteria["items"], {"item": "模型多写的项"}]}
    _archive_bid(project_id, "B1", amount=1000.0, criteria=criteria,
                 criteria_ref=_project_ref(criteria))
    _archive_bid(project_id, "B2", amount=1200.0, criteria=drifted,
                 criteria_ref=_project_ref(criteria))

    compare_input, signature = collect_compare_input(TENANT, project_id, {})

    assert compare_input["criteria_version"] == compute_criteria_hash(criteria)
    assert compare_input["price_comparison_blocked"] is False
    assert all(b["comparable"] for b in compare_input["bidders"])
    assert signature.criteria_hash == compute_criteria_hash(criteria)


def test_self_parsed_bidder_is_excluded_but_others_still_compare():
    criteria = _criteria()
    project_id = _new_project(criteria)
    _archive_bid(project_id, "B1", amount=1000.0, criteria_ref=_project_ref(criteria))
    _archive_bid(project_id, "B2", amount=1200.0, criteria_ref=_project_ref(criteria))
    _archive_bid(
        project_id, "B3", amount=1100.0,
        criteria_ref={"version": "deadbeef", "source": "self_parsed"},
    )

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["price_comparison_blocked"] is False
    assert _bidder(compare_input, "B3")["comparable"] is False
    assert _bidder(compare_input, "B3")["exclusion_reason"] == "criteria_stale"
    assert _bidder(compare_input, "B1")["comparable"] is True
    assert any("B3" in warning and "重评" in warning for warning in compare_input["warnings"])


def test_all_self_parsed_blocks_pool_and_names_bidders():
    criteria = _criteria()
    project_id = _new_project(criteria)
    _archive_bid(project_id, "B1", amount=1000.0,
                 criteria_ref={"version": "old1", "source": "self_parsed"})
    _archive_bid(project_id, "B2", amount=1200.0,
                 criteria_ref={"version": "old2", "source": "self_parsed"})

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["price_comparison_blocked"] is True
    assert compare_input["price_comparison_blocked_reason"] == "insufficient_comparable_bidders"
    joined = " ".join(compare_input["warnings"])
    assert "B1" in joined and "B2" in joined


def test_legacy_result_without_criteria_ref_counts_as_self_parsed():
    """存量结论无 ref → 按 self_parsed 处理（排除 + 提示重评），不走旧 hash 判据。"""
    criteria = _criteria()
    project_id = _new_project(criteria)
    _archive_bid(project_id, "B1", amount=1000.0, criteria=criteria)
    _archive_bid(project_id, "B2", amount=1200.0, criteria=criteria)

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["price_comparison_blocked"] is True
    assert compare_input["price_comparison_blocked_reason"] == "insufficient_comparable_bidders"


def test_collect_returns_none_when_pool_under_two():
    criteria = _criteria()
    project_id = _new_project(criteria)
    _archive_bid(project_id, "B1", amount=1000.0, criteria_ref=_project_ref(criteria))
    assert collect_compare_input(TENANT, project_id, {}) is None


def test_missing_authority_criteria_reports_pool_reason_not_price_reason():
    """F3：项目规则未定稿时，封锁原因是「可比家数不足」，不该被价格项短路成 no_price_item。"""
    project_id = _new_project(None)
    _archive_bid(project_id, "B1", amount=1000.0,
                 criteria_ref={"version": "v1", "source": "self_parsed"})
    _archive_bid(project_id, "B2", amount=1200.0,
                 criteria_ref={"version": "v1", "source": "self_parsed"})

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["price_comparison_blocked"] is True
    assert compare_input["price_comparison_blocked_reason"] == "insufficient_comparable_bidders"

    payload = {"bidders": [], "recommended": None, "provisional": True, "warnings": [],
               "explanation": ""}
    enforce_compare_guardrails(payload, compare_input)
    assert all("未找到" not in bidder["note"] for bidder in payload["bidders"])


def test_price_reason_still_reported_when_pool_is_comparable():
    """池可比时价格项原因照常上报（F3 修复不得把价格项三态吃掉）。"""
    criteria = _criteria(price_max=None)
    project_id = _new_project(criteria)
    ref = _project_ref(criteria)
    _archive_bid(project_id, "B1", amount=1000.0, criteria_ref=ref)
    _archive_bid(project_id, "B2", amount=1200.0, criteria_ref=ref)

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["price_comparison_blocked_reason"] == "price_max_unknown"


def test_exclusion_warning_hides_internal_hash():
    """F7：告警面向业务人员，不得把 16 位内容 hash 摆上去。"""
    criteria = _criteria()
    project_id = _new_project(criteria)
    version = compute_criteria_hash(criteria)
    _archive_bid(project_id, "B1", amount=1000.0, criteria_ref=_project_ref(criteria))
    _archive_bid(project_id, "B2", amount=1200.0,
                 criteria_ref={"version": "stale-version", "source": "self_parsed"})
    _archive_bid(project_id, "B3", amount=1100.0, criteria_ref=_project_ref(criteria))

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    joined = " ".join(compare_input["warnings"])
    assert version not in joined
    assert "stale-version" not in joined
    assert "B2" in joined and "重评" in joined


# ── KD3 价格项：权威单源 + 遍历三态 ────────────────────────────────────────────


def test_find_price_item_skips_illegal_and_keeps_searching():
    """0730 自锁回归：首个 cross-bid 项 max=null 时不得提前 return，须继续找到合法价格项。"""
    criteria = _criteria(
        extra_items=[
            {"item": "现场答辩加权", "max": None, "scoring_rule": "现场", "source_ref": "p.20",
             "tag": "requires_cross_bid_comparison", "score_mode": "manual"}
        ]
    )
    item, reason = find_price_item(criteria)
    assert reason is None
    assert item["item"] == "价格分"
    assert item["max"] == 40


def test_find_price_item_reports_price_max_unknown_when_all_illegal():
    criteria = _criteria(price_max=None)
    item, reason = find_price_item(criteria)
    assert item is None
    assert reason == "price_max_unknown"


def test_find_price_item_reports_no_price_item_when_no_cross_bid_tag():
    criteria = _criteria()
    criteria["items"] = criteria["items"][:1]
    item, reason = find_price_item(criteria)
    assert item is None
    assert reason == "no_price_item"


def test_find_price_item_rejects_negative_and_non_finite_max():
    for bad in (-1, math.inf, math.nan, True, "40"):
        criteria = _criteria(price_max=bad)
        assert find_price_item(criteria)[1] == "price_max_unknown"


def test_price_item_and_method_come_from_authority_not_snapshot():
    """ref 同版本但快照漂移时，价格项/method 必须取权威值（否则转录信任 bug 换皮存活）。"""
    criteria = _criteria(price_max=40)
    project_id = _new_project(criteria)
    lying_snapshot = json.loads(json.dumps(criteria))
    lying_snapshot["items"][-1]["max"] = 99
    lying_snapshot["method"] = "其他"
    _archive_bid(project_id, "B1", amount=1000.0, criteria=lying_snapshot,
                 criteria_ref=_project_ref(criteria))
    _archive_bid(project_id, "B2", amount=1200.0, criteria=lying_snapshot,
                 criteria_ref=_project_ref(criteria))

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["criteria_price_item"]["max"] == 40
    assert compare_input["method"] == "综合评估法"


def test_blocked_notes_match_reason():
    """F9：封锁 note 文案必须与 reason 一致，不再硬编码"价格项满分未设"。"""
    payload = {
        "bidders": [{"claim_id": "B1", "price_score": 40, "total_score": 90, "rank": 1,
                     "status": "scored"}],
        "recommended": "B1", "provisional": False, "warnings": [], "explanation": "B1 第一",
    }
    compare_input = {
        "price_comparison_blocked": True,
        "price_comparison_blocked_reason": "no_price_item",
        "warnings": [],
        "bidders": [{"claim_id": "B1", "bid_price": {"amount": 1000, "currency": "CNY"},
                     "comparable": True, "exclusion_reason": None}],
    }

    enforce_compare_guardrails(payload, compare_input)

    assert payload["recommended"] is None
    assert payload["provisional"] is True
    bidder = payload["bidders"][0]
    assert bidder["status"] == "manual_review"
    assert bidder["rank"] is None and bidder["total_score"] is None
    assert "未找到" in bidder["note"] and "满分未设" not in bidder["note"]


def test_excluded_bidder_is_forced_manual_while_pool_still_ranks():
    payload = {
        "bidders": [
            {"claim_id": "B1", "price_score": 40, "total_score": 90, "rank": 1,
             "status": "scored"},
            {"claim_id": "B2", "price_score": 30, "total_score": 80, "rank": 2,
             "status": "scored"},
        ],
        "recommended": None, "provisional": True, "warnings": [], "explanation": "排名",
    }
    compare_input = {
        "price_comparison_blocked": False,
        "price_comparison_blocked_reason": None,
        "warnings": ["投标人「B2」的报价数据无效"],
        "bidders": [
            {"claim_id": "B1", "bid_price": {"amount": 1000}, "comparable": True,
             "exclusion_reason": None},
            {"claim_id": "B2", "bid_price": None, "comparable": False,
             "exclusion_reason": "bid_price_invalid"},
        ],
    }

    enforce_compare_guardrails(payload, compare_input)

    by_claim = {b["claim_id"]: b for b in payload["bidders"]}
    assert by_claim["B1"]["rank"] == 1 and by_claim["B1"]["status"] == "scored"
    assert by_claim["B2"]["status"] == "manual_review"
    assert by_claim["B2"]["rank"] is None and by_claim["B2"]["price_score"] is None
    assert "报价" in by_claim["B2"]["note"]
    assert "投标人「B2」的报价数据无效" in payload["warnings"]


# ── KD4 报价护栏 + 池去重 ──────────────────────────────────────────────────────


def test_missing_bid_price_excludes_only_that_bidder():
    criteria = _criteria()
    project_id = _new_project(criteria)
    ref = _project_ref(criteria)
    _archive_bid(project_id, "B1", amount=1000.0, criteria_ref=ref)
    _archive_bid(project_id, "B2", amount=1200.0, criteria_ref=ref)
    _archive_bid(project_id, "B3", amount=None, criteria_ref=ref)

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["price_comparison_blocked"] is False
    assert _bidder(compare_input, "B3")["exclusion_reason"] == "bid_price_invalid"
    assert _bidder(compare_input, "B1")["comparable"] is True
    assert any("B3" in warning for warning in compare_input["warnings"])


def test_zero_and_negative_and_non_finite_bid_price_are_invalid():
    criteria = _criteria()
    ref = _project_ref(criteria)
    for bad in (0, -5, math.inf, math.nan):
        project_id = _new_project(criteria)
        _archive_bid(project_id, "B1", amount=1000.0, criteria_ref=ref)
        _archive_bid(project_id, "B2", amount=1200.0, criteria_ref=ref)
        _archive_bid(project_id, "BAD", amount=bad, criteria_ref=ref)

        compare_input, _sig = collect_compare_input(TENANT, project_id, {})

        assert _bidder(compare_input, "BAD")["exclusion_reason"] == "bid_price_invalid", bad


def test_magnitude_gap_blocks_pool_as_unit_mismatch():
    criteria = _criteria()
    project_id = _new_project(criteria)
    ref = _project_ref(criteria)
    _archive_bid(project_id, "B1", amount=1200.0, criteria_ref=ref)  # 万元口径
    _archive_bid(project_id, "B2", amount=12_000_000.0, criteria_ref=ref)  # 元口径

    compare_input, _sig = collect_compare_input(TENANT, project_id, {})

    assert compare_input["price_comparison_blocked"] is True
    assert compare_input["price_comparison_blocked_reason"] == "bid_price_unit_mismatch"
    assert any("单位" in warning for warning in compare_input["warnings"])


def test_pool_keeps_only_latest_result_per_bidder():
    criteria = _criteria()
    project_id = _new_project(criteria)
    ref = _project_ref(criteria)
    _archive_bid(project_id, "B1", amount=1000.0, criteria_ref=ref, bid_id="bd-1",
                 created_at="2026-08-01T00:00:00+00:00")
    latest = _archive_bid(project_id, "B1", amount=1050.0, criteria_ref=ref, bid_id="bd-1",
                          created_at="2026-08-02T00:00:00+00:00")
    _archive_bid(project_id, "B2", amount=1200.0, criteria_ref=ref, bid_id="bd-2",
                 created_at="2026-08-01T00:00:00+00:00")

    compare_input, signature = collect_compare_input(TENANT, project_id, {})

    assert len(compare_input["bidders"]) == 2
    assert _bidder(compare_input, "B1")["bid_price"]["amount"] == 1050.0
    assert latest in signature.input_result_ids


# ── 错误详情脱敏（KD2 GET 透传前的边界处理）────────────────────────────────────


def test_sanitize_error_detail_passes_known_business_reason():
    """已知业务异常（服务端自己抛的、面向用户的话）原文透出。"""
    raw = (
        'Traceback (most recent call last):\n'
        '  File "/Users/someone/workspace/server/tender/compare_worker.py", line 12, in run\n'
        "ValueError: 参与横比的已完成投标人不足 2 家"
    )
    cleaned = sanitize_error_detail(raw)
    assert cleaned == "参与横比的已完成投标人不足 2 家"


def test_sanitize_error_detail_masks_unknown_internal_errors():
    """F6 白名单：未知内部异常一律固定文案，不透任何内部信息。"""
    raw = (
        'Traceback (most recent call last):\n'
        '  File "/Users/someone/workspace/server/tender/compare_worker.py", line 12, in run\n'
        "sqlite3.OperationalError: no such column: tender_compare_results.foo"
    )
    cleaned = sanitize_error_detail(raw)
    assert cleaned == GENERIC_ERROR_DETAIL
    assert "sqlite3" not in cleaned
    assert "/Users/someone" not in cleaned


def test_sanitize_error_detail_masks_credentials_even_in_known_reason():
    """凭证兜底：任何形态的密钥/令牌都不得随错误文案出网。"""
    for secret in (
        "Bearer abcdef123456",
        "sk-live-0123456789abcdef",
        "api_key=ZZZTOPSECRET",
        "api-key: ZZZTOPSECRET",
        "token=ZZZTOPSECRET",
    ):
        cleaned = sanitize_error_detail(f"参与横比的已完成投标人不足 2 家（{secret}）")
        assert "ZZZTOPSECRET" not in cleaned, secret
        assert "abcdef123456" not in cleaned, secret
        assert "0123456789abcdef" not in cleaned, secret


def test_sanitize_error_detail_logs_full_detail_server_side(caplog):
    """被屏蔽的详情必须进服务端日志，否则等于把线索一起丢了。"""
    with caplog.at_level("WARNING", logger="server.tender.compare_guard"):
        sanitize_error_detail("sqlite3.OperationalError: disk I/O error")
    assert "disk I/O error" in caplog.text


def test_sanitize_error_detail_handles_blank():
    assert sanitize_error_detail(None) == ""
    assert sanitize_error_detail("") == ""
