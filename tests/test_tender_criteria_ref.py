"""KD1：criteria 项目级权威 + 结论 ``criteria_ref`` 引用（横比可比性判据的新底座）。

旧判据 = 各家结论里模型转录的 criteria 副本 hash 字节等价 → 转录漂移即 `criteria_inconsistent`
全员不排名。新判据 = 各家结论引用同一项目级 criteria **版本**：

- ``criteria_version`` = 权威副本内容 hash，**compute-on-read**（免 DB 迁移，存量项目自然获得版本）；
- runner 注入 criteria 时同时注入版本，并在结论上**确定性打 ref**（不靠模型回声）；
- worker 落库后把 ref 持久化进 results.payload：注入过 → project；未注入但本家 criteria 赢得
  backfill（即本家就是权威） → project；输给别家 → self_parsed。
"""

from __future__ import annotations

import asyncio
import json
import uuid

from server.common.agent_bridge import AgentRunMeta
from server.stores.result_store import get_result_payload_by_request_id
from server.stores.tender_compare_store import compute_criteria_hash
from server.stores.tender_doc_store import upsert_project_doc
from server.stores.tender_project_store import get_or_create_project
from server.tender.compare_input import resolve_project_criteria

TENANT = "acme"


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


def _new_project_with_criteria(criteria: dict | None) -> str:
    project_id = get_or_create_project(
        tenant=TENANT, tender_no=f"R-{uuid.uuid4().hex[:8]}"
    )["project_id"]
    upsert_project_doc(
        project_id=project_id,
        tenant=TENANT,
        tender_files=json.dumps([f"{project_id}.pdf"], ensure_ascii=False),
        criteria=json.dumps(criteria, ensure_ascii=False) if criteria else None,
        # 抽取已到终态 ready（criteria 为空只代表那次抽取没产出评分项，权威留给评标回填）。
        # 补这一列的理由：收单等就绪后（用户产品裁决 2026-08-19）评标任务会等 criteria 到终态，
        # 而默认的 criteria_status='pending' + 新鲜心跳在生产里意味着"抽取还在跑"，任务会一直等。
        criteria_status="ready",
    )
    return project_id


def _fake_meta(request_id: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="tender/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def test_audit_schema_declares_criteria_ref_shape():
    """D2：criteria_ref 是横比承重字段，形状必须进契约（不能只靠 additionalProperties 放行）。"""
    from server.common.contract import load_output_schema

    schema = load_output_schema("common/audit-result.schema.json")
    ref = schema["properties"]["extracted_data"]["properties"]["criteria_ref"]
    assert ref["required"] == ["version", "source"]
    assert set(ref["properties"]["source"]["enum"]) == {"project", "self_parsed"}


def test_audit_schema_rejects_unknown_criteria_ref_source():
    import jsonschema
    import pytest

    from server.common.contract import load_output_schema

    schema = load_output_schema("common/audit-result.schema.json")
    payload = {
        "claim_id": "B1", "verdict": "manual_review",
        "manual_review_reason": "rule_gap", "explanation": "x", "reasons": [],
        "policy_refs": [], "risk_score": 1,
        "extracted_data": {"criteria_ref": {"version": "v1", "source": "guessed"}},
        "evidence_chain": [], "reviewed_by": "tender-evaluator",
        "timestamp": "2026-08-11T00:00:00+00:00",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


# ── compute-on-read 版本 ────────────────────────────────────────────────────────


def test_resolve_project_criteria_computes_version_on_read():
    """存量项目（只有 criteria 内容、无 version 列）读取时现算版本 → 免迁移即可解锁横比。"""
    criteria = _criteria()
    project_id = _new_project_with_criteria(criteria)

    resolved, version = resolve_project_criteria(project_id, TENANT)

    assert resolved == criteria
    assert version == compute_criteria_hash(criteria)


def test_resolve_project_criteria_none_when_absent():
    project_id = _new_project_with_criteria(None)
    assert resolve_project_criteria(project_id, TENANT) == (None, None)


def test_resolve_project_criteria_version_is_stable_across_reads():
    project_id = _new_project_with_criteria(_criteria())
    assert resolve_project_criteria(project_id, TENANT)[1] == (
        resolve_project_criteria(project_id, TENANT)[1]
    )


# ── runner：注入版本 + 确定性打 ref ─────────────────────────────────────────────


def test_runner_injects_criteria_version_and_stamps_project_ref(monkeypatch):
    from server.tender import runner

    criteria = _criteria()
    project_id = _new_project_with_criteria(criteria)
    version = compute_criteria_hash(criteria)
    captured: dict = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        captured["context"] = opts.get("context")
        # 模型转录漂移（多写一项）——判据只看 ref，不看快照。
        drifted = {**criteria, "items": [*criteria["items"], {"item": "多余项"}]}
        return {"verdict": "manual_review", "extracted_data": {"criteria": drifted}}, _fake_meta(
            opts["request_id"]
        )

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "底稿")

    payload, _meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-criteria-ref",
            tenant=TENANT,
            directory_path="/fake/dir",
            project_id=project_id,
        )
    )

    assert version in captured["context"]
    assert payload["extracted_data"]["criteria_ref"] == {
        "version": version,
        "source": "project",
    }


def test_runner_marks_self_parsed_when_no_project_criteria(monkeypatch):
    from server.tender import runner

    criteria = _criteria()
    project_id = _new_project_with_criteria(None)

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        return {"verdict": "manual_review", "extracted_data": {"criteria": criteria}}, _fake_meta(
            opts["request_id"]
        )

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "底稿")

    payload, _meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-self-parsed",
            tenant=TENANT,
            directory_path="/fake/dir",
            project_id=project_id,
        )
    )

    assert payload["extracted_data"]["criteria_ref"] == {
        "version": compute_criteria_hash(criteria),
        "source": "self_parsed",
    }


# ── worker：ref 落库 + backfill 竞态消解 ────────────────────────────────────────


def _run_worker(project_id: str, request_id: str, payload: dict) -> None:
    from server.tender import worker

    async def fake_eval(**kwargs):
        from server.stores.result_store import archive_result_payload

        archive_result_payload(
            request_id=kwargs["request_id"],
            tenant=TENANT,
            project_id=kwargs["project_id"],
            conversation_id="c1",
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name="tender/audit-result.schema.json",
            request_mode="text",
            result_subtype="success",
            cost_usd=0.0,
            prompt_preview="x",
            response=payload,
        )
        return payload, _fake_meta(kwargs["request_id"])

    original = worker._run_evaluation
    worker._run_evaluation = fake_eval
    try:
        asyncio.run(
            worker.execute_tender_evaluation_task(
                request_id=request_id,
                tenant=TENANT,
                directory_path="/fake/dir",
                source_mode="directory",
                project_id=project_id,
            )
        )
    finally:
        worker._run_evaluation = original


def test_worker_persists_criteria_ref_into_archived_result():
    criteria = _criteria()
    project_id = _new_project_with_criteria(criteria)
    version = compute_criteria_hash(criteria)
    request_id = f"rid-{uuid.uuid4().hex[:8]}"

    _run_worker(
        project_id,
        request_id,
        {
            "verdict": "manual_review",
            "claim_id": "B1",
            "extracted_data": {
                "criteria": criteria,
                "criteria_ref": {"version": version, "source": "project"},
            },
        },
    )

    stored = get_result_payload_by_request_id(request_id, TENANT)
    assert stored["response"]["extracted_data"]["criteria_ref"] == {
        "version": version,
        "source": "project",
    }


def test_worker_upgrades_self_parsed_ref_when_backfill_wins():
    """权威缺位时首写者赢 backfill → 本家即权威，ref 必须升为 project（否则自己排除自己）。

    verdict 在本文件其余用例里只是填充值，这里**必须**是非 manual_review：2026-08-17 事故后
    回填有质量门（``worker._authority_block_reason``），转人工的会话不再有资格定项目权威。
    """
    criteria = _criteria()
    project_id = _new_project_with_criteria(None)
    request_id = f"rid-{uuid.uuid4().hex[:8]}"

    _run_worker(
        project_id,
        request_id,
        {
            "verdict": "approved",
            "claim_id": "B1",
            "extracted_data": {
                "criteria": criteria,
                "criteria_ref": {
                    "version": compute_criteria_hash(criteria),
                    "source": "self_parsed",
                },
            },
        },
    )

    stored = get_result_payload_by_request_id(request_id, TENANT)
    assert stored["response"]["extracted_data"]["criteria_ref"] == {
        "version": compute_criteria_hash(criteria),
        "source": "project",
    }
    assert resolve_project_criteria(project_id, TENANT)[1] == compute_criteria_hash(criteria)


def test_worker_keeps_self_parsed_ref_when_backfill_loses():
    """权威已被别家写入且与本家不同 → 本家保持 self_parsed（横比时被排除并提示重评）。"""
    authoritative = _criteria(price_max=40)
    own = _criteria(price_max=30)
    project_id = _new_project_with_criteria(authoritative)
    request_id = f"rid-{uuid.uuid4().hex[:8]}"

    _run_worker(
        project_id,
        request_id,
        {
            "verdict": "manual_review",
            "claim_id": "B2",
            "extracted_data": {
                "criteria": own,
                "criteria_ref": {
                    "version": compute_criteria_hash(own),
                    "source": "self_parsed",
                },
            },
        },
    )

    stored = get_result_payload_by_request_id(request_id, TENANT)
    assert stored["response"]["extracted_data"]["criteria_ref"]["source"] == "self_parsed"
