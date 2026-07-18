"""D10③ T3: direct-connect wall-clock/token metrics land on AgentRunMeta.

Guards against the slots-dataclass hollow-getattr pitfall documented in
``.ai_state/compound/2026-07-15-learning-slots-dataclass-hollow-getattr.md``:
``AgentRunMeta`` is ``@dataclass(slots=True)``, so a field must be declared on
the dataclass itself (not bolted on) — and the test must assert a *non-default*
value path (10/5 tokens flowing through), not just that the field exists and
happens to equal its own default.
"""

from __future__ import annotations

from server.audit.direct import run_direct_audit
from server.common.agent_bridge import AgentRunMeta
from server.core import DEFAULT_OUTPUT_SCHEMA_NAME

from tests.test_audit_direct import _FakeClient, _FakeResponse, _VALID_PAYLOAD


def _required_meta_kwargs() -> dict:
    return dict(
        request_id="rid",
        conversation_id="conv",
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        log_file="",
        result_file=None,
        result_subtype=None,
        cost_usd=0.0,
        finished_at=None,
    )


def test_agent_run_meta_declares_metrics_fields_with_zero_defaults():
    meta = AgentRunMeta(**_required_meta_kwargs())
    assert meta.wall_s == 0.0
    assert meta.input_tokens == 0
    assert meta.output_tokens == 0


async def test_run_direct_audit_populates_non_default_metrics(monkeypatch):
    request_id = "rid-direct-metrics-001"
    fake_client = _FakeClient([_FakeResponse(_VALID_PAYLOAD, input_tokens=123, output_tokens=45)])
    monkeypatch.setattr("server.audit.direct._build_client", lambda: (fake_client, "test-model"))

    _structured, meta = await run_direct_audit(
        "prompt text",
        request_id=request_id,
        tenant="acme",
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        contract_max_retry=0,
    )

    assert meta.input_tokens == 123
    assert meta.output_tokens == 45
    assert isinstance(meta.wall_s, float)
    assert meta.wall_s >= 0.0
