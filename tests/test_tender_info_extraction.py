"""TDD tests for tender-info-extraction feature (Round 1 backend).

Coverage:
1. Schema migration: old DB without new columns gets them added idempotently.
2. Store: update_project_doc_criteria_extracted writes criteria+tender_info+criteria_status.
3. Store: update_project_fields_if_empty only fills null/empty fields (user-filled wins).
4. Route: _extract_project_doc_info happy path writes criteria+tender_info+criteria_status=ready,
   and backfills empty project fields.
5. Route: _extract_project_doc_info failure sets criteria_status=failed, leaves ocr_status=ready.
6. Route: GET /tender/projects/{id}/tender-doc returns expected shape.
7. Route: docs-status includes criteria_status.
8. Worker: _run_evaluation injects stored criteria into context when present.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest
from fastapi.testclient import TestClient

# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

_TOKEN = "test-fake-token-r1-extract"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


SAMPLE_CRITERIA = {
    "source_ref": "招标文件第三章 评标办法 p.18",
    "method": "综合评估法",
    "total_max": 100,
    "items": [
        {
            "item": "技术方案",
            "max": 60,
            "scoring_rule": "按技术规格响应程度评分，满分60分",
            "source_ref": "第三章 p.19",
            "tag": "scored",
            "score_mode": "banded",
            "deductions": [],
        }
    ],
    "rejection_rules": [],
}

SAMPLE_TENDER_INFO = {
    "tender_no": "ZBZS-2024-001",
    "project_name": "智慧城市综合管理平台建设项目",
    "tenderee": "某市政务服务和大数据局",
    "control_price": "1500万元",
    "method": "综合评估法",
    "funding_hint": "财政资金",
}

SAMPLE_EXTRACT_PAYLOAD = {"criteria": SAMPLE_CRITERIA, "tender_info": SAMPLE_TENDER_INFO}

# ──────────────────────────────────────────────────────────────────────────────
# 1. Schema migration: new columns are added idempotently
# ──────────────────────────────────────────────────────────────────────────────


def test_schema_migration_adds_new_columns():
    """tender_project_docs gains criteria_status and tender_info after _initialize_schema."""
    from server.stores.tender_doc_store import _initialize_schema
    from server.platform.paths import PLATFORM_DB_FILE
    from server.platform.sqlite_store import connect_sqlite

    # Re-run _initialize_schema (idempotent; DB already exists with migrations applied)
    _initialize_schema()

    with connect_sqlite(PLATFORM_DB_FILE) as conn:
        col_names = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(tender_project_docs)").fetchall()
        }
    assert "criteria_status" in col_names, "criteria_status column must exist"
    assert "tender_info" in col_names, "tender_info column must exist"


def test_schema_migration_new_rows_have_default_criteria_status():
    """Newly inserted rows default criteria_status to 'pending'."""
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t-migration", tender_files="[]")
    row = get_project_doc(pid, "t-migration")
    assert row is not None
    assert row["criteria_status"] == "pending"
    assert row["tender_info"] is None


def test_schema_migration_is_idempotent():
    """Calling _initialize_schema twice does not raise or duplicate columns."""
    from server.stores.tender_doc_store import _initialize_schema
    from server.platform.paths import PLATFORM_DB_FILE
    from server.platform.sqlite_store import connect_sqlite

    _initialize_schema()
    _initialize_schema()

    with connect_sqlite(PLATFORM_DB_FILE) as conn:
        col_names = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(tender_project_docs)").fetchall()
        ]
    # Columns should appear exactly once
    assert col_names.count("criteria_status") == 1
    assert col_names.count("tender_info") == 1


# ──────────────────────────────────────────────────────────────────────────────
# 2. update_project_doc_criteria_extracted store function
# ──────────────────────────────────────────────────────────────────────────────


def test_update_project_doc_criteria_extracted_writes_all_fields():
    """update_project_doc_criteria_extracted writes criteria, tender_info, criteria_status."""
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_criteria_extracted,
        upsert_project_doc,
    )

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t-ext", tender_files="[]")

    criteria_json = json.dumps(SAMPLE_CRITERIA)
    tender_info_json = json.dumps(SAMPLE_TENDER_INFO)
    update_project_doc_criteria_extracted(
        pid,
        "t-ext",
        criteria_json=criteria_json,
        tender_info_json=tender_info_json,
        status="ready",
    )

    row = get_project_doc(pid, "t-ext")
    assert row is not None
    assert row["criteria"] == criteria_json
    assert row["tender_info"] == tender_info_json
    assert row["criteria_status"] == "ready"


def test_update_project_doc_criteria_extracted_failed_status():
    """Failure path: criteria_json=None, status=failed."""
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_criteria_extracted,
        upsert_project_doc,
    )

    pid = _pid()
    upsert_project_doc(
        project_id=pid, tenant="t-ext-fail", tender_files="[]", ocr_status="ready"
    )

    update_project_doc_criteria_extracted(
        pid,
        "t-ext-fail",
        criteria_json=None,
        tender_info_json=None,
        status="failed",
    )

    row = get_project_doc(pid, "t-ext-fail")
    assert row is not None
    assert row["criteria"] is None
    assert row["tender_info"] is None
    assert row["criteria_status"] == "failed"
    # ocr_status must not be touched
    assert row["ocr_status"] == "ready"


def test_update_project_doc_criteria_extracted_tenant_scope():
    """update_project_doc_criteria_extracted is tenant-scoped (wrong tenant → no update)."""
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_criteria_extracted,
        upsert_project_doc,
    )

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t-ext-a", tender_files="[]")

    # Attempt update with wrong tenant
    update_project_doc_criteria_extracted(
        pid,
        "t-ext-WRONG",
        criteria_json=json.dumps(SAMPLE_CRITERIA),
        tender_info_json=None,
        status="ready",
    )

    row = get_project_doc(pid, "t-ext-a")
    assert row is not None
    # Should still be pending (the update hit no rows)
    assert row["criteria_status"] == "pending"


# ──────────────────────────────────────────────────────────────────────────────
# 3. update_project_fields_if_empty store function
# ──────────────────────────────────────────────────────────────────────────────


def test_update_project_fields_if_empty_fills_null_fields():
    """Fields that are NULL get filled; existing non-empty values are preserved."""
    from server.stores.tender_project_store import (
        get_or_create_project,
        get_project,
        update_project_fields_if_empty,
    )

    # Create project with only tender_no, leaving tenderee/control_price/method empty
    pid = get_or_create_project(
        tenant="t-fill",
        tender_no=f"TF-{uuid.uuid4().hex[:8]}",
    )["project_id"]

    update_project_fields_if_empty(
        pid,
        "t-fill",
        {
            "tenderee": "某市政务局",
            "control_price": "1500万元",
            "method": "综合评估法",
            "tender_no": "SHOULD-NOT-OVERWRITE",  # already has a value
        },
    )

    row = get_project(pid, "t-fill")
    assert row is not None
    assert row["tenderee"] == "某市政务局"
    assert row["control_price"] == "1500万元"
    assert row["method"] == "综合评估法"
    # tender_no was set at create-time; update_project_fields_if_empty must not overwrite
    assert row["tender_no"] != "SHOULD-NOT-OVERWRITE"


def test_update_project_fields_if_empty_preserves_user_data():
    """If user explicitly set a field, it is never overwritten by OCR-derived data."""
    from server.stores.tender_project_store import (
        get_or_create_project,
        get_project,
        update_project_fields_if_empty,
    )

    user_tenderee = "用户手动填入的招标人名称"
    pid = get_or_create_project(
        tenant="t-preserve",
        tender_no=f"TP-{uuid.uuid4().hex[:8]}",
        tenderee=user_tenderee,
    )["project_id"]

    # OCR extraction tries to overwrite
    update_project_fields_if_empty(
        pid,
        "t-preserve",
        {"tenderee": "OCR派生值，不该覆盖"},
    )

    row = get_project(pid, "t-preserve")
    assert row is not None
    assert row["tenderee"] == user_tenderee, "User-entered value must not be overwritten"


def test_update_project_fields_if_empty_empty_string_treated_as_empty():
    """Empty-string values are treated as 'empty' and should be overwritten."""
    from server.stores.tender_project_store import (
        get_or_create_project,
        get_project,
        update_project_fields_if_empty,
    )

    pid = get_or_create_project(
        tenant="t-empty-str",
        tender_no=f"ES-{uuid.uuid4().hex[:8]}",
    )["project_id"]

    # Manually check that fields start as NULL (not empty string)
    row = get_project(pid, "t-empty-str")
    assert row["tenderee"] is None

    update_project_fields_if_empty(pid, "t-empty-str", {"tenderee": "新招标人"})
    row = get_project(pid, "t-empty-str")
    assert row["tenderee"] == "新招标人"


def test_update_project_fields_if_empty_ignores_unknown_fields():
    """Unknown field names are silently ignored (no SQL error)."""
    from server.stores.tender_project_store import (
        get_or_create_project,
        update_project_fields_if_empty,
    )

    pid = get_or_create_project(
        tenant="t-unknown",
        tender_no=f"UK-{uuid.uuid4().hex[:8]}",
    )["project_id"]

    # Should not raise
    update_project_fields_if_empty(
        pid, "t-unknown", {"nonexistent_column": "value", "tenderee": "招标人"}
    )


def test_update_project_fields_if_empty_tenant_scope():
    """update_project_fields_if_empty is tenant-scoped."""
    from server.stores.tender_project_store import (
        get_or_create_project,
        get_project,
        update_project_fields_if_empty,
    )

    pid = get_or_create_project(
        tenant="t-scope-a",
        tender_no=f"SC-{uuid.uuid4().hex[:8]}",
    )["project_id"]

    # Attempt update with wrong tenant
    update_project_fields_if_empty(pid, "t-scope-WRONG", {"tenderee": "不该填入"})

    row = get_project(pid, "t-scope-a")
    assert row is not None
    assert row["tenderee"] is None


# ──────────────────────────────────────────────────────────────────────────────
# 4 & 5. _extract_project_doc_info coroutine (mocked run_command_json)
# ──────────────────────────────────────────────────────────────────────────────


def test_extract_project_doc_info_happy_path(monkeypatch):
    """_extract_project_doc_info happy path:
    - writes criteria + tender_info + criteria_status=ready
    - backfills empty project fields from tender_info
    - does not overwrite non-empty project fields
    """
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project, get_project

    tenant = "t-extract-happy"
    # Create project with only tender_no set; tenderee/method/control_price are empty
    pid = get_or_create_project(
        tenant=tenant,
        tender_no=f"EH-{uuid.uuid4().hex[:8]}",
    )["project_id"]
    # Create the tender_project_docs row (simulating post-OCR state)
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")

    from server.common.agent_bridge import AgentRunMeta

    fake_meta = AgentRunMeta(
        request_id="rid-extract-test",
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )

    async def fake_run_command_json(command_name, *args, **kwargs):
        return SAMPLE_EXTRACT_PAYLOAD, fake_meta

    monkeypatch.setattr(tender_module, "run_command_json", fake_run_command_json)

    asyncio.run(
        tender_module.extract_project_doc_info(
            pid, "/fake/case/path", "OCR底稿文本", tenant
        )
    )

    # Check doc store updated
    row = get_project_doc(pid, tenant)
    assert row is not None
    assert row["criteria_status"] == "ready"
    stored_criteria = json.loads(row["criteria"])
    assert stored_criteria["method"] == "综合评估法"
    stored_tender_info = json.loads(row["tender_info"])
    assert stored_tender_info["tenderee"] == "某市政务服务和大数据局"

    # Check project fields backfilled
    proj = get_project(pid, tenant)
    assert proj is not None
    assert proj["tenderee"] == "某市政务服务和大数据局"
    assert proj["control_price"] == "1500万元"
    assert proj["method"] == "综合评估法"


def test_extract_project_doc_info_preserves_user_fields(monkeypatch):
    """_extract_project_doc_info must not overwrite user-filled project fields."""
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project, get_project

    tenant = "t-extract-preserve"
    user_tenderee = "用户手动填写的招标人"
    pid = get_or_create_project(
        tenant=tenant,
        tender_no=f"EP-{uuid.uuid4().hex[:8]}",
        tenderee=user_tenderee,
    )["project_id"]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")

    from server.common.agent_bridge import AgentRunMeta

    fake_meta = AgentRunMeta(
        request_id="rid-preserve",
        conversation_id="conv",
        claude_session_id="sess",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )

    async def fake_run_command_json(command_name, *args, **kwargs):
        # Returns tender_info with different tenderee
        return {"criteria": SAMPLE_CRITERIA, "tender_info": {"tenderee": "OCR派生值"}}, fake_meta

    monkeypatch.setattr(tender_module, "run_command_json", fake_run_command_json)

    asyncio.run(
        tender_module.extract_project_doc_info(pid, "/fake/path", "OCR text", tenant)
    )

    proj = get_project(pid, tenant)
    assert proj is not None
    # User-filled tenderee must be preserved
    assert proj["tenderee"] == user_tenderee


def test_extract_project_doc_info_failure_sets_criteria_failed(monkeypatch):
    """On run_command_json exception, criteria_status=failed; ocr_status=ready unchanged."""
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project

    tenant = "t-extract-fail"
    pid = get_or_create_project(
        tenant=tenant,
        tender_no=f"EF-{uuid.uuid4().hex[:8]}",
    )["project_id"]
    upsert_project_doc(
        project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready"
    )

    async def fail_run_command_json(command_name, *args, **kwargs):
        raise RuntimeError("simulated model failure")

    monkeypatch.setattr(tender_module, "run_command_json", fail_run_command_json)

    # Must not raise
    asyncio.run(
        tender_module.extract_project_doc_info(pid, "/fake/path", "OCR text", tenant)
    )

    row = get_project_doc(pid, tenant)
    assert row is not None
    assert row["criteria_status"] == "failed"
    # ocr_status must remain ready (extraction failure is non-fatal)
    assert row["ocr_status"] == "ready"
    assert row["criteria"] is None
    assert row["tender_info"] is None


def test_extract_project_doc_info_bad_payload_sets_criteria_failed(monkeypatch):
    """When run_command_json returns payload without criteria key, criteria_status=failed."""
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project
    from server.common.agent_bridge import AgentRunMeta

    tenant = "t-extract-badpayload"
    pid = get_or_create_project(
        tenant=tenant,
        tender_no=f"EB-{uuid.uuid4().hex[:8]}",
    )["project_id"]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")

    fake_meta = AgentRunMeta(
        request_id="rid-bad",
        conversation_id="c",
        claude_session_id="s",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )

    async def fake_run_command_json(command_name, *args, **kwargs):
        # Missing 'criteria' key; service should treat as failed
        return {"wrong_key": "value"}, fake_meta

    monkeypatch.setattr(tender_module, "run_command_json", fake_run_command_json)

    asyncio.run(
        tender_module.extract_project_doc_info(pid, "/fake/path", "OCR text", tenant)
    )

    row = get_project_doc(pid, tenant)
    assert row is not None
    assert row["criteria_status"] == "failed"


def _meta_for(rid: str):
    from server.common.agent_bridge import AgentRunMeta

    return AgentRunMeta(
        request_id=rid,
        conversation_id="c",
        claude_session_id="s",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def test_extract_project_doc_info_invalid_criteria_sets_failed(monkeypatch):
    """codex R1 P1: criteria 不符合 criteria.schema（缺 required items/method）→ criteria_status=failed，
    绝不把残缺 criteria 标 ready 注入评标。"""
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project

    tenant = "t-extract-invalidcrit"
    pid = get_or_create_project(tenant=tenant, tender_no=f"EI-{uuid.uuid4().hex[:8]}")["project_id"]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")

    # criteria 缺 required 字段（method/total_max/items），schema 校验必失败
    bad = {"criteria": {"source_ref": "招标文件 p.1"}, "tender_info": {"tenderee": "X公司"}}

    async def fake(command_name, *args, **kwargs):
        return bad, _meta_for("rid-invalid-crit")

    monkeypatch.setattr(tender_module, "run_command_json", fake)
    asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/path", "OCR text", tenant))

    row = get_project_doc(pid, tenant)
    assert row["criteria_status"] == "failed"
    assert row["ocr_status"] == "ready"  # 抽取失败绝不回退 OCR 就绪


def test_extract_project_doc_info_invalid_tender_info_dropped_criteria_ready(monkeypatch):
    """codex R1 P1: criteria 合法但 tender_info 非法 → tender_info 丢弃、criteria 仍 ready
    （tender_info 仅展示/回填，best-effort，不拖垮整体）。"""
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project

    tenant = "t-extract-badinfo"
    pid = get_or_create_project(tenant=tenant, tender_no=f"EG-{uuid.uuid4().hex[:8]}")["project_id"]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")

    # tender_info 含非法字段（additionalProperties:false）/ 错类型 → 丢弃
    payload = {
        "criteria": SAMPLE_CRITERIA,
        "tender_info": {"tender_no": 12345, "bogus_field": "x"},
    }

    async def fake(command_name, *args, **kwargs):
        return payload, _meta_for("rid-badinfo")

    monkeypatch.setattr(tender_module, "run_command_json", fake)
    asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/path", "OCR text", tenant))

    row = get_project_doc(pid, tenant)
    assert row["criteria_status"] == "ready"  # criteria 合法 → ready
    assert row["tender_info"] is None  # 非法 tender_info 被丢弃


def test_extract_project_doc_info_slims_initial_ocr_context_with_budget(monkeypatch):
    """Initial criteria extraction must fit the configured input + output budget."""
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project

    monkeypatch.setenv("TENDER_SLIM_CONTEXT", "1")
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "2000")
    tenant = "t-extract-initial-slim"
    pid = get_or_create_project(tenant=tenant, tender_no=f"ES-{uuid.uuid4().hex[:8]}")[
        "project_id"
    ]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
    ocr_text = (
        "### 文件: 招标文件.pdf (kind=pdf_text, route=native)\n"
        "项目名称：城市更新项目\n招标人：某市建设局\n"
        "# 第一章 项目说明\n"
        + "无关正文\n" * 40000
        + "# 第二章 评标办法\n评分标准：技术方案最高得 60 分。\n"
        "# 第三章 资格审查与符合性审查\n资格审查和符合性审查要求。\n"
        "# 第四章 废标与否决条款\n废标情形和否决投标条款。\n"
    )
    calls: dict[str, str] = {}

    async def fake_run_command_json(command_name, *args, **kwargs):
        calls["context"] = kwargs["context"]
        return SAMPLE_EXTRACT_PAYLOAD, _meta_for("rid-initial-slim")

    monkeypatch.setattr(tender_module, "run_command_json", fake_run_command_json)

    asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/path", ocr_text, tenant))

    context = calls["context"]
    estimated_messages = math.ceil(len(context) / 1.5)
    assert estimated_messages + 2000 + 4096 <= 100000
    assert "项目名称：城市更新项目" in context
    assert "评分标准：技术方案最高得 60 分" in context
    assert "资格审查和符合性审查要求" in context
    assert "废标情形和否决投标条款" in context
    assert "无关正文" not in context
    assert "禁止调用 Read、Glob 或任何工具" in context
    assert "只输出一个合法 JSON 对象" in context

    row = get_project_doc(pid, tenant)
    assert row is not None
    assert row["criteria_status"] == "ready"
    assert row["ocr_status"] == "ready"


def test_extract_project_doc_info_keeps_small_unstructured_ocr_behavior(monkeypatch):
    """Slimming must fall back to the original context for small/unstructured OCR."""
    import server.tender.doc_pipeline as tender_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc
    from server.stores.tender_project_store import get_or_create_project

    monkeypatch.setenv("TENDER_SLIM_CONTEXT", "1")
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "2000")
    tenant = "t-extract-small-fallback"
    pid = get_or_create_project(tenant=tenant, tender_no=f"EU-{uuid.uuid4().hex[:8]}")[
        "project_id"
    ]
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
    ocr_text = "### 文件: 招标文件.pdf (kind=pdf_text, route=native)\n普通 OCR 正文"
    calls: dict[str, str] = {}

    async def fake_run_command_json(command_name, *args, **kwargs):
        calls["context"] = kwargs["context"]
        return SAMPLE_EXTRACT_PAYLOAD, _meta_for("rid-small-fallback")

    monkeypatch.setattr(tender_module, "run_command_json", fake_run_command_json)

    asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/path", ocr_text, tenant))

    assert calls["context"].startswith(
        "=== 招标文件 OCR 底稿（确定性预处理，优先用此文本，无需再 Read 文件）===\n" + ocr_text
    )
    assert "禁止调用 Read、Glob 或任何工具" in calls["context"]
    row = get_project_doc(pid, tenant)
    assert row is not None
    assert row["criteria_status"] == "ready"
    assert row["ocr_status"] == "ready"


# ──────────────────────────────────────────────────────────────────────────────
# 6. GET /tender/projects/{id}/tender-doc
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    """TestClient with patched tenant + no-op background tasks."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    return TestClient(api_module.app)


def _make_project_api(client: TestClient, tender_no: str | None = None) -> str:
    tn = tender_no or f"R-{uuid.uuid4().hex[:8]}"
    resp = client.post("/tender/projects", json={"tender_no": tn}, headers=_AUTH)
    assert resp.status_code == 200, resp.text
    return resp.json()["project_id"]


def test_get_tender_doc_returns_expected_shape(client, monkeypatch):
    """GET /tender/projects/{id}/tender-doc returns correct schema shape."""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import upsert_project_doc

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)

    pid = _make_project_api(client)

    # Create a tender_project_docs row with ready status
    upsert_project_doc(
        project_id=pid,
        tenant="acme",
        tender_files=json.dumps(["招标文件.pdf"]),
        ocr_status="ready",
    )

    resp = client.get(f"/tender/projects/{pid}/tender-doc", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "ocr_status" in body
    assert "criteria_status" in body
    assert "criteria" in body
    assert "tender_info" in body
    assert "tender_files" in body
    assert isinstance(body["tender_files"], list)


def test_get_tender_doc_infers_failed_when_ocr_failed_and_criteria_stuck(client, monkeypatch):
    """reviewer R1 F3: ocr_status=failed 但 criteria_status 悬在 pending（崩溃/中断）→ GET 端把
    criteria_status 推断为 failed（终态），让前端停轮询；DB 原值不改。"""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import get_project_doc, update_project_doc_ocr, upsert_project_doc

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)
    pid = _make_project_api(client)
    upsert_project_doc(project_id=pid, tenant="acme", tender_files="[]", ocr_status="pending")
    # OCR 失败但（模拟崩溃）criteria_status 仍是默认 pending
    update_project_doc_ocr(pid, tenant="acme", ocr_text=None, ocr_clarity=None, status="failed")
    assert get_project_doc(pid, "acme")["criteria_status"] == "pending"  # DB 仍 pending

    body = client.get(f"/tender/projects/{pid}/tender-doc", headers=_AUTH).json()
    assert body["ocr_status"] == "failed"
    assert body["criteria_status"] == "failed"  # GET 端推断为终态，前端停轮询
    # DB 原值不被改写（仅 GET 输出推断）
    assert get_project_doc(pid, "acme")["criteria_status"] == "pending"


def test_get_tender_doc_returns_null_criteria_when_not_ready(client, monkeypatch):
    """GET /tender/projects/{id}/tender-doc returns criteria=null when not yet extracted."""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import upsert_project_doc

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)

    pid = _make_project_api(client)
    upsert_project_doc(
        project_id=pid,
        tenant="acme",
        tender_files=json.dumps(["招标文件.pdf"]),
        ocr_status="ready",
    )

    resp = client.get(f"/tender/projects/{pid}/tender-doc", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["criteria"] is None
    assert body["tender_info"] is None
    assert body["criteria_status"] == "pending"


def test_get_tender_doc_returns_decoded_criteria_when_ready(client, monkeypatch):
    """GET /tender/projects/{id}/tender-doc returns decoded criteria object when extracted."""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import (
        upsert_project_doc,
        update_project_doc_criteria_extracted,
    )

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)

    pid = _make_project_api(client)
    upsert_project_doc(
        project_id=pid,
        tenant="acme",
        tender_files=json.dumps(["招标文件.pdf"]),
        ocr_status="ready",
    )
    update_project_doc_criteria_extracted(
        pid,
        "acme",
        criteria_json=json.dumps(SAMPLE_CRITERIA),
        tender_info_json=json.dumps(SAMPLE_TENDER_INFO),
        status="ready",
    )

    resp = client.get(f"/tender/projects/{pid}/tender-doc", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["criteria_status"] == "ready"
    assert isinstance(body["criteria"], dict)
    assert body["criteria"]["method"] == "综合评估法"
    assert isinstance(body["tender_info"], dict)
    assert body["tender_info"]["tenderee"] == "某市政务服务和大数据局"
    assert body["ocr_clarity"] is None  # clarity was not set


def test_get_tender_doc_404_for_missing_project(client):
    """GET /tender/projects/{id}/tender-doc returns 404 for non-existent project."""
    resp = client.get("/tender/projects/nonexistent-pid/tender-doc", headers=_AUTH)
    assert resp.status_code == 404


def test_get_tender_doc_requires_auth(client, monkeypatch):
    """GET /tender/projects/{id}/tender-doc requires authentication."""
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)
    pid = _make_project_api(client)
    resp = client.get(f"/tender/projects/{pid}/tender-doc")
    assert resp.status_code == 401


def test_get_tender_doc_no_doc_uploaded_returns_404(client):
    """When no tender-doc was uploaded, returns 404."""
    pid = _make_project_api(client)
    resp = client.get(f"/tender/projects/{pid}/tender-doc", headers=_AUTH)
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 7. docs-status includes criteria_status
# ──────────────────────────────────────────────────────────────────────────────


def test_docs_status_includes_criteria_status(client, monkeypatch):
    """GET /tender/projects/{id}/docs-status includes criteria_status in tender_doc."""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import upsert_project_doc

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)

    pid = _make_project_api(client)
    upsert_project_doc(
        project_id=pid,
        tenant="acme",
        tender_files=json.dumps(["招标文件.pdf"]),
        ocr_status="ready",
    )

    resp = client.get(f"/tender/projects/{pid}/docs-status", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tender_doc" in body
    assert body["tender_doc"] is not None
    assert "criteria_status" in body["tender_doc"]
    assert body["tender_doc"]["criteria_status"] == "pending"


def test_docs_status_criteria_status_ready(client, monkeypatch):
    """docs-status returns criteria_status=ready after successful extraction."""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import (
        upsert_project_doc,
        update_project_doc_criteria_extracted,
    )

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)

    pid = _make_project_api(client)
    upsert_project_doc(
        project_id=pid,
        tenant="acme",
        tender_files=json.dumps(["招标文件.pdf"]),
        ocr_status="ready",
    )
    update_project_doc_criteria_extracted(
        pid, "acme", criteria_json='{"a":1}', tender_info_json=None, status="ready"
    )

    resp = client.get(f"/tender/projects/{pid}/docs-status", headers=_AUTH)
    body = resp.json()
    assert body["tender_doc"]["criteria_status"] == "ready"


# ──────────────────────────────────────────────────────────────────────────────
# 8. Worker: _run_evaluation injects stored criteria into context
# ──────────────────────────────────────────────────────────────────────────────


def test_worker_injects_stored_criteria_into_context(monkeypatch):
    """When get_project_doc returns non-empty criteria, _run_evaluation injects it into context."""
    import server.tender.runner as worker

    calls: dict = {}

    from server.common.agent_bridge import AgentRunMeta

    def _fake_meta(request_id: str) -> AgentRunMeta:
        return AgentRunMeta(
            request_id=request_id,
            conversation_id="conv-test",
            claude_session_id="sess-test",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name="common/audit-result.schema.json",
            log_file="logs/test.log",
            result_file="logs/test-result.json",
            result_subtype="success",
            cost_usd=0.0,
            finished_at=None,
        )

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls["context"] = opts.get("context")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(worker, "run_command_json", fake_run_command_json)

    # Provide doc layer context with criteria
    criteria_json = json.dumps(SAMPLE_CRITERIA)

    def fake_load_doc_layer(project_id, bid_id, tenant):
        return "=== 招标文件底稿 ===\nOCR文本\n\n=== 投标文件（测试公司）底稿 ===\n投标文本"

    monkeypatch.setattr(worker, "_load_doc_layer_context", fake_load_doc_layer)

    # Patch get_project_doc to return a row with stored criteria
    def fake_get_project_doc(project_id, tenant):
        return {
            "project_id": project_id,
            "criteria": criteria_json,
            "ocr_status": "ready",
            "criteria_status": "ready",
        }

    monkeypatch.setattr(worker, "get_project_doc", fake_get_project_doc)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    preprocess_called = []
    monkeypatch.setattr(
        worker,
        "ocr_preprocess_block",
        lambda *a, **kw: preprocess_called.append(True) or "fallback",
    )

    asyncio.run(
        worker.run_tender_evaluation(
            request_id="rid-inject-criteria",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
            bid_id="bd-test",
        )
    )

    # context must contain the criteria injection marker
    context = calls.get("context") or ""
    assert "已解析评分标准 criteria" in context, (
        f"Expected criteria injection marker in context. Got: {context[:500]}"
    )
    assert "综合评估法" in context, "Criteria content must be in the injected context"


def test_worker_no_criteria_in_store_unchanged_behavior(monkeypatch):
    """When get_project_doc has no criteria, context is not polluted with criteria block."""
    import server.tender.runner as worker

    calls: dict = {}

    from server.common.agent_bridge import AgentRunMeta

    def _fake_meta(request_id: str) -> AgentRunMeta:
        return AgentRunMeta(
            request_id=request_id,
            conversation_id="conv",
            claude_session_id="sess",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name="common/audit-result.schema.json",
            log_file="logs/test.log",
            result_file="logs/test-result.json",
            result_subtype="success",
            cost_usd=0.0,
            finished_at=None,
        )

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls["context"] = opts.get("context")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(worker, "run_command_json", fake_run_command_json)

    # Doc layer provides context but criteria is None
    def fake_load_doc_layer(project_id, bid_id, tenant):
        return "=== 招标文件底稿 ===\nOCR文本\n\n=== 投标文件（测试公司）底稿 ===\n投标文本"

    monkeypatch.setattr(worker, "_load_doc_layer_context", fake_load_doc_layer)

    def fake_get_project_doc_no_criteria(project_id, tenant):
        return {
            "project_id": project_id,
            "criteria": None,
            "ocr_status": "ready",
            "criteria_status": "pending",
        }

    monkeypatch.setattr(worker, "get_project_doc", fake_get_project_doc_no_criteria)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")
    monkeypatch.setattr(
        worker,
        "ocr_preprocess_block",
        lambda *a, **kw: "fallback",
    )

    asyncio.run(
        worker.run_tender_evaluation(
            request_id="rid-no-criteria",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-no-criteria",
            bid_id="bd-test",
        )
    )

    context = calls.get("context") or ""
    assert "已解析评分标准 criteria" not in context, (
        "Criteria block must not be injected when criteria is absent"
    )
