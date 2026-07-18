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
