"""TDD tests for tender P3 backend tasks:

A. criteria 项目级回填 (tender_worker post-evaluation backfill):
   - 评标 completed 后, payload.extracted_data.criteria 存在时回填到招标层。
   - 首个写入者赢: 已存非空则不覆盖。
   - project_id 为 None (散单) 跳过。
   - 异常不崩评标主流程 (try/except + log)。

B. delete 级联 (tender_project_store.delete_project_cascade):
   - 同时删 tender_project_docs (project_id) 行。
   - 同时删 tender_bid_docs (project_id) 行。
   - 避免孤儿数据。
"""

from __future__ import annotations

import json
import uuid

def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _bid_id() -> str:
    return f"bd-{uuid.uuid4().hex[:16]}"


# ── A. criteria 项目级回填 ─────────────────────────────────────────────────────

SAMPLE_CRITERIA = {
    "source_ref": "招标文件第三章 p.18",
    "method": "综合评估法",
    "total_max": 100,
    "items": [
        {
            "item": "技术方案",
            "max": 60,
            "scoring_rule": "按技术规格响应程度评分",
            "source_ref": "第三章 p.19",
            "tag": "scored",
        }
    ],
}


def test_criteria_backfill_writes_when_none(monkeypatch):
    """评标 completed + criteria in payload → 写入招标层 (当前为空)。"""
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.routes.tender_worker import _backfill_criteria

    pid = _pid()
    tenant = "t-crit-a"
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]")
    assert get_project_doc(pid, tenant)["criteria"] is None

    _backfill_criteria(pid, tenant, SAMPLE_CRITERIA)

    row = get_project_doc(pid, tenant)
    assert row is not None
    stored = json.loads(row["criteria"])
    assert stored["method"] == "综合评估法"
    assert stored["items"][0]["item"] == "技术方案"


def test_criteria_backfill_first_writer_wins(monkeypatch):
    """首个写入者赢: criteria 已存在时不覆盖。"""
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_criteria,
        upsert_project_doc,
    )
    from server.routes.tender_worker import _backfill_criteria

    pid = _pid()
    tenant = "t-crit-b"
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]")

    original_criteria = {"source_ref": "original", "method": "original_method", "total_max": 50, "items": []}
    update_project_doc_criteria(pid, tenant, json.dumps(original_criteria))

    # 尝试用新 criteria 覆盖 → 应不覆盖
    new_criteria = {"source_ref": "new", "method": "new_method", "total_max": 100, "items": []}
    _backfill_criteria(pid, tenant, new_criteria)

    row = get_project_doc(pid, tenant)
    stored = json.loads(row["criteria"])
    # 应保留原来的 (首个赢)
    assert stored["method"] == "original_method"


def test_criteria_backfill_skips_none_project_id():
    """project_id 为 None (散单) 时直接跳过, 不抛异常。"""
    from server.routes.tender_worker import _backfill_criteria

    # 不应抛任何异常
    _backfill_criteria(None, "any-tenant", SAMPLE_CRITERIA)


def test_criteria_backfill_skips_empty_criteria():
    """criteria 为 None 或空时跳过 (无需回填)。"""
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.routes.tender_worker import _backfill_criteria

    pid = _pid()
    tenant = "t-crit-c"
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]")

    _backfill_criteria(pid, tenant, None)

    row = get_project_doc(pid, tenant)
    assert row["criteria"] is None  # 没写入任何东西


def test_criteria_backfill_does_not_crash_on_exception(monkeypatch):
    """DB 异常时不应崩评标主流程: _backfill_criteria 吞掉异常、仅 log。"""
    import server.routes.tender_worker as worker_mod
    from server.routes.tender_worker import _backfill_criteria

    call_count = {"n": 0}

    def _boom(project_id, tenant):
        call_count["n"] += 1
        raise RuntimeError("simulated DB error")

    # patch the name as imported in the worker module
    monkeypatch.setattr(worker_mod, "get_project_doc", _boom)

    # 不应 raise, 主流程继续
    _backfill_criteria("fake-pid", "fake-tenant", SAMPLE_CRITERIA)
    assert call_count["n"] == 1  # 确实调到了 get_project_doc


def test_criteria_backfill_skips_project_not_in_db():
    """project_id 存在但招标层记录不存在时安全跳过。"""
    from server.routes.tender_worker import _backfill_criteria

    # 没有预先创建 project doc → 应安全跳过
    _backfill_criteria(_pid(), "no-such-tenant", SAMPLE_CRITERIA)


# ── B. delete 级联清两新表 ──────────────────────────────────────────────────────


def test_delete_project_cascade_removes_project_docs():
    """delete_project_cascade 同时删 tender_project_docs 行。"""
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import (
        delete_project_cascade,
        get_or_create_project,
    )

    tenant = "t-cas-a"
    pid = get_or_create_project(tenant=tenant, tender_no=f"DEL-A-{uuid.uuid4().hex[:8]}")["project_id"]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
    assert get_project_doc(pid, tenant) is not None

    outcome = delete_project_cascade(pid, tenant)
    assert outcome is not None

    # tender_project_docs 行应已删除
    assert get_project_doc(pid, tenant) is None


def test_delete_project_cascade_removes_bid_docs():
    """delete_project_cascade 同时删 tender_bid_docs 行 (含多行)。"""
    from server.stores.tender_doc_store import list_bid_docs, upsert_bid_doc
    from server.stores.tender_project_store import (
        delete_project_cascade,
        get_or_create_project,
    )

    tenant = "t-cas-b"
    pid = get_or_create_project(tenant=tenant, tender_no=f"DEL-B-{uuid.uuid4().hex[:8]}")["project_id"]

    for i in range(3):
        upsert_bid_doc(
            project_id=pid,
            bid_id=_bid_id(),
            tenant=tenant,
            bidder_name=f"公司{i}",
            bid_files="[]",
            ocr_status="ready",
        )
    assert len(list_bid_docs(pid, tenant)) == 3

    outcome = delete_project_cascade(pid, tenant)
    assert outcome is not None

    # tender_bid_docs 行应全部删除
    assert list_bid_docs(pid, tenant) == []


def test_delete_project_cascade_counts_include_new_tables():
    """delete_project_cascade 返回的 deleted 字段包含 tender_project_docs / tender_bid_docs 行数。"""
    from server.stores.tender_doc_store import upsert_bid_doc, upsert_project_doc
    from server.stores.tender_project_store import (
        delete_project_cascade,
        get_or_create_project,
    )

    tenant = "t-cas-c"
    pid = get_or_create_project(tenant=tenant, tender_no=f"DEL-C-{uuid.uuid4().hex[:8]}")["project_id"]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]")
    upsert_bid_doc(project_id=pid, bid_id=_bid_id(), tenant=tenant,
                   bidder_name="甲", bid_files="[]")
    upsert_bid_doc(project_id=pid, bid_id=_bid_id(), tenant=tenant,
                   bidder_name="乙", bid_files="[]")

    outcome = delete_project_cascade(pid, tenant)
    assert outcome is not None
    deleted = outcome["deleted"]

    # 两新表的删行数应在返回值中
    assert deleted.get("tender_project_docs", 0) == 1
    assert deleted.get("tender_bid_docs", 0) == 2


def test_delete_project_cascade_no_orphans_after_delete():
    """删项目后, 另一项目的 project_docs / bid_docs 不受影响 (无跨项目孤儿清理)。"""
    from server.stores.tender_doc_store import get_project_doc, list_bid_docs, upsert_bid_doc, upsert_project_doc
    from server.stores.tender_project_store import (
        delete_project_cascade,
        get_or_create_project,
    )

    tenant = "t-cas-d"
    pid_a = get_or_create_project(tenant=tenant, tender_no=f"DEL-D-A-{uuid.uuid4().hex[:8]}")["project_id"]
    pid_b = get_or_create_project(tenant=tenant, tender_no=f"DEL-D-B-{uuid.uuid4().hex[:8]}")["project_id"]

    upsert_project_doc(project_id=pid_a, tenant=tenant, tender_files="[]")
    bid_b_id = _bid_id()
    upsert_project_doc(project_id=pid_b, tenant=tenant, tender_files="[]")
    upsert_bid_doc(project_id=pid_b, bid_id=bid_b_id, tenant=tenant,
                   bidder_name="乙方", bid_files="[]")

    # 只删 A
    delete_project_cascade(pid_a, tenant)

    # B 的数据完好
    assert get_project_doc(pid_b, tenant) is not None
    assert len(list_bid_docs(pid_b, tenant)) == 1


def test_delete_project_cascade_returns_none_for_nonexistent():
    """不存在的项目 → 返回 None (不抛异常)。"""
    from server.stores.tender_project_store import delete_project_cascade

    result = delete_project_cascade("nonexistent-pid", "any-tenant")
    assert result is None
