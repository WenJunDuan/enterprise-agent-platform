"""(a) criteria 状态诚实化 + 回填质量门。

生产事故 2026-08-17：招标文件的 criteria 抽取抛 ``JSONContractError`` → criteria 缺位 →
证据层（以 criteria 项为检索键）跳过 → 整份底稿退回全量注入 → 784,903 字节截到 178,641
（砍 77%）→ 模型只看到 23% 的材料。**那次降级会话自解析出的 criteria 随后被回填成项目
永久权威**：DB 里至今是 ``criteria_status='ready'`` 与 ``criteria_error='…extraction_failed'``
并存，后续每一家投标都继承这份从残卷里解析出来的规则。

本文件钉两条性质：

1. **状态诚实**：回填成功即清 ``criteria_error``（ready 与 error 不得并存），并落
   ``criteria_source`` 出处标记；"首个写入者赢"由 SQL 守卫原子保证（读-判-写两步在
   ``MAX_CONCURRENT_TENDER=2`` 下会双双判空）。
2. **回填质量门**：只有**未发生截断**且**结论非 manual_review** 的会话，其 criteria 才有
   资格成为项目权威。判据只看链路信号（预算闸有没有真的削过、结论落在哪一档），
   **绝不看文档内容**——语言无关、换一份标书仍然成立，也就无从拟合。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import server.tender.worker as tw

_SAMPLE_CRITERIA = {
    "source_ref": "招标文件 第三章 评标办法",
    "method": "综合评估法",
    "total_max": 100,
    "items": [{"item": "技术方案", "max": 40, "tag": "scored", "score_mode": "banded"}],
}
_OTHER_CRITERIA = {
    "source_ref": "招标文件 第四章",
    "method": "综合评估法",
    "total_max": 80,
    "items": [{"item": "商务报价", "max": 30, "tag": "scored", "score_mode": "formula"}],
}
# 生产现场 DB 里那一条（见 doc_pipeline 失败分支的文案）。
_PRODUCTION_ERROR = "评分标准抽取未完成（抽取命令失败或返回结构异常）（extraction_failed）"


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _fake_meta():
    class _Meta:
        result_file = "logs/test-result.json"
        claude_session_id = "sess-test"

    return _Meta()


def _self_parsed_payload(verdict: str = "approved") -> dict:
    return {
        "verdict": verdict,
        "extracted_data": {
            "criteria": _SAMPLE_CRITERIA,
            "criteria_ref": {"version": "v-self", "source": "self_parsed"},
        },
    }


# ── 1. 存储层：状态诚实 ────────────────────────────────────────────────────────


class TestBackfillLeavesAnHonestRow:
    def test_backfill_onto_a_failed_row_clears_the_failure_reason(self):
        """生产现场形态：failed + criteria_error 在库，评标回填后不得 ready 与 error 并存。"""
        from server.stores.tender_doc_store import (
            CRITERIA_SOURCE_BACKFILL,
            get_project_doc,
            update_project_doc_criteria,
            update_project_doc_criteria_extracted,
            upsert_project_doc,
        )

        pid, tenant = _pid(), "t-honesty"
        upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
        update_project_doc_criteria_extracted(
            pid,
            tenant,
            criteria_json=None,
            tender_info_json=None,
            status="failed",
            criteria_error=_PRODUCTION_ERROR,
        )

        wrote = update_project_doc_criteria(pid, tenant, json.dumps(_SAMPLE_CRITERIA))

        row = get_project_doc(pid, tenant)
        assert wrote is True
        assert row["criteria_status"] == "ready"
        assert row["criteria_error"] is None, "ready 与 error 并存正是生产事故的库内形态"
        assert row["criteria_source"] == CRITERIA_SOURCE_BACKFILL

    def test_backfill_reports_that_it_lost_to_the_existing_authority(self):
        """首个写入者赢由 SQL 守卫保证，并如实回报输赢（``criteria_ref`` 据此定 project/self_parsed）。"""
        from server.stores.tender_doc_store import (
            get_project_doc,
            update_project_doc_criteria,
            upsert_project_doc,
        )

        pid, tenant = _pid(), "t-first-writer"
        upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")

        assert update_project_doc_criteria(pid, tenant, json.dumps(_SAMPLE_CRITERIA)) is True
        assert update_project_doc_criteria(pid, tenant, json.dumps(_OTHER_CRITERIA)) is False

        row = get_project_doc(pid, tenant)
        assert json.loads(row["criteria"])["total_max"] == 100

    def test_backfill_onto_a_missing_row_reports_a_loss(self):
        """散单/旧迁移项目没有招标层行 → 写 0 行，如实回报没成为权威（不抛、不假装赢）。"""
        from server.stores.tender_doc_store import update_project_doc_criteria

        assert update_project_doc_criteria(_pid(), "t-absent", json.dumps(_SAMPLE_CRITERIA)) is False


class TestExtractionRecordsItsProvenance:
    def test_successful_extraction_is_marked_as_extracted(self):
        from server.stores.tender_doc_store import (
            CRITERIA_SOURCE_EXTRACTED,
            get_project_doc,
            update_project_doc_criteria_extracted,
            upsert_project_doc,
        )

        pid, tenant = _pid(), "t-prov-ok"
        upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
        update_project_doc_criteria_extracted(
            pid,
            tenant,
            criteria_json=json.dumps(_SAMPLE_CRITERIA),
            tender_info_json=None,
            status="ready",
        )

        row = get_project_doc(pid, tenant)
        assert row["criteria_source"] == CRITERIA_SOURCE_EXTRACTED
        assert row["criteria_error"] is None

    def test_failed_extraction_leaves_no_provenance(self):
        """criteria 为空时出处必须一并清掉——出处描述的是"现在库里这份"的来源。"""
        from server.stores.tender_doc_store import (
            get_project_doc,
            update_project_doc_criteria_extracted,
            upsert_project_doc,
        )

        pid, tenant = _pid(), "t-prov-fail"
        upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
        update_project_doc_criteria_extracted(
            pid,
            tenant,
            criteria_json=json.dumps(_SAMPLE_CRITERIA),
            tender_info_json=None,
            status="ready",
        )
        update_project_doc_criteria_extracted(
            pid,
            tenant,
            criteria_json=None,
            tender_info_json=None,
            status="failed",
            criteria_error=_PRODUCTION_ERROR,
        )

        row = get_project_doc(pid, tenant)
        assert row["criteria_status"] == "failed"
        assert row["criteria_error"] == _PRODUCTION_ERROR
        assert row["criteria_source"] is None


# ── 2. 截断信号：从预算闸传到回填点 ────────────────────────────────────────────


class TestTruncationIsObservableAtTheBackfillPoint:
    def test_the_draft_budget_gate_marks_the_session_when_it_cuts(self, monkeypatch):
        from server.tender.draft_budget import bound_draft
        from server.tender.eval_signals import evaluation_signals

        monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
        with evaluation_signals() as signals:
            assert bound_draft("评标办法\n" + "评分细则内容\n" * 40) is not None
            assert signals.context_truncated is True

    def test_a_draft_within_budget_leaves_the_session_clean(self, monkeypatch):
        from server.tender.draft_budget import bound_draft
        from server.tender.eval_signals import evaluation_signals

        monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
        with evaluation_signals() as signals:
            assert bound_draft("短底稿") is None
            assert signals.context_truncated is False

    def test_trimming_the_assembled_context_marks_the_session(self, monkeypatch):
        from server.tender import context_slim
        from server.tender.eval_signals import evaluation_signals

        monkeypatch.setattr(context_slim, "_preextract_char_budget", lambda model=None: 200)
        with evaluation_signals() as signals:
            context_slim.bound_tender_context("上下文" * 300)
            assert signals.context_truncated is True

    def test_the_mark_survives_a_worker_thread_and_a_child_task(self):
        """预算闸跑在 ``to_thread`` / 子任务里也算数——ContextVar 只保证向下复制，
        故信号必须是**可变记录**，否则深处打的标在发起方看不见（整条门就形同虚设）。"""
        from server.tender.eval_signals import evaluation_signals, mark_context_truncated

        async def _drive() -> bool:
            with evaluation_signals() as signals:
                await asyncio.to_thread(mark_context_truncated)
                return signals.context_truncated

        async def _drive_child_task() -> bool:
            with evaluation_signals() as signals:
                await asyncio.create_task(_mark_async())
                return signals.context_truncated

        async def _mark_async() -> None:
            mark_context_truncated()

        assert asyncio.run(_drive()) is True
        assert asyncio.run(_drive_child_task()) is True

    def test_marking_without_an_open_session_is_a_no_op(self):
        """CLI / 单测等没开会话作用域的路径不得因为一句标记而炸。"""
        from server.tender.eval_signals import mark_context_truncated

        mark_context_truncated()


# ── 3. 回填质量门（worker completed 分支）────────────────────────────────────


def _stub_worker_io(monkeypatch, *, writes: list, refs: list) -> None:
    monkeypatch.setattr(tw, "upsert_tender_task", lambda payload: None)
    monkeypatch.setattr(tw, "update_tender_progress", lambda *a, **k: None)
    monkeypatch.setattr(tw, "_backfill_bidder_name", lambda *a, **k: None)
    monkeypatch.setattr(
        tw,
        "update_project_doc_criteria",
        lambda pid, tenant, criteria_json: (writes.append((pid, tenant, criteria_json)), True)[1],
    )
    monkeypatch.setattr(
        tw, "update_result_criteria_ref", lambda rid, tenant, ref: refs.append(ref)
    )

    async def _no_compare(*_a, **_kw):
        return None

    monkeypatch.setattr(tw, "maybe_schedule_compare", _no_compare)


def _run_worker(monkeypatch, payload: dict, *, truncated: bool, writes: list, refs: list) -> None:
    from server.tender.eval_signals import mark_context_truncated

    _stub_worker_io(monkeypatch, writes=writes, refs=refs)

    async def _fake_run_evaluation(**_kwargs):
        if truncated:
            # 预算闸真的削过底稿时会打的那个标（``bound_draft`` / ``bound_tender_context``）。
            mark_context_truncated()
        return payload, _fake_meta()

    monkeypatch.setattr(tw, "_run_evaluation", _fake_run_evaluation)
    asyncio.run(
        tw._execute_inner(
            request_id=f"r-{uuid.uuid4().hex[:8]}",
            tenant="acme",
            directory_path="/tmp/case",
            source_mode="directory",
            project_id="tp-gate",
            bid_id="bd-gate",
        )
    )


class TestOnlyAnUndegradedSessionCanSetTheProjectAuthority:
    def test_a_truncated_session_never_becomes_the_authority(self, monkeypatch):
        """事故主链路：只看到 23% 材料的会话，其自解析 criteria 不得固化成项目规则。"""
        writes: list = []
        refs: list = []
        _run_worker(monkeypatch, _self_parsed_payload(), truncated=True, writes=writes, refs=refs)

        assert writes == []
        assert refs and refs[0]["source"] == "self_parsed", "没赢下权威就不得把 ref 升成 project"

    def test_a_manual_review_session_never_becomes_the_authority(self, monkeypatch):
        """结论自己都不成立（转人工），其副产物更不该成为后续每一家的规则。"""
        writes: list = []
        refs: list = []
        _run_worker(
            monkeypatch,
            _self_parsed_payload(verdict="manual_review"),
            truncated=False,
            writes=writes,
            refs=refs,
        )

        assert writes == []
        assert refs and refs[0]["source"] == "self_parsed"

    def test_an_undegraded_session_still_backfills(self, monkeypatch):
        """门是"挡住降级会话"，不是"关掉回填"——否则证据层永远解锁不了。"""
        writes: list = []
        refs: list = []
        _run_worker(monkeypatch, _self_parsed_payload(), truncated=False, writes=writes, refs=refs)

        assert len(writes) == 1
        assert writes[0][0] == "tp-gate"
        assert json.loads(writes[0][2])["total_max"] == 100
        assert refs and refs[0]["source"] == "project"


class TestTheGateJudgesLinkSignalsOnly:
    def test_gate_blocks_on_truncation_and_on_manual_review(self):
        assert tw._authority_block_reason(_self_parsed_payload(), context_truncated=True) == (
            "context_truncated"
        )
        assert tw._authority_block_reason(
            _self_parsed_payload(verdict="manual_review"), context_truncated=False
        ) == "manual_review"

    def test_gate_passes_an_undegraded_session(self):
        assert tw._authority_block_reason(_self_parsed_payload(), context_truncated=False) is None

    def test_gate_does_not_look_at_the_document_at_all(self):
        """判据必须语言无关：同一档链路信号下，换任何文本内容结论都不变（防拟合）。"""
        chinese = {"verdict": "approved", "extracted_data": {"criteria": _SAMPLE_CRITERIA}}
        english = {
            "verdict": "approved",
            "extracted_data": {"criteria": {"items": [{"item": "Technical", "max": 40}]}},
        }
        assert tw._authority_block_reason(chinese, context_truncated=False) is None
        assert tw._authority_block_reason(english, context_truncated=False) is None
        assert tw._authority_block_reason(chinese, context_truncated=True) == "context_truncated"
        assert tw._authority_block_reason(english, context_truncated=True) == "context_truncated"

    def test_blocked_backfill_writes_nothing(self, monkeypatch):
        """门关着时连 store 都不该碰（不是写完再回滚）。"""
        calls: list = []
        monkeypatch.setattr(
            tw, "update_project_doc_criteria", lambda *a, **k: calls.append(a) or True
        )

        assert (
            tw._backfill_criteria("tp-x", "acme", _SAMPLE_CRITERIA, block_reason="context_truncated")
            is False
        )
        assert calls == []
