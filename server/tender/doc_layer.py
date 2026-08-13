"""Tender 评标读层：预热 OCR 底稿的读取、in-flight 判定、等待与补跑（H3 从 runner 抽出）。

从 ``server.tender.runner`` 抽出（H3：runner.py 基线 328 行已越 300 线，本 sprint 净增上界 40 行，
超出即拆——与 ``server/ocr/vlm_client.py`` 同一条 design 纪律）。本模块只回答一个问题：
**这次评标能不能直接用上传时预热好的底稿；不能的话该等、该补跑、还是该回落 inline OCR**。

评标主流程（context 组装 / 结论 warning 注入 / 模型调用）仍在 ``runner``；
**补底稿重跑那一侧的写动作**在 ``server.tender.doc_rerun``（review N4：读/写职责分家）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime

from server.platform.config import get_ocr_concurrency_settings
from server.stores.tender_doc_store import OCR_STATUSES, get_bid_doc, get_project_doc
from server.tender.context_slim import build_slim_tender_context

logger = logging.getLogger(__name__)

# R6-R2 复用预热 OCR：等招标层 + 当前家投标层 OCR 就绪。等待**上限**不再是拍脑袋的 360s，
# 而是从 tender 总预算派生（get_ocr_concurrency_settings().doc_layer_wait_cap_sec，H3 KD5）——
# 360s 到点无条件回落 inline 是"双跑正反馈"的源头之一。
DOC_LAYER_POLL_SEC = 3.0
DOC_LAYER_LOG_INTERVAL_SEC = 60.0

# doc 层可复用的底稿状态：degraded/partial 有内容，退回 inline 重 OCR 只会白烧一遍资源；
# 它们的质量问题走结论 warning 显式暴露，而不是假装无底稿。
DOC_LAYER_USABLE_STATUSES = frozenset({"ready", "degraded", "partial"})
DOC_LAYER_TERMINAL_STATUSES = DOC_LAYER_USABLE_STATUSES | {"failed"}
# 需要"入口自动重跑一次预热"的降级态。
DOC_LAYER_IMPAIRED_STATUSES = frozenset({"degraded", "partial"})


def doc_ocr_status(row: dict | None) -> str | None:
    """读 doc 行的 ocr_status 并校验枚举；未知值 fail-fast。

    绝不把未识别状态静默当 ready——doc 状态是"能否直接拿这份底稿评标"的唯一开关，
    漏接一个新枚举值的代价是拿残缺底稿出结论。
    """
    if row is None:
        return None
    status = row.get("ocr_status")
    if status not in OCR_STATUSES:
        raise ValueError(f"unknown ocr_status {status!r} in tender doc layer")
    return status


def is_prewarm_in_flight(row: dict | None, *, stale_sec: float) -> bool:
    """预热是否真的在途（KD5 in-flight oracle）。

    预热是 upload 端点起的后台 task，**没有任务注册表可查**，唯一可观测面是 doc 行本身：
    ``ocr_status=running`` 且 ``updated_at`` 距今 < ``stale_sec``（预热流水线以 doc 级 60s
    ticker 持续刷新）。进程重启遗留的僵尸 running 因心跳停摆而变陈旧，按 failed 处理。
    """
    if row is None or row.get("ocr_status") != "running":
        return False
    raw = row.get("updated_at")
    if not isinstance(raw, str):
        return False
    try:
        updated_at = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - updated_at).total_seconds() < stale_sec


def _build_doc_context(
    project_id: str, bid_id: str | None, tenant: str, *, slim: bool
) -> str | None:
    """P2 评标读层公共体：取招标层 + **当前被评标这一家**的投标层底稿，拼成上下文字符串。

    全量版与 D8 瘦身版只差"招标底稿要不要按 criteria 瘦"一处（review F10：两个 loader 曾是
    逐行孪生，读层判据改一次要同步改两遍）。

    **P1-1 修复**：只加载当前家（by bid_id）。旧实现拼接所有投标文件 → 多家材料污染同一
    context，错乱 claim_id/scoring。无 bid_id（legacy 散单/无法定位当前家）→ 返回 None 回落
    串行 OCR（天然正确，case_path 就是该家散单目录）。招标层或当前家 not-ready/failed/缺失
    → 返回 None。DB/IO 异常 → 静默返回 None，**绝不拖垮评标**。

    Args:
        project_id: 招标项目 ID。
        bid_id: 当前被评标的投标文件 ID；为 None 时跳过读层（安全回落）。
        tenant: 租户作用域。
        slim: 招标底稿是否走 D8 criteria 驱动瘦身；投标底稿任何情况下都原样透传。

    Returns:
        "招标底稿 + 当前家投标底稿"组合字符串，或 None 触发回落。

    Raises:
        ValueError: doc 行带未知 ocr_status（见 :func:`doc_ocr_status`）。
    """
    # 无 bid_id → 无法精确定位当前家，绝不混入其他家材料，直接回落
    if not bid_id:
        return None
    try:
        project_doc = get_project_doc(project_id, tenant)
        if doc_ocr_status(project_doc) not in DOC_LAYER_USABLE_STATUSES:
            return None
        bid = get_bid_doc(project_id, bid_id, tenant)
        if doc_ocr_status(bid) not in DOC_LAYER_USABLE_STATUSES or not bid.get("ocr_text"):
            return None
        tender_text = project_doc["ocr_text"]
        if slim:
            criteria = _parse_stored_criteria(project_doc.get("criteria"))
            slim_text = (
                build_slim_tender_context(tender_text, criteria, file_name=project_id)
                if criteria is not None
                else None
            )
            # criteria 缺失、或瘦身产不出完整结果 → 保留招标全文（宁可长，不可缺）
            tender_text = slim_text if slim_text is not None else tender_text
        bidder = bid.get("bidder_name") or bid["bid_id"]
        parts: list[str] = [
            f"=== 招标文件底稿 ===\n{tender_text}",
            f"=== 投标文件（{bidder}）底稿 ===\n{bid['ocr_text']}",
        ]
        return "\n\n".join(parts)
    except ValueError:
        # 枚举违约是**内部不变量被破坏**，必须炸出来（与 wait_doc_layer_ready 同一归宿）；
        # blanket catch 只留给下面的 DB/IO 故障，否则同一个 ValueError 有两种命运（review F4）。
        raise
    except Exception:
        logger.warning(
            "doc layer context load failed, falling back",
            extra={"project_id": project_id, "bid_id": bid_id, "slim": slim},
            exc_info=True,
        )
        return None


def load_doc_layer_context(project_id: str, bid_id: str | None, tenant: str) -> str | None:
    """读层全量版：招标底稿整份进上下文。语义见 :func:`_build_doc_context`。"""
    return _build_doc_context(project_id, bid_id, tenant, slim=False)


def slim_context_enabled() -> bool:
    """Return True when D8 criteria-driven tender context slimming is enabled."""
    return os.getenv("TENDER_SLIM_CONTEXT", "0").lower() in {"1", "true", "yes"}


def _parse_stored_criteria(raw: str | None) -> dict | None:
    """Parse stored criteria JSON for the D8 slimming path, tolerating missing or invalid data."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def load_doc_layer_context_slim(project_id: str, bid_id: str | None, tenant: str) -> str | None:
    """读层瘦身版（D8）：招标底稿按 criteria 裁剪，裁不安全时自动回落全文。

    语义见 :func:`_build_doc_context`；投标底稿永远原样透传，不参与瘦身。
    """
    return _build_doc_context(project_id, bid_id, tenant, slim=True)


async def wait_doc_layer_ready(project_id: str, bid_id: str, tenant: str) -> str:
    """等招标层 + 当前家投标层预热 OCR 到终态，并回报"为什么不等了"（H3 KD5）。

    用户「上传即 OCR」后可能在 OCR 未完就点开始分析 → 评标提交时预热还在跑。此前到点即无条件
    回落 inline 全量重 OCR，而预热并不取消 → 同批文件双份流水线、负载翻倍正反馈。现在只在
    **预热确实在途**（``is_prewarm_in_flight`` oracle）时继续等；不在途才放行回落，此时无双跑。

    Returns:
        - ``terminal``：两层都到终态，可判复用/回落。
        - ``absent``：无预热记录（散单/旧路径）。
        - ``stale``：非终态但预热不在途（僵尸 running / pending）——按 failed 处理。
        - ``wait_cap_reached``：派生上限内没等到，放行 inline 回落一次（调用方加结论 warning）。
        - ``unreadable``：doc 层读失败。

    Raises:
        ValueError: doc 行带未知 ocr_status（fail-fast，见 :func:`doc_ocr_status`）。
    """
    settings = get_ocr_concurrency_settings()
    deadline = time.monotonic() + settings.doc_layer_wait_cap_sec
    next_log_at = 0.0
    while True:
        try:
            proj = await asyncio.to_thread(get_project_doc, project_id, tenant)
            bid = await asyncio.to_thread(get_bid_doc, project_id, bid_id, tenant)
        except Exception:
            logger.warning("tender_doc_layer_read_failed", exc_info=True)
            return "unreadable"
        proj_status = doc_ocr_status(proj)
        bid_status = doc_ocr_status(bid)
        if proj is None or bid is None:
            return "absent"
        if (
            proj_status in DOC_LAYER_TERMINAL_STATUSES
            and bid_status in DOC_LAYER_TERMINAL_STATUSES
        ):
            return "terminal"
        in_flight = is_prewarm_in_flight(
            proj, stale_sec=settings.prewarm_stale_sec
        ) or is_prewarm_in_flight(bid, stale_sec=settings.prewarm_stale_sec)
        if not in_flight:
            return "stale"  # 预热没在跑 → 等下去毫无意义，放行 inline（此时无双跑）
        now = time.monotonic()
        if now >= deadline:
            return "wait_cap_reached"
        if now >= next_log_at:
            next_log_at = now + DOC_LAYER_LOG_INTERVAL_SEC
            logger.info(
                "tender_doc_layer_wait",
                extra={
                    "project_id": project_id,
                    "bid_id": bid_id,
                    "project_ocr_status": proj_status,
                    "bid_ocr_status": bid_status,
                    "remaining_sec": round(deadline - now, 1),
                },
            )
        await asyncio.sleep(DOC_LAYER_POLL_SEC)


async def read_doc_rows(
    project_id: str, bid_id: str, tenant: str
) -> tuple[dict | None, dict | None]:
    """一次取齐招标层 + 当前家投标层 doc 行（同步 SQLite 读经 to_thread 移出事件循环）。"""
    project_doc = await asyncio.to_thread(get_project_doc, project_id, tenant)
    bid_doc = await asyncio.to_thread(get_bid_doc, project_id, bid_id, tenant)
    return project_doc, bid_doc


