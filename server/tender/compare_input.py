"""横比输入组装与护栏（判据侧）——``compare_worker`` 只留任务生命周期。

本模块回答三个问题，全部**只认项目级权威 criteria**（``tender_project_docs.criteria``）：

1. **谁可比**（KD1）：结论 ``extracted_data.criteria_ref.version`` 是否等于项目权威版本。
   ``criteria_version`` 是权威副本的内容 hash，**compute-on-read**（读时现算，免 DB 迁移，
   存量项目重评即解锁横比）。旧判据"各家转录副本 hash 字节等价"已废除——模型换版即漂移。
2. **拿什么算价格分**（KD3）：价格项与评标方法从**权威副本单源提取一次**供全池使用，
   各家结论里的 criteria 快照仅作审计，不再参与取值（否则 ref 同版本而快照漂移时会拿漂移值算分）。
3. **哪些数据不可信**（KD4）：``bid_price`` 数值校验（缺失 / 非有限 / ≤0 均非法）、
   各家金额数量级差 ≥100 倍疑似单位不一致、比较池按投标人取最新一条结论。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from server.stores.tender_compare_store import compute_criteria_hash
from server.stores.tender_doc_store import get_project_doc

logger = logging.getLogger(__name__)

PRICE_ITEM_TAG = "requires_cross_bid_comparison"


def resolve_project_criteria(project_id: str, tenant: str) -> tuple[dict[str, Any] | None, str | None]:
    """取项目级权威 criteria 及其版本（compute-on-read 内容 hash）。

    版本不落列、每次读时现算：幂等、免 DB 迁移，存量 ``tender_project_docs.criteria``
    （有内容无版本字段）自然获得版本。内容缺失 / 非 JSON / 非对象 → ``(None, None)``。

    Args:
        project_id: 招标项目 ID。
        tenant: 租户作用域。

    Returns:
        ``(criteria, version)``；无权威副本时为 ``(None, None)``。
    """
    doc = get_project_doc(project_id, tenant)
    raw = (doc or {}).get("criteria")
    if not raw:
        return None, None
    criteria = raw
    if isinstance(raw, str):
        try:
            criteria = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(
                "tender_project_criteria_unparsable",
                extra={"project_id": project_id, "tenant": tenant or "default"},
            )
            return None, None
    if not isinstance(criteria, dict):
        return None, None
    return criteria, compute_criteria_hash(criteria)


def build_criteria_ref(
    injected_version: str | None, own_criteria: Any
) -> dict[str, str] | None:
    """结论的 criteria 引用：注入过权威版本 → ``project``；否则按本家解析副本记 ``self_parsed``。

    与 ``resolve_project_criteria`` 共用同一 hash 计算（禁止两处各算一套）。
    ``self_parsed`` 结论在横比时会被排除并提示重评，不再直接封锁全池。

    Args:
        injected_version: 评标时注入给模型的项目权威版本；未注入为 None。
        own_criteria: 模型自行解析出的 criteria 副本。

    Returns:
        ``{"version", "source"}``；无版本可记（既未注入、模型也没给 criteria）时为 None。
    """
    if injected_version:
        return {"version": injected_version, "source": "project"}
    if own_criteria:
        return {"version": compute_criteria_hash(own_criteria), "source": "self_parsed"}
    return None


__all__ = [
    "PRICE_ITEM_TAG",
    "build_criteria_ref",
    "resolve_project_criteria",
]
