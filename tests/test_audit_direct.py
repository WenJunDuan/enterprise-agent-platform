"""D10① T2 unit tests: server/audit/direct.py — the AsyncAnthropic direct-connect path.

Covers design.md T2 acceptance (flag-on branch):
- fail-fast when gateway config is missing (no network call attempted).
- mock-transport success: results-table archival + GET-equivalent readback
  (critic F1 — the archival splice this design exists to close).
- contract-class retry: retries up to contract_max_retry, then raises
  DirectContractError (no fallback decided here — that's runner.py's job).
- transport-class failure: wrapped as DirectTransportError on the first call,
  no in-function retry (single fast failure, so the caller can fall back once).

anthropic's AsyncAnthropic/client.messages.create is never actually invoked over
the network — every test replaces ``server.audit.direct._build_client`` with a
fake client, per project convention (no real gateway calls in tests).
"""

from __future__ import annotations

import httpx
import pytest
from anthropic import APIConnectionError, APIStatusError

from server.audit.direct import (
    DirectContractError,
    DirectTransportError,
    _build_client,
    run_direct_audit,
)
from server.core import DEFAULT_OUTPUT_SCHEMA_NAME
from server.stores.result_store import get_result_payload_by_request_id


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, text: str, *, input_tokens: int = 10, output_tokens: int = 5) -> None:
        self.content = [_FakeTextBlock(text)]
        self.usage = _FakeUsage(input_tokens, output_tokens)


class _FakeMessages:
    def __init__(self, results: list) -> None:
        self._results = list(results)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        result = self._results[min(self.calls, len(self._results)) - 1]
        if isinstance(result, Exception):
            raise result
        return result


class _FakeClient:
    def __init__(self, results: list) -> None:
        self.messages = _FakeMessages(results)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


_VALID_PAYLOAD = (
    '{"verdict": "manual_review", "manual_review_reason": "rule_gap", '
    '"explanation": "mock 直连响应：无适用规则"}'
)


class TestBuildClient:
    def test_fails_fast_when_gateway_config_missing(self, monkeypatch):
        for name in (
            "MODEL_BASE_URL",
            "ANTHROPIC_BASE_URL",
            "MODEL_API_KEY",
            "MODEL_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "MODEL_NAME",
            "ANTHROPIC_MODEL",
        ):
            monkeypatch.delenv(name, raising=False)

        with pytest.raises(DirectTransportError):
            _build_client()

    def test_succeeds_when_gateway_config_present(self, monkeypatch):
        # conftest.py already sets MODEL_BASE_URL / ANTHROPIC_API_KEY / MODEL_NAME
        # process-wide for the whole test session — no per-test setup needed.
        client, model = _build_client()
        assert model == "test-model"
        assert client is not None

    def test_native_api_key_passed_as_api_key_not_bearer(self, monkeypatch):
        """review F1: 原生 API key（无 auth token）走 ``api_key=``（x-api-key 头），
        不能折叠成 ``auth_token=``（Bearer 头）——否则只认 x-api-key 的网关会鉴权失败。"""
        captured: dict = {}

        class _CaptureClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr("server.audit.direct.AsyncAnthropic", _CaptureClient)
        # conftest 设了 ANTHROPIC_API_KEY；清掉任何 auth token 来源，确保只剩 api_key。
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("MODEL_AUTH_TOKEN", raising=False)

        _build_client()
        assert captured.get("api_key")
        assert "auth_token" not in captured

    def test_auth_token_passed_as_bearer_not_api_key(self, monkeypatch):
        """review F1: 配了 auth token（网关/LiteLLM 场景）走 ``auth_token=``（Bearer 头），
        并优先于 api_key。"""
        captured: dict = {}

        class _CaptureClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr("server.audit.direct.AsyncAnthropic", _CaptureClient)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-fake-bearer-token-not-real")

        _build_client()
        assert captured.get("auth_token") == "test-fake-bearer-token-not-real"
        assert "api_key" not in captured

    def test_client_uses_sdk_default_timeout_not_httpx_5s(self, monkeypatch):
        """review F4: 不显式传 timeout——httpx 默认 Timeout(5.0) 命中 SDK 的
        HTTPX_DEFAULT_TIMEOUT 哨兵，SDK 落到自身 DEFAULT_TIMEOUT（read 600s / connect 5s），
        不会因 httpx 5s 默认而误触发超时回落。"""
        client, _model = _build_client()
        assert client.timeout.read == 600
        assert client.timeout.connect == 5.0


class TestRunDirectAuditSuccess:
    async def test_archives_to_results_table_and_reads_back(self, monkeypatch):
        request_id = "rid-direct-success-001"
        fake_client = _FakeClient([_FakeResponse(_VALID_PAYLOAD)])
        monkeypatch.setattr(
            "server.audit.direct._build_client", lambda: (fake_client, "test-model")
        )

        structured, meta = await run_direct_audit(
            "prompt text",
            request_id=request_id,
            tenant="acme",
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            contract_max_retry=1,
        )

        assert structured["verdict"] == "manual_review"
        assert meta.request_id == request_id
        assert meta.claude_session_id is None
        assert meta.log_file == ""
        assert meta.result_file

        # critic F1: GET 结果端点只读 results 表 — 归档接缝必须让读回可用。
        payload = get_result_payload_by_request_id(request_id=request_id, tenant="acme")
        assert payload is not None
        assert payload["response"]["verdict"] == "manual_review"
        assert fake_client.messages.calls == 1
        # 每次审核构造独立 httpx client；用完必须关闭，防长跑服务进程逐单泄连接。
        assert fake_client.closed is True


class TestRunDirectAuditContractRetry:
    async def test_retries_once_then_succeeds(self, monkeypatch):
        request_id = "rid-direct-retry-success-001"
        fake_client = _FakeClient(
            [_FakeResponse("not json at all"), _FakeResponse(_VALID_PAYLOAD)]
        )
        monkeypatch.setattr(
            "server.audit.direct._build_client", lambda: (fake_client, "test-model")
        )

        structured, _meta = await run_direct_audit(
            "prompt text",
            request_id=request_id,
            tenant="acme",
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            contract_max_retry=1,
        )

        assert structured["verdict"] == "manual_review"
        assert fake_client.messages.calls == 2

    async def test_raises_directcontracterror_after_retries_exhausted(self, monkeypatch):
        request_id = "rid-direct-retry-exhausted-001"
        fake_client = _FakeClient([_FakeResponse("not json"), _FakeResponse("still not json")])
        monkeypatch.setattr(
            "server.audit.direct._build_client", lambda: (fake_client, "test-model")
        )

        with pytest.raises(DirectContractError):
            await run_direct_audit(
                "prompt text",
                request_id=request_id,
                tenant="acme",
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                contract_max_retry=1,
            )
        assert fake_client.messages.calls == 2

        # 契约类失败不落库（未过闸的输出不该出现在 results 表里）。
        assert get_result_payload_by_request_id(request_id=request_id, tenant="acme") is None


class TestRunDirectAuditTransport:
    async def test_connection_error_wrapped_as_directtransporterror(self, monkeypatch):
        request = httpx.Request("POST", "http://test-gateway:4000/v1/messages")
        fake_client = _FakeClient([APIConnectionError(request=request)])
        monkeypatch.setattr(
            "server.audit.direct._build_client", lambda: (fake_client, "test-model")
        )

        with pytest.raises(DirectTransportError):
            await run_direct_audit(
                "prompt text",
                request_id="rid-direct-transport-001",
                tenant="acme",
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                contract_max_retry=2,
            )
        # 传输类故障不在本函数内重试（秒级失败，交调用方按设计单次回落 CLI 路径）。
        assert fake_client.messages.calls == 1
        # 异常路径也必须走 finally 关闭 client（不因失败而泄连接）。
        assert fake_client.closed is True

    async def test_gateway_5xx_wrapped_as_directtransporterror(self, monkeypatch):
        request = httpx.Request("POST", "http://test-gateway:4000/v1/messages")
        response = httpx.Response(status_code=502, request=request)
        fake_client = _FakeClient(
            [APIStatusError("bad gateway", response=response, body=None)]
        )
        monkeypatch.setattr(
            "server.audit.direct._build_client", lambda: (fake_client, "test-model")
        )

        with pytest.raises(DirectTransportError):
            await run_direct_audit(
                "prompt text",
                request_id="rid-direct-transport-002",
                tenant="acme",
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                contract_max_retry=0,
            )
        assert fake_client.messages.calls == 1

    async def test_client_4xx_propagates_without_wrapping_or_fallback(self, monkeypatch):
        """review F2: 400/404/422 等持久性客户端错误原样向上抛出（不包装成
        DirectTransportError，故调用方 runner 不会误当传输类回落）——避免静默掩盖真实
        请求/配置错误。"""
        request = httpx.Request("POST", "http://test-gateway:4000/v1/messages")
        response = httpx.Response(status_code=400, request=request)
        fake_client = _FakeClient(
            [APIStatusError("bad request", response=response, body=None)]
        )
        monkeypatch.setattr(
            "server.audit.direct._build_client", lambda: (fake_client, "test-model")
        )

        # 原样传播 APIStatusError；DirectTransportError 是 RuntimeError，不会被这里捕获——
        # 若实现误把 400 包装成传输类，本断言会失败（正是我们要防的回归）。
        with pytest.raises(APIStatusError):
            await run_direct_audit(
                "prompt text",
                request_id="rid-direct-4xx-001",
                tenant="acme",
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                contract_max_retry=2,
            )
        assert fake_client.messages.calls == 1
        assert fake_client.closed is True
