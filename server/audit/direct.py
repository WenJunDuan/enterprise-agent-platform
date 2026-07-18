"""Direct anthropic-SDK audit path (D10①): one gateway round-trip via ``AsyncAnthropic``,
bypassing the ``claude-agent-sdk`` CLI subprocess that ``run_agent_json`` drives.

WHY: E1 直连 spike 证明 anthropic SDK 直打网关比 claude-agent-sdk CLI 子进程快
40-60%（中位 19s vs ~31s），质量零损失，且享网关 prompt cache 红利、消除 CLI 独有
故障类（流式解析崩溃/buffer 上限）。全部证据见
``.ai_state/sprints/2026-07-18-prompt-single-source/spike/*.jsonl``。

本模块只做「一次网关往返 + 契约重试 + 归档」；prompt 组装（案件材料/本地规则内联）
仍由 ``server/audit/runner.py`` 负责并作为参数传入——避免 runner.py（调度方，flag
门控 + 回落语义）与 direct.py（执行方）互相 import 造成循环依赖。

flag 门控（``AUDIT_DIRECT_CONNECT``，默认关）+ 回落语义（传输类单次回落 CLI /
契约类不回落）由 ``server/audit/runner.py`` 实现，本模块只抛出两类语义清晰的异常
供调用方分流，自身不知道「CLI 路径」的存在。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic

from server.common.contract import apply_schema_semantics
from server.core import AgentRunMeta, StructuredJSON, _extract_json_object
from server.platform.config import configure_claude_runtime_env
from server.stores.result_store import archive_result_payload
from server.stores.session_store import new_conversation_id, utc_now

logger = logging.getLogger(__name__)

# 审核结论（verdict/explanation/reasons/policy_refs/evidence_chain）比表单回填小得多；
# 直连单跳无需像 agent_bridge 的 CLAUDE_CODE_MAX_OUTPUT_TOKENS(32000) 那样为多轮
# <think> 累积预留 buffer。4096 足够容纳审核 JSON，避免过度保守拖慢/多计费。
MAX_TOKENS = 4096

# 传输类故障（连接/鉴权/网关 5xx/超时，critic F2 归类）：APIConnectionError 覆盖连接失败
# 与 APITimeoutError（其子类）；APIStatusError 覆盖全部 HTTP 状态错误（含 401 鉴权 /
# 429 限流 / 5xx 网关错误）。命中即单次回落 CLI 路径，由调用方（runner.py）决定。
_TRANSPORT_EXCEPTIONS: tuple[type[Exception], ...] = (APIConnectionError, APIStatusError)


class DirectTransportError(RuntimeError):
    """连接 / 鉴权 / 网关 5xx / 超时等传输层故障——秒级失败，调用方按设计单次回落 CLI 路径。"""


class DirectContractError(RuntimeError):
    """契约类失败（半截 JSON / schema 校验不过）重试耗尽——模型输出问题，换路径大概率同败，
    调用方直接失败上报，禁止静默降级回落。"""


def _build_client() -> tuple[AsyncAnthropic, str]:
    """构造直连 client + 解析模型名；缺任一关键配置立即 fail-fast（不发起网络请求）。

    ``trust_env=False`` 显式关闭 httpx 的环境代理继承——内网部署常见 HTTP_PROXY/SOCKS
    环境变量会劫持网关流量到无关代理（compound codex-proxy trick 2026-07-18 增补），
    必须显式关闭而非依赖默认行为。**必须传一个原生 ``httpx.AsyncClient(trust_env=False)``**，
    不能用 anthropic SDK 自带的 ``DefaultAsyncHttpxClient``——后者内部无条件调用
    ``get_environment_proxies()`` 拼 ``mounts``（不看 ``trust_env`` 参数），代理环境变量
    存在时会强行按环境代理挂载 transport，在无 ``socksio`` 的机器上直接对 SOCKS 代理抛
    ``ImportError``（本仓库实测：sandbox 环境变量含 ``all_proxy=socks5://...`` 时复现）。
    """
    runtime = configure_claude_runtime_env()
    base_url = runtime.get("anthropic_base_url")
    auth_token = runtime.get("anthropic_auth_token") or runtime.get("anthropic_api_key")
    model = runtime.get("anthropic_model")
    if not base_url or not auth_token or not model:
        raise DirectTransportError(
            "AUDIT_DIRECT_CONNECT 缺网关配置（base_url / auth / model 任一为空）："
            "检查 MODEL_BASE_URL、MODEL_API_KEY|MODEL_AUTH_TOKEN、MODEL_NAME"
            "（或原生 ANTHROPIC_* 等价变量）是否已配置。"
        )
    client = AsyncAnthropic(
        base_url=base_url,
        auth_token=auth_token,
        http_client=httpx.AsyncClient(trust_env=False),
    )
    return client, model


def _response_text(response: Any) -> str:
    """拼接响应里所有 text 类型内容块（审核结论只需文本 JSON，不涉及工具调用块）。"""
    blocks = getattr(response, "content", None) or []
    return "".join(
        str(getattr(block, "text", "") or "")
        for block in blocks
        if getattr(block, "type", None) == "text"
    )


async def run_direct_audit(
    prompt: str,
    *,
    request_id: str,
    tenant: str | None,
    schema_name: str,
    contract_max_retry: int,
    project_id: str | None = None,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """一次（或契约重试后多次）``AsyncAnthropic`` 网关往返完成审核判断。

    归档接缝（critic F1）：拿到过闸结果后显式调用 ``archive_result_payload`` 写
    ``results`` 表——GET 结果端点（``routes/audit.py:190`` → ``result_store.py:182``）
    只读该表，不复刻这步会让任务 completed 但结论 404。``claude_session_id=None``（直连
    路径没有 claude-agent-sdk 会话概念）；``log_file=""``（直连没有 CLI 子进程可捕获的
    ``SessionLogger`` 日志文件——结构化指标改走下方 ``audit_direct_metrics`` 日志事件，
    GET 结果端点只读 ``result_file``/``results`` 表，不依赖 ``log_file``，留空不影响读回）。

    Returns:
        (structured_output, AgentRunMeta) — 与 ``run_agent_json`` 的返回形状对齐，
        使调用方（``server/audit/runner.py``）能在两条路径间无缝切换。

    Raises:
        DirectTransportError: 连接 / 鉴权 / 网关错误（含缺配置）。
        DirectContractError: 契约重试耗尽仍未拿到合法输出。
    """
    client, model = _build_client()
    try:
        return await _run_contract_retry_loop(
            client,
            model,
            prompt,
            request_id=request_id,
            tenant=tenant,
            schema_name=schema_name,
            contract_max_retry=contract_max_retry,
            project_id=project_id,
        )
    finally:
        # 每次审核构造独立 client（httpx.AsyncClient 持有连接池）；用完显式关闭，
        # 避免长跑服务进程逐单泄连接 / 文件描述符。
        await client.close()


async def _run_contract_retry_loop(
    client: AsyncAnthropic,
    model: str,
    prompt: str,
    *,
    request_id: str,
    tenant: str | None,
    schema_name: str,
    contract_max_retry: int,
    project_id: str | None,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """同一 client 内最多重试 ``contract_max_retry`` 次，直到拿到合法结构化输出并归档。"""
    conversation_id = new_conversation_id()
    last_error: Exception | None = None
    for attempt in range(contract_max_retry + 1):
        started = time.monotonic()
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except _TRANSPORT_EXCEPTIONS as exc:
            raise DirectTransportError(str(exc)) from exc
        wall_s = time.monotonic() - started

        try:
            parsed = _extract_json_object(_response_text(response))
            if parsed is None:
                raise ValueError("直连响应未解析出 JSON 对象（模型未按要求只输出 JSON）")
            structured = apply_schema_semantics(schema_name, parsed, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 — 契约类失败集合（半截 JSON/schema/语义闸），非传输故障
            last_error = exc
            if attempt >= contract_max_retry:
                raise DirectContractError(str(exc)) from exc
            logger.warning(
                "audit direct-connect attempt failed (%s, %d/%d), retrying: %s",
                type(exc).__name__,
                attempt + 1,
                contract_max_retry + 1,
                exc,
                extra={"request_id": request_id, "tenant": tenant or "default"},
            )
            continue

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        logger.info(
            "audit_direct_metrics",
            extra={
                "request_id": request_id,
                "tenant": tenant or "default",
                "wall_s": round(wall_s, 3),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )
        finished_at = utc_now()
        result_record = archive_result_payload(
            request_id=request_id,
            tenant=tenant,
            project_id=project_id,
            conversation_id=conversation_id,
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=schema_name,
            request_mode="direct",
            result_subtype="success",
            cost_usd=0.0,
            prompt_preview=prompt[:200],
            response=structured,
            created_at=finished_at,
        )
        meta = AgentRunMeta(
            request_id=request_id,
            conversation_id=conversation_id,
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=schema_name,
            log_file="",
            result_file=result_record.result_file,
            result_subtype="success",
            cost_usd=0.0,
            finished_at=finished_at,
            wall_s=round(wall_s, 3),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return structured, meta
    # 不可达：循环要么 return 要么在最后一次 attempt 抛 DirectContractError。
    raise AssertionError("unreachable: direct audit retry loop exited without returning") from last_error
