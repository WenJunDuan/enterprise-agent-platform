"""提交评标前的 criteria 就绪闸：未就绪就别收这一单（P0.4）。

**为什么闸在提交口而不是在评标里**：线上实测评标可以在 criteria 抽取仍 ``running`` 时启动
（相差 24 秒），后续链条是确定的——证据层（S3）只在有 criteria 时接管 → 跳过 → 整份底稿退回
全量注入 → 超预算被截断 → 截断即转人工。**整单作废，而用户已经等完了全程**。
``doc_layer.wait_doc_layer_ready`` 早就多等了一档 criteria，但等待上限到点后仍放行降级，
那条注定作废的路照走不误；而它在 worker 里，任务与 token 都已经花出去了。

闸的边界刻意收窄：**只在项目确实有预热底稿记录时生效**。散单 / directory 模式 / 还没传招标
文件的项目本来就不走证据层，拒它们是无中生有的回归。

本模块单独成家而不塞进 ``doc_layer`` 或 ``routes/tender/tasks``：那两个文件分别是 277 / 320
行，都已顶到或越过 300 行的拆分线；而"提交口该不该收这一单"本身就是一个独立的变更理由。
"""

from __future__ import annotations

import logging

from server.platform.config import get_ocr_concurrency_settings
from server.stores.tender_doc_store import get_project_doc
from server.tender.doc_layer import criteria_pending

logger = logging.getLogger(__name__)

# 还在解析：用户该做的是**稍等再提交**。刻意不提"重新上传"——那会把一次正常的并发抢跑
# 变成一次无谓的重传。
_STILL_PARSING = (
    "本项目的评分标准仍在解析中，请稍后再提交评标。"
    "评分标准是逐项检索证据的依据，缺它会退回整份底稿注入并在超预算时被截断，"
    "那样出的分没有权威性。招标文件详情页的解析状态转为「已就绪」后即可提交。"
)

# 解析不会有结果了（failed / 心跳陈旧的僵尸任务）：等下去不会变好，只能重来。
_NEEDS_REUPLOAD = (
    "本项目的评分标准解析未成功，暂时无法评标：请重新上传招标文件触发重新解析，"
    "或改用可检索的电子版招标文件（扫描件缺文字层时解析常失败）。"
)


def criteria_submission_block(project_id: str, tenant: str) -> str | None:
    """本次评标提交该不该被拒；返回**用户可执行**的拒绝说明，或 ``None`` 表示放行。

    三种未就绪状态给两种处方，因为用户要做的事不同：``pending``/``running`` 且心跳新鲜 =
    稍后重试；``failed`` 或非终态但心跳陈旧（进程重启遗留的僵尸任务，等到上限也不会有结果）
    = 重新上传。

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
        # criteria_error 是抽取侧写下的具体原因（含它自己的可执行动作），原样带给用户。
        detail = str(project_doc.get("criteria_error") or "").strip()
        return f"{_NEEDS_REUPLOAD}（原因：{detail}）" if detail else _NEEDS_REUPLOAD
    if criteria_pending(project_doc, get_ocr_concurrency_settings().prewarm_stale_sec):
        return _STILL_PARSING
    logger.warning(
        "tender_criteria_stalled_at_submit",
        extra={"project_id": project_id, "criteria_status": status or "(empty)"},
    )
    return _NEEDS_REUPLOAD
