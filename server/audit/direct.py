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
from anthropic import (
    APIConnectionError,
    APIStatusError,
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
)

from server.common.contract import apply_schema_semantics, is_non_retryable
from server.core import AgentRunMeta, StructuredJSON, _extract_json_object
from server.platform.config import configure_claude_runtime_env, resolve_model_max_output_tokens
from server.stores.result_store import archive_result_payload
from server.stores.session_store import new_conversation_id, utc_now

logger = logging.getLogger(__name__)

# 传输类故障（连接/鉴权/网关 5xx/超时，review round1 F2 修订）：APIConnectionError
# 覆盖连接失败与 APITimeoutError（其子类）；APIStatusError 里只有 AuthenticationError
# (401)/RateLimitError(429)/status_code>=500 才是「换路径大概率能救」的瞬时/网关故障，
# 单次回落 CLI 路径。400/403/404/422 等持久性错误（请求本身有问题，换路径同样会错）
# **不在此列**——见下方 ``_classify_status_error``，原样向上抛出、不包装不回落，
# 避免长期静默掩盖真实配置错误（review F2 原始 finding）。
_RETRYABLE_STATUS_CODE_FLOOR = 500


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

    凭据按来源分别透传（review round1 F1 修订）：原生 ``ANTHROPIC_API_KEY`` 走
    ``api_key=``（SDK 据此发 ``x-api-key`` 头），``MODEL_AUTH_TOKEN``/``MODEL_API_KEY``
    转译出的 ``ANTHROPIC_AUTH_TOKEN``（网关/LiteLLM 场景）走 ``auth_token=``（SDK 据此发
    ``Authorization: Bearer`` 头）。两者含义不同，**不能**折叠成同一个参数传——原实现把
    ``auth_token or api_key`` 一律塞进 ``auth_token=``，会让只配了原生 API key 的部署把
    凭据错发成 Bearer 头（网关侧若只认 ``x-api-key`` 会鉴权失败）。两者都配置时优先
    ``auth_token``（与既有 spike/d10_direct_spike.py 的 ``_make_client`` 同款优先级）。

    未显式传 ``timeout``：httpx 默认 ``Timeout(5.0)``（== SDK 内部
    ``HTTPX_DEFAULT_TIMEOUT``），命中该哨兵值时 anthropic SDK 会落到自身
    ``DEFAULT_TIMEOUT``（read 600s / connect 5s，见 ``anthropic._base_client``），
    与 CLI 路径的 ``API_TIMEOUT_MS=3000000``（agent_bridge.py 兜底 3000s）不同量级
    但同属"留足模型推理时间、连接层快速失败"的取向，故复用 SDK 默认值不单独覆盖
    （review round1 F4）。
    """
    runtime = configure_claude_runtime_env()
    base_url = runtime.get("anthropic_base_url")
    auth_token = runtime.get("anthropic_auth_token")
    api_key = runtime.get("anthropic_api_key")
    model = runtime.get("anthropic_model")
    if not base_url or not (auth_token or api_key) or not model:
        raise DirectTransportError(
            "AUDIT_DIRECT_CONNECT 缺网关配置（base_url / auth / model 任一为空）："
            "检查 MODEL_BASE_URL、MODEL_API_KEY|MODEL_AUTH_TOKEN、MODEL_NAME"
            "（或原生 ANTHROPIC_* 等价变量）是否已配置。"
        )
    credential_kwargs: dict[str, str] = (
        {"auth_token": auth_token} if auth_token else {"api_key": api_key}
    )
    client = AsyncAnthropic(
        base_url=base_url,
        **credential_kwargs,
        http_client=httpx.AsyncClient(trust_env=False),
    )
    return client, model


def _classify_status_error(exc: APIStatusError) -> bool:
    """判断一个 ``APIStatusError`` 是否属于「换路径大概率能救」的传输类故障。

    True(传输类, 回落一次): 401 鉴权(``AuthenticationError``) / 429 限流
    (``RateLimitError``) / 5xx 网关错误——瞬时或环境性问题，CLI 路径大概率能过。
    False(持久性错误, 不回落): 400/403/404/422 等——请求/配置本身有问题，换路径
    同样会错，包装成传输类回落只会静默掩盖真实错误（review round1 F2）。
    """
    if isinstance(exc, (AuthenticationError, RateLimitError)):
        return True
    return exc.status_code >= _RETRYABLE_STATUS_CODE_FLOOR


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
    archive_to_results: bool = True,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """一次（或契约重试后多次）``AsyncAnthropic`` 网关往返完成审核判断。

    归档接缝（critic F1）：拿到过闸结果后显式调用 ``archive_result_payload`` 写
    ``results`` 表——GET 结果端点（``routes/audit.py:190`` → ``result_store.py:182``）
    只读该表，不复刻这步会让任务 completed 但结论 404。``claude_session_id=None``（直连
    路径没有 claude-agent-sdk 会话概念）；``log_file=""``（直连没有 CLI 子进程可捕获的
    ``SessionLogger`` 日志文件——结构化指标改走下方 ``audit_direct_metrics`` 日志事件，
    GET 结果端点只读 ``result_file``/``results`` 表，不依赖 ``log_file``，留空不影响读回）。

    ``archive_to_results``（review round1 F3）：与 ``run_agent_json`` 同名参数对齐——
    ``False`` 时跳过 ``results`` 表归档（``meta.result_file=None``），供 eval/compare 等
    不落库路径复用；调用方（runner.py flag-on 分支）显式透传，不静默丢弃 opts。

    Returns:
        (structured_output, AgentRunMeta) — 与 ``run_agent_json`` 的返回形状对齐，
        使调用方（``server/audit/runner.py``）能在两条路径间无缝切换。

    Raises:
        DirectTransportError: 连接 / 鉴权 / 网关错误（含缺配置）。
        DirectContractError: 契约重试耗尽仍未拿到合法输出。
    """
    client, model = _build_client()
    max_output_tokens = resolve_model_max_output_tokens(model=model)
    if max_output_tokens is None or max_output_tokens <= 0:
        await client.close()
        raise DirectTransportError(
            "AUDIT_DIRECT_CONNECT 未配置有效输出预算：请在 MODEL_PROFILES_JSON 的当前模型条目"
            "或 CLAUDE_CODE_MAX_OUTPUT_TOKENS 中配置 max_output_tokens。"
        )
    try:
        return await _run_contract_retry_loop(
            client,
            model,
            max_output_tokens,
            prompt,
            request_id=request_id,
            tenant=tenant,
            schema_name=schema_name,
            contract_max_retry=contract_max_retry,
            project_id=project_id,
            archive_to_results=archive_to_results,
        )
    finally:
        # 每次审核构造独立 client（httpx.AsyncClient 持有连接池）；用完显式关闭，
        # 避免长跑服务进程逐单泄连接 / 文件描述符。
        await client.close()


async def _run_contract_retry_loop(
    client: AsyncAnthropic,
    model: str,
    max_output_tokens: int,
    prompt: str,
    *,
    request_id: str,
    tenant: str | None,
    schema_name: str,
    contract_max_retry: int,
    project_id: str | None,
    archive_to_results: bool,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """同一 client 内最多重试 ``contract_max_retry`` 次，直到拿到合法结构化输出并归档。"""
    conversation_id = new_conversation_id()
    last_error: Exception | None = None
    for attempt in range(contract_max_retry + 1):
        started = time.monotonic()
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except APIConnectionError as exc:
            # 连接失败 / 超时（APITimeoutError 是其子类）——传输类，单次回落 CLI 路径。
            raise DirectTransportError(str(exc)) from exc
        except APIStatusError as exc:
            # HTTP 状态错误按 _classify_status_error 分流（review round1 F2）：401/429/5xx
            # 是「换路径大概率能救」的瞬时/网关故障→包装成传输类回落；400/403/404/422 等
            # 持久性错误原样向上抛出（不包装、不回落），避免静默掩盖真实配置/请求错误。
            if _classify_status_error(exc):
                raise DirectTransportError(str(exc)) from exc
            raise
        wall_s = time.monotonic() - started

        try:
            parsed = _extract_json_object(_response_text(response))
            if parsed is None:
                raise ValueError("直连响应未解析出 JSON 对象（模型未按要求只输出 JSON）")
            structured = apply_schema_semantics(schema_name, parsed, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 — 契约类失败集合（半截 JSON/schema/语义闸），非传输故障
            last_error = exc
            # 确定性失败立即收口（2026-08-14 事故同型）：重发同一 prompt 结果必然相同。
            # 仍包成 DirectContractError——调用方据此**不回落** CLI 路径（同一超长 prompt
            # 换路径同样超长），与既有"契约类不回落"语义一致。判定与 tender 共用。
            if is_non_retryable(exc) or attempt >= contract_max_retry:
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
        # archive_to_results=False（eval/compare 等不落库路径，review round1 F3）：跳过
        # results 表归档，meta.result_file=None，与 run_agent_json 同名参数语义对齐。
        result_file = None
        if archive_to_results:
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
            result_file = result_record.result_file
        meta = AgentRunMeta(
            request_id=request_id,
            conversation_id=conversation_id,
            claude_session_id=None,
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=schema_name,
            log_file="",
            result_file=result_file,
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
