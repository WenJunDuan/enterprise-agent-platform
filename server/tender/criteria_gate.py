"""评标的 criteria 就绪闸：等不来结果的单不收，还在解析的收下等它（P0.4 + 2026-08-19 裁决）。

**底线（不变）**：绝不在没有 criteria 时开始判分。线上实测评标可以在 criteria 抽取仍
``running`` 时启动（相差 24 秒），后续链条是确定的——证据层（S3）只在有 criteria 时接管 →
跳过 → 整份底稿退回全量注入 → 超预算被截断 → 截断即转人工。**整单作废，而用户已经等完了
全程**。

**变的是"未就绪"的归宿**（2026-08-19 用户产品裁决，原话「传完招标文件就可以直接传投标文件，
然后就可以点开始分析，不要等」「实际上我点了分析还是在分析招标文件啊，只是交互上看起来舒服」）：

- 提交时仍在解析（``pending`` / ``running`` 且心跳新鲜）→ :func:`criteria_submission_block`
  **放行收单**，前端立刻拿到 request_id；任务在开跑判分前走 :func:`criteria_start_failure`
  等 criteria 就绪。等不到（上限到点 / 转 failed）→ **任务明确失败**，不降级评标。
- 提交时已 ``failed`` 或心跳陈旧的僵尸任务 → 维持 409 立即拒：结果等不来了，收下这一单只是
  让用户多等一场必败的评标。拒必须发生在解析请求体之前——晚一步就落上传文件、建任务记录。

闸的边界刻意收窄：**只在项目确实有预热底稿记录时生效**。散单 / directory 模式 / 还没传招标
文件的项目本来就不走证据层，拒它们或让它们等都是无中生有的回归。

本模块单独成家而不塞进 ``doc_layer`` 或 ``routes/tender/tasks``：那两个文件分别是 277 / 329
行，一个贴着、一个已越过 300 行的拆分线；而"这一单该不该收、该不该开跑"本身就是一个独立的
变更理由。doc 行的心跳判据（``criteria_pending``）留在 doc 层与 ``is_prewarm_in_flight``
同处，本模块只负责等待策略、裁决与文案。
"""

from __future__ import annotations

import asyncio
import logging
import time

from server.platform.config import get_ocr_concurrency_settings
from server.stores.tender_doc_store import get_project_doc
from server.tender import doc_layer

logger = logging.getLogger(__name__)

# 等到上限也没等到：任务已经等过了，用户该做的是**稍后重新提交**。刻意不提"重新上传"——
# 那会把一次正常的并发抢跑变成一次无谓的重传。
_STILL_PARSING = (
    "本项目的评分标准仍在解析中：本次评标已自动等待 {waited_sec} 秒仍未就绪，未开始判分。"
    "评分标准是逐项检索证据的依据，缺它会退回整份底稿注入并在超预算时被截断，"
    "那样出的分没有权威性。招标文件详情页的解析状态转为「已就绪」后重新提交即可。"
)

# 解析不会有结果了（failed / 心跳陈旧的僵尸任务）：等下去不会变好，只能重来。
_NEEDS_REUPLOAD = (
    "本项目的评分标准解析未成功，暂时无法评标：请重新上传招标文件触发重新解析，"
    "或改用可检索的电子版招标文件（扫描件缺文字层时解析常失败）。"
)


def _needs_reupload_message(project_doc: dict | None) -> str:
    """渲染"解析不会有结果了"的说明，带上抽取侧写下的具体原因（它自己含可执行动作）。"""
    detail = str((project_doc or {}).get("criteria_error") or "").strip()
    return f"{_NEEDS_REUPLOAD}（原因：{detail}）" if detail else _NEEDS_REUPLOAD


def criteria_submission_block(project_id: str, tenant: str) -> str | None:
    """本次评标提交该不该被拒；返回**用户可执行**的拒绝说明，或 ``None`` 表示收下。

    只拒"等不来结果"的那一类（``failed``，或非终态但心跳陈旧的僵尸任务——等到上限也不会有
    结果）。``pending`` / ``running`` 且心跳新鲜是**正常的并发抢跑**，收下即可，由
    :func:`criteria_start_failure` 在任务里等。

    Args:
        project_id: 招标项目 ID。
        tenant: 租户作用域。

    Returns:
        拒绝说明；可以提交时返回 ``None``。
    """
    project_doc = get_project_doc(project_id, tenant)
    if project_doc is None:
        # 没有预热底稿记录 → 本来就不走证据层（散单 / directory / 未传招标文件），照旧放行。
        return None
    status = str(project_doc.get("criteria_status") or "").strip()
    if status == "ready":
        return None
    if status == "failed":
        return _needs_reupload_message(project_doc)
    if doc_layer.criteria_pending(project_doc, get_ocr_concurrency_settings().prewarm_stale_sec):
        # 收单（2026-08-19 用户裁决）：还在解析 → 收下，任务开跑判分前自己等就绪。
        return None
    logger.warning(
        "tender_criteria_stalled_at_submit",
        extra={"project_id": project_id, "criteria_status": status or "(empty)"},
    )
    return _needs_reupload_message(project_doc)


async def wait_criteria_ready(project_id: str, tenant: str) -> str:
    """等招标层的 criteria 抽取到就绪，并回报"为什么不等了"。

    从 ``doc_layer.wait_doc_layer_ready`` 收编而来（2026-08-19）：那里"多等一档 criteria"的
    所有出口都通向 inline 回落**降级**，而这一档的正确归宿是"等不到就任务失败"——无 criteria
    时证据层（S3）整个跳过，整份底稿退回全量注入、超预算被截断，出来的分没有权威性
    （2026-08-17 实测：784KB 底稿被砍到 23%）。轮询节奏沿用 doc 层同一组常量（按属性读，
    测试可整体调快），上限沿用 ``doc_layer_wait_cap_sec``（从 ``TENDER_TIMEOUT_SEC`` 派生）
    ——等待期不占并发名额也不烧 token，不需要另设一档配置。

    Args:
        project_id: 招标项目 ID。
        tenant: 租户作用域。

    Returns:
        - ``ready``：criteria 已落库，可以判分。
        - ``failed``：抽取失败，或非终态但心跳陈旧（进程重启遗留的僵尸任务）——不会有结果了。
        - ``absent``：项目没有预热底稿记录（散单 / directory），本档不适用。
        - ``wait_cap_reached``：上限内仍在解析中。
    """
    settings = get_ocr_concurrency_settings()
    deadline = time.monotonic() + settings.doc_layer_wait_cap_sec
    next_log_at = 0.0
    while True:
        project_doc = await asyncio.to_thread(get_project_doc, project_id, tenant)
        if project_doc is None:
            return "absent"
        if str(project_doc.get("criteria_status") or "").strip() == "ready":
            return "ready"
        if not doc_layer.criteria_pending(project_doc, settings.prewarm_stale_sec):
            # failed / 僵尸 running / 坏时间戳：等下去不会变好（判据见 doc_layer.criteria_pending）。
            return "failed"
        now = time.monotonic()
        if now >= deadline:
            return "wait_cap_reached"
        if now >= next_log_at:
            next_log_at = now + doc_layer.DOC_LAYER_LOG_INTERVAL_SEC
            logger.info(
                "tender_criteria_wait",
                extra={
                    "project_id": project_id,
                    "criteria_status": project_doc.get("criteria_status"),
                    "remaining_sec": round(deadline - now, 1),
                },
            )
        await asyncio.sleep(doc_layer.DOC_LAYER_POLL_SEC)


async def criteria_start_failure(project_id: str, tenant: str) -> str | None:
    """开跑判分前等评分标准就绪；返回**任务失败说明**，或 ``None`` 表示可以开跑。

    收单的另一半：提交口收下了还在解析的单，判分前必须在这里把它等回来。等不到就让任务
    明确失败——**不存在"等超时就凑合评"这条路**，那正是 P0.4 要根治的整单作废。

    Args:
        project_id: 招标项目 ID。
        tenant: 租户作用域。

    Returns:
        任务失败说明（用户可执行）；criteria 已就绪、或项目本就没有预热底稿记录时返回 ``None``。
    """
    outcome = await wait_criteria_ready(project_id, tenant)
    if outcome in {"ready", "absent"}:
        return None
    if outcome == "wait_cap_reached":
        waited_sec = int(get_ocr_concurrency_settings().doc_layer_wait_cap_sec)
        logger.warning(
            "tender_criteria_wait_timeout",
            extra={"project_id": project_id, "waited_sec": waited_sec},
        )
        return _STILL_PARSING.format(waited_sec=waited_sec)
    project_doc = await asyncio.to_thread(get_project_doc, project_id, tenant)
    logger.warning(
        "tender_criteria_unavailable_at_start",
        extra={
            "project_id": project_id,
            "criteria_status": (project_doc or {}).get("criteria_status") or "(empty)",
        },
    )
    return _needs_reupload_message(project_doc)
