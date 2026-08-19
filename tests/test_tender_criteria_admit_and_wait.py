"""收单等就绪：criteria 仍在解析时收下评标，任务内等就绪再判分（2026-08-19 用户产品裁决）。

用户原话：「传完招标文件就可以直接传投标文件，然后就可以点开始分析，不要等」
「实际上我点了分析还是在分析招标文件啊（后台还在解析），只是交互上看起来舒服」。

P0.4 的底线一条没松：**绝不在无 criteria 时开始判分**——那条路的终点是证据层（S3）跳过 →
整份底稿退回全量注入 → 超预算截断 → 整单作废（2026-08-17 实测）。变的只是"未就绪"的归宿：

- 还在解析（心跳新鲜）→ **收单**，任务在开跑判分前等它就绪；等不到就**任务失败**，不降级评标；
- 解析失败 / 心跳陈旧的僵尸任务 → 仍在提交口 409 拒收（等不来结果的单不收，见
  ``test_tender_criteria_submit_gate.py``）。

等待上限沿用既有的 ``doc_layer_wait_cap_sec``（从 ``TENDER_TIMEOUT_SEC`` 派生），不新增配置项。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

import server.tender.worker as tw
from server.stores.tender_doc_store import (
    get_project_doc,
    update_project_doc_criteria_extracted,
    upsert_project_doc,
)
from server.tender import criteria_gate, doc_layer

_TENANT = "t-admit-wait"
_CRITERIA = {
    "source_ref": "招标文件 第三章 评标办法",
    "method": "综合评估法",
    "total_max": 100,
    "items": [{"item": "技术方案", "max": 40, "tag": "scored", "score_mode": "banded"}],
}


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _prewarmed(project_id: str, criteria_status: str) -> None:
    """给项目挂一份预热底稿记录（评标会走证据层的那种项目）。"""
    upsert_project_doc(
        project_id=project_id,
        tenant=_TENANT,
        tender_files='["招标.pdf"]',
        ocr_status="ready",
        ocr_text="招标文件底稿",
        criteria_status=criteria_status,
    )


def _set_criteria(project_id: str, status: str, *, error: str | None = None) -> None:
    update_project_doc_criteria_extracted(
        project_id,
        _TENANT,
        criteria_json=json.dumps(_CRITERIA, ensure_ascii=False) if status == "ready" else None,
        tender_info_json=None,
        status=status,
        criteria_error=error,
    )


async def _flip_criteria_after(project_id: str, delay: float, status: str, **kwargs) -> None:
    """模拟后台抽取在评标等待期间落地（真写库，不是打桩）。"""
    await asyncio.sleep(delay)
    _set_criteria(project_id, status, **kwargs)


class _Meta:
    result_file = "logs/test-result.json"
    claude_session_id = "sess-test"


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch):
    monkeypatch.setattr(doc_layer, "DOC_LAYER_POLL_SEC", 0.01)


# ── 等待本身：就绪 / 等不到 / 不适用 ──────────────────────────────────────────


def test_wait_returns_ready_when_extraction_lands_while_we_wait():
    """AC3：等待中 criteria 转 ready → 放行判分（"点了分析后台还在解析"的正常出口）。"""
    pid = _pid()
    _prewarmed(pid, "running")

    async def _scenario() -> str:
        flip = asyncio.create_task(_flip_criteria_after(pid, 0.03, "ready"))
        outcome = await criteria_gate.wait_criteria_ready(pid, _TENANT)
        await flip
        return outcome

    assert asyncio.run(_scenario()) == "ready"


def test_wait_gives_up_at_the_existing_derived_cap(monkeypatch):
    """AC4：上限沿用既有 ``doc_layer_wait_cap_sec``（TENDER_TIMEOUT_SEC 派生），不新增配置项。"""
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "0.02")  # 派生上限 = 0.01s
    pid = _pid()
    _prewarmed(pid, "running")

    assert asyncio.run(criteria_gate.wait_criteria_ready(pid, _TENANT)) == "wait_cap_reached"


def test_wait_does_not_linger_on_a_failed_or_zombie_extraction(monkeypatch):
    """failed 与心跳陈旧的僵尸 running 都等不来结果 → 立刻收手，别白等到上限。"""
    failed_pid = _pid()
    _prewarmed(failed_pid, "failed")
    assert asyncio.run(criteria_gate.wait_criteria_ready(failed_pid, _TENANT)) == "failed"

    monkeypatch.setenv("OCR_PREWARM_STALE_SEC", "0.001")  # 刚写的行也算心跳陈旧
    zombie_pid = _pid()
    _prewarmed(zombie_pid, "running")
    assert asyncio.run(criteria_gate.wait_criteria_ready(zombie_pid, _TENANT)) == "failed"


def test_wait_is_not_applicable_without_a_prewarmed_project_doc():
    """AC5：没有预热底稿记录（散单 / directory）本来就不走证据层 → 不等待，行为零变化。"""
    assert asyncio.run(criteria_gate.wait_criteria_ready(_pid(), _TENANT)) == "absent"


# ── 失败文案：两种未就绪，两种可执行动作 ──────────────────────────────────────


def test_ready_criteria_starts_scoring_without_any_failure_message():
    pid = _pid()
    _prewarmed(pid, "ready")

    assert asyncio.run(criteria_gate.criteria_start_failure(pid, _TENANT)) is None


def test_timeout_message_says_it_waited_and_tells_the_user_to_resubmit(monkeypatch):
    """等待超时 → 沿用"仍在解析"那段文案的语义：等过了、没等到、稍后重新提交。"""
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "0.02")
    pid = _pid()
    _prewarmed(pid, "running")

    detail = asyncio.run(criteria_gate.criteria_start_failure(pid, _TENANT))

    assert detail is not None
    assert "评分标准" in detail
    assert "等待" in detail, "必须说清是等过了才失败，不是一提交就拒"
    assert "重新提交" in detail
    assert "重新上传" not in detail, "还在解析时叫人重传是把人往回赶（沿用提交闸的文案分工）"


def test_failed_extraction_message_carries_the_reupload_action_and_the_reason():
    """等待中转 failed → 沿用"解析未成功"那段文案：重新上传招标文件，并带上具体原因。"""
    pid = _pid()
    _prewarmed(pid, "running")
    _set_criteria(pid, "failed", error="扫描件缺文字层（extraction_failed）")

    detail = asyncio.run(criteria_gate.criteria_start_failure(pid, _TENANT))

    assert detail is not None
    assert "重新上传" in detail
    assert "扫描件缺文字层" in detail


# ── 任务侧：等就绪自动开跑 / 等不到明确失败 ────────────────────────────────────


def _capture_task_writes(monkeypatch) -> list[dict]:
    captured: list[dict] = []
    monkeypatch.setattr(tw, "upsert_tender_task", lambda payload: captured.append(payload))
    monkeypatch.setattr(tw, "update_tender_progress", lambda *a, **k: None)

    async def _no_compare(*_a, **_k):
        return None

    monkeypatch.setattr(tw, "maybe_schedule_compare", _no_compare)
    return captured


def _forbid_evaluation(monkeypatch) -> None:
    async def _never(**_kwargs):
        pytest.fail("criteria 未就绪时绝不允许开始判分——那条路的终点是整单作废")

    monkeypatch.setattr(tw, "_run_evaluation", _never)


def test_task_starts_scoring_by_itself_once_criteria_turns_ready(monkeypatch):
    """AC1+AC3：收下的单在 criteria 就绪后自动开跑，全链路与今天一致。

    ``seen_status`` 是这条 AC 的承重断言：判分**开始那一刻**招标层必须已经是 ready，
    否则就是"收单"把 P0.4 的底线一起收掉了。
    """
    pid = _pid()
    _prewarmed(pid, "running")
    captured = _capture_task_writes(monkeypatch)
    ran: list[dict] = []
    seen_status: list[str] = []

    async def _fake_eval(**kwargs):
        row = get_project_doc(pid, _TENANT) or {}
        seen_status.append(str(row.get("criteria_status")))
        ran.append(kwargs)
        return {"verdict": "approved"}, _Meta()

    monkeypatch.setattr(tw, "_run_evaluation", _fake_eval)

    async def _scenario() -> None:
        flip = asyncio.create_task(_flip_criteria_after(pid, 0.03, "ready"))
        await tw.execute_tender_evaluation_task(
            request_id="r-admit-ready",
            tenant=_TENANT,
            directory_path="/tmp/case-admit-ready",
            source_mode="directory",
            project_id=pid,
        )
        await flip

    asyncio.run(_scenario())

    assert len(ran) == 1, "criteria 就绪后必须真的开跑判分"
    assert seen_status == ["ready"], "判分开跑时 criteria 必须已就绪（P0.4 的底线）"
    assert [c.get("status") for c in captured] == ["running", "completed"]


def test_task_fails_when_the_criteria_wait_times_out(monkeypatch):
    """AC4：等待上限到点 → 任务落 failed 带可执行文案，**绝不降级评标**。"""
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "0.02")
    pid = _pid()
    _prewarmed(pid, "running")
    captured = _capture_task_writes(monkeypatch)
    _forbid_evaluation(monkeypatch)

    asyncio.run(
        tw.execute_tender_evaluation_task(
            request_id="r-admit-timeout",
            tenant=_TENANT,
            directory_path="/tmp/case-admit-timeout",
            source_mode="directory",
            project_id=pid,
        )
    )

    assert [c.get("status") for c in captured] == ["failed"]
    assert "评分标准" in (captured[0].get("error_detail") or "")
    assert captured[0].get("progress_message") == "评分标准未就绪"


def test_task_fails_when_extraction_fails_while_the_task_waits(monkeypatch):
    """AC4：等待中 criteria 转 failed → 任务失败并指引重传，不接着评。"""
    pid = _pid()
    _prewarmed(pid, "running")
    captured = _capture_task_writes(monkeypatch)
    _forbid_evaluation(monkeypatch)

    async def _scenario() -> None:
        flip = asyncio.create_task(
            _flip_criteria_after(pid, 0.03, "failed", error="抽取命令返回结构异常")
        )
        await tw.execute_tender_evaluation_task(
            request_id="r-admit-failed",
            tenant=_TENANT,
            directory_path="/tmp/case-admit-failed",
            source_mode="directory",
            project_id=pid,
        )
        await flip

    asyncio.run(_scenario())

    assert [c.get("status") for c in captured] == ["failed"]
    assert "重新上传" in (captured[0].get("error_detail") or "")


def test_legacy_submission_without_a_project_is_never_gated(monkeypatch):
    """AC5：legacy 散单（project_id=None）没有招标层可查，一秒都不该等。"""
    captured = _capture_task_writes(monkeypatch)
    ran: list[dict] = []

    async def _fake_eval(**kwargs):
        ran.append(kwargs)
        return {"verdict": "approved"}, _Meta()

    monkeypatch.setattr(tw, "_run_evaluation", _fake_eval)

    asyncio.run(
        tw.execute_tender_evaluation_task(
            request_id="r-admit-legacy",
            tenant=_TENANT,
            directory_path="/tmp/case-admit-legacy",
            source_mode="directory",
        )
    )

    assert len(ran) == 1
    assert [c.get("status") for c in captured] == ["running", "completed"]
