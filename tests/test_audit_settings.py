"""Lock the env→AuditSettings mapping for the consolidated inline-audit knobs.

These knobs were previously read with scattered os.getenv calls inside
run_inline_directory_audit; they now flow through config.get_audit_settings.
This suite pins the defaults and the env parsing so a future edit to either
side stays observable.
"""

from __future__ import annotations

import pytest

from server.platform.config import AuditSettings, get_audit_settings

# Every env var get_audit_settings reads — cleared before each case so a stray
# value in the ambient environment can't make the defaults test flap.
_AUDIT_ENV_VARS = (
    "AUDIT_LEAN_CONTEXT",
    "AUDIT_STRUCTURED_OUTPUT",
    "AUDIT_ENABLE_READ",
    "AUDIT_CONTRACT_MAX_RETRY",
    "AUDIT_INLINE_MAX_TURNS",
)


@pytest.fixture(autouse=True)
def _clear_audit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AUDIT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_match_production_behavior() -> None:
    s = get_audit_settings()
    assert s == AuditSettings(
        lean_context=True,
        structured_output=False,
        enable_read=False,
        contract_max_retry=1,
        inline_max_turns=8,
    )


def test_allowed_tools_empty_in_default_text_mode() -> None:
    assert get_audit_settings().allowed_tools == []


@pytest.mark.parametrize(
    ("structured", "enable_read"),
    [("1", "0"), ("0", "1"), ("1", "1")],
)
def test_allowed_tools_includes_read_when_either_flag_on(
    monkeypatch: pytest.MonkeyPatch, structured: str, enable_read: str
) -> None:
    monkeypatch.setenv("AUDIT_STRUCTURED_OUTPUT", structured)
    monkeypatch.setenv("AUDIT_ENABLE_READ", enable_read)
    assert get_audit_settings().allowed_tools == ["Read"]


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on", "On"])
def test_bool_truthy_spellings(monkeypatch: pytest.MonkeyPatch, truthy: str) -> None:
    monkeypatch.setenv("AUDIT_ENABLE_READ", truthy)
    assert get_audit_settings().enable_read is True


@pytest.mark.parametrize("falsy", ["0", "false", "no", "off", "", "garbage"])
def test_bool_falsy_and_unknown_spellings(monkeypatch: pytest.MonkeyPatch, falsy: str) -> None:
    monkeypatch.setenv("AUDIT_ENABLE_READ", falsy)
    assert get_audit_settings().enable_read is False


def test_contract_max_retry_clamped_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_CONTRACT_MAX_RETRY", "-5")
    assert get_audit_settings().contract_max_retry == 0


def test_int_knobs_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_CONTRACT_MAX_RETRY", "3")
    monkeypatch.setenv("AUDIT_INLINE_MAX_TURNS", "12")
    s = get_audit_settings()
    assert (s.contract_max_retry, s.inline_max_turns) == (3, 12)


def test_settings_are_read_fresh_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """No lru_cache: changing env between calls must take effect (runtime-flippable)."""
    assert get_audit_settings().enable_read is False
    monkeypatch.setenv("AUDIT_ENABLE_READ", "1")
    assert get_audit_settings().enable_read is True
