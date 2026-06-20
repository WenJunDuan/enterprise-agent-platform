"""External company-credit lookup tool (G3 工具契约化).

外部企业信用查询 API 的强契约工具。设计要点（round4 F1「结果先过代码校验再进上下文」）：

- **未配置**（``CREDIT_API_URL`` / ``CREDIT_API_KEY`` 任一为空）→ 返回 ``None``，调用方据此把
  评分项保持 ``manual_review``（人工），绝不臆造信用结论。
- **配置后** → 调用 API，**原始响应先按 ``.claude/contracts/tools/credit-check.schema.json`` 校验**，
  校验不过 / HTTP 错 / 网络错 / 超时 一律优雅降级返 ``None``（不 crash、不污染推理上下文）。
- **接入真实 API**：只需在 env 填 url/key（无需改代码）；若 API 原始字段名与契约不同，
  在 ``_fetch_raw`` 末尾加一层映射规范成契约字段即可。

分层：ops 是 routes 之下的 service 层，只依赖 common(契约校验) + platform(config) + 外部 httpx。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import jsonschema

from server.common.contract import JSONContractError, load_output_schema
from server.platform.config import CreditApiSettings, get_credit_api_settings

logger = logging.getLogger(__name__)

CREDIT_SCHEMA_NAME = "tools/credit-check.schema.json"


def credit_api_available(settings: CreditApiSettings | None = None) -> bool:
    """配置是否就绪（url+key 均非空）。调用方据此决定走自动查询还是 manual_review。"""
    return (settings or get_credit_api_settings()).configured


async def lookup_company_credit(
    query: str,
    *,
    settings: CreditApiSettings | None = None,
) -> dict[str, Any] | None:
    """查询企业信用；未配置或任何失败 → ``None``（调用方据此保持 manual_review）。

    Args:
        query: 企业名称或统一社会信用代码。
        settings: 可注入（测试用）；默认从 env 读。

    Returns:
        通过 credit-check 契约校验的信用结果 dict；未配置/失败/校验不过 → ``None``。
    """
    settings = settings or get_credit_api_settings()
    if not settings.configured:
        return None  # 无接口 → 跳过，交人工审核

    try:
        raw = await _fetch_raw(settings, query)
    except Exception as exc:  # 网络/HTTP/超时一律优雅降级，绝不 crash 审核流程
        logger.warning("credit api fetch failed (fallback to manual): %s", exc)
        return None

    try:
        jsonschema.validate(raw, load_output_schema(CREDIT_SCHEMA_NAME))
    except (jsonschema.ValidationError, jsonschema.SchemaError, JSONContractError) as exc:
        logger.warning("credit api response failed contract (discarded): %s", exc)
        return None
    return raw


async def _fetch_raw(settings: CreditApiSettings, query: str) -> dict[str, Any]:
    """实际 HTTP 调用。隔离成独立函数便于测试 monkeypatch / 接真实 API 时加字段映射。"""
    async with httpx.AsyncClient(timeout=settings.timeout_seconds) as client:
        response = await client.get(
            settings.url,
            params={"q": query},
            headers={"Authorization": f"Bearer {settings.key}"},
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("credit api returned a non-object JSON payload")
    return data
