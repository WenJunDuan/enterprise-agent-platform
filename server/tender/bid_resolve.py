"""评标提交入口的预热 bid_id 解析（KD5 主链路掉落根因修复）。

2026-08-15 实测事故：招标层与投标层预热 OCR 都已 ``ready``，评标却记
``source=inline_ocr``、``bid_id=null``，对整个 case 目录重跑了一遍 inline OCR。

根因不在字段命名（前后端 ``form_json.bid_id`` 两侧一致），而在**提交时机**：前端
``canStartReview`` 刻意只看"本地选了文件"，用户可在 ``uploadBid`` 的 POST 尚未返回时就点
「开始分析」；此时 ``prewarmBidIds[bidder.id]`` 还是 ``undefined``，``JSON.stringify`` 直接
丢掉该键 → 服务端拿到的 ``bid_id`` 为空 → 读层按"无法定位当前家"回落 inline。而预热请求随后
正常完成，所以事后去查 doc 层两层都是 ``ready``——症状与根因在时间上错开。

前端侧会等在途上传（见 ``use-tender-review-page.ts``），但那只覆盖"同一次会话内"的竞态；
刷新页面、换标签页恢复、断线重连都会让内存态 ``prewarmBidIds`` 归零。因此**权威修复放在
服务端**：``tender_bid_docs`` 里本来就存着 ``(project_id, bidder_name) → bid_id``，缺 bid_id
时按投标人名回查即可，与前端时序完全解耦。
"""

from __future__ import annotations

import logging

from server.stores.tender_doc_store import list_bid_docs

logger = logging.getLogger(__name__)


def resolve_prewarm_bid_id(
    project_id: str | None,
    tenant: str,
    *,
    explicit_bid_id: str | None,
    bidder_name: str | None,
) -> tuple[str | None, str | None]:
    """解析本次评标应复用的预热 ``bid_id``。

    Args:
        project_id: 招标项目 ID；``None`` 表示 legacy 散单（不挂项目，无预热可复用）。
        tenant: 租户作用域。
        explicit_bid_id: 前端 ``form_json.bid_id``，有值即为权威。
        bidder_name: 前端 ``form_json.bidder_name``，作为回查键。

    Returns:
        ``(bid_id, reason)``。``bid_id`` 为 None 时 ``reason`` 必为具名机器码，供调用方
        渲染用户可见降级说明——**任何一条回落路径都不返回 ``(None, None)``**（AC2）。

    Note:
        同名多家时**拒绝猜测**：猜错等于拿别家材料评本家，比回落 inline OCR 危险得多。
    """
    if explicit_bid_id and explicit_bid_id.strip():
        return explicit_bid_id.strip(), None
    if not project_id:
        return None, "project_missing"
    name = (bidder_name or "").strip()
    if not name:
        return None, "bidder_name_missing"
    try:
        rows = list_bid_docs(project_id, tenant)
    except Exception:
        # 提交入口是用户交互路径：DB 故障不该把提交打回，降级 inline 仍能出结论。
        logger.warning(
            "tender_prewarm_bid_lookup_failed",
            extra={"project_id": project_id, "tenant": tenant or "default"},
            exc_info=True,
        )
        return None, "bid_lookup_failed"
    matches = [row["bid_id"] for row in rows if (row.get("bidder_name") or "").strip() == name]
    if len(matches) == 1:
        logger.info(
            "tender_prewarm_bid_recovered",
            extra={"project_id": project_id, "bid_id": matches[0], "bidder_name": name},
        )
        return matches[0], None
    return None, "bidder_name_ambiguous" if matches else "bidder_name_unmatched"
