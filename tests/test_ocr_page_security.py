"""Adversarial tests for the tender-only ocr-page Bash hook."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from server.common.agent_bridge import build_options


_OCR_PREFIX = "uv run python .claude/skills/ocr-page/ocr.py"


@pytest.fixture
def case_paths(tmp_path: Path) -> dict[str, Path]:
    """Create an in-case file, a second case, and an escaping symlink."""
    case_root = tmp_path / "case-a"
    case_root.mkdir()
    inside = case_root / "bid.pdf"
    inside.write_bytes(b"not a real PDF; the hook only checks the boundary")
    spaced = case_root / "bid copy.pdf"
    spaced.write_bytes(b"placeholder")

    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside")
    other_root = tmp_path / "case-b"
    other_root.mkdir()
    other = other_root / "bid.pdf"
    other.write_bytes(b"other case")
    escaped = case_root / "escaped.pdf"
    escaped.symlink_to(outside)
    return {
        "root": case_root,
        "inside": inside,
        "spaced": spaced,
        "outside": outside,
        "other": other,
        "escaped": escaped,
    }


def _command(file_path: Path, *flags: str, quoted: bool = False) -> str:
    rendered = f'"{file_path}"' if quoted else str(file_path)
    suffix = " ".join(flags)
    return f"{_OCR_PREFIX} {rendered}" + (f" {suffix}" if suffix else "")


def _hook(options):
    assert options.hooks is not None
    matchers = options.hooks["PreToolUse"]
    assert len(matchers) == 1
    assert matchers[0].matcher == "Bash"
    assert len(matchers[0].hooks) == 1
    return matchers[0].hooks[0]


async def _invoke(options, command: str) -> dict:
    return await _hook(options)(
        {"tool_name": "Bash", "tool_input": {"command": command}},
        "test-tool-use-id",
        {"signal": None},
    )


def _decision(response: dict) -> str:
    return response["hookSpecificOutput"]["permissionDecision"]


def test_case_root_build_options_readds_only_controlled_bash(case_paths):
    """The production wiring exposes Bash only when a case root is supplied."""
    options = build_options(case_root=case_paths["root"])

    assert options.tools is not None
    assert "Bash" in options.tools
    assert options.allowed_tools[-1] == "Bash"

    allow = asyncio.run(_invoke(options, _command(case_paths["inside"], "--pages", "7", "--seal")))
    deny = asyncio.run(
        _invoke(options, _command(case_paths["inside"], "--pages", "7; touch /tmp/d11-ta3"))
    )
    assert _decision(allow) == "allow"
    assert _decision(deny) == "deny"


def test_ocr_hook_accepts_absolute_in_case_file_and_both_flag_orders(case_paths):
    options = build_options(case_root=case_paths["root"])

    for command in (
        _command(case_paths["inside"], "--pages", "7"),
        _command(case_paths["inside"], "--pages", "7", "--seal"),
        _command(case_paths["inside"], "--seal", "--pages", "7"),
        _command(case_paths["spaced"], "--pages", "7", quoted=True),
        f"{_OCR_PREFIX} '{case_paths['spaced']}' --pages 7",
    ):
        response = asyncio.run(_invoke(options, command))
        assert _decision(response) == "allow", command


def test_ocr_hook_denies_shell_injection_and_anchored_suffixes(case_paths, tmp_path):
    options = build_options(case_root=case_paths["root"])
    marker = tmp_path / "must-not-be-created"
    commands = [
        f"{_OCR_PREFIX} {case_paths['inside']}; touch {marker}",
        f"{_OCR_PREFIX} {case_paths['inside']} `touch {marker}`",
        f"{_OCR_PREFIX} {case_paths['inside']} $(touch {marker})",
        f"{_OCR_PREFIX} {case_paths['inside']} | touch {marker}",
        f"{_OCR_PREFIX} {case_paths['inside']} && touch {marker}",
        f"{_OCR_PREFIX} {case_paths['inside']}\ntouch {marker}",
        _command(case_paths["inside"], "--pages", f"3; touch {marker}"),
    ]

    for command in commands:
        response = asyncio.run(_invoke(options, command))
        assert _decision(response) == "deny", command
        assert not marker.exists(), command


def test_ocr_hook_denies_path_escape_cross_case_and_symlink_escape(case_paths):
    options = build_options(case_root=case_paths["root"])
    commands = [
        _command(case_paths["root"] / ".." / "outside.pdf"),
        _command(case_paths["outside"]),
        _command(case_paths["other"]),
        _command(case_paths["escaped"]),
        _command(case_paths["root"] / "missing.pdf"),
    ]

    for command in commands:
        response = asyncio.run(_invoke(options, command))
        assert _decision(response) == "deny", command


def test_ocr_hook_denies_invalid_page_ranges(case_paths):
    options = build_options(case_root=case_paths["root"])
    invalid_specs = ("-1", "0", "abc", "3 4", "8-7", str(2**63), "9" * 5000)

    for spec in invalid_specs:
        response = asyncio.run(_invoke(options, _command(case_paths["inside"], "--pages", spec)))
        assert _decision(response) == "deny", spec


def test_default_options_have_no_ocr_hook_or_bash():
    """Audit/expense callers that omit case_root retain the existing tool surface."""
    options = build_options()

    assert options.hooks is None
    assert options.tools is not None
    assert "Bash" not in options.tools


def test_case_root_is_explicitly_forwarded_through_command_adapter(monkeypatch, tmp_path):
    import server.common.command_adapter as adapter

    captured: dict[str, object] = {}

    async def fake_run_agent_json(prompt, **opts):
        captured.update(opts)
        return {}, None

    case_root = tmp_path / "case"
    monkeypatch.setattr(adapter, "run_agent_json", fake_run_agent_json)
    asyncio.run(
        adapter.run_command_json(
            "tender-evaluate",
            str(case_root),
            schema_name="tender-result",
            case_root=case_root,
        )
    )

    assert captured["case_root"] is case_root


def test_tender_runner_binds_directory_as_case_root(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import server.tender.runner as runner

    captured: dict[str, object] = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        captured.update(opts)
        return {}, SimpleNamespace(retry_count=0)

    case_root = tmp_path / "case"
    case_root.mkdir()
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "0")
    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *args, **kwargs: "ocr")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="security-case-root",
            tenant="acme",
            directory_path=str(case_root),
        )
    )

    assert captured["case_root"] == case_root
