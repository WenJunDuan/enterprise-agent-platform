#!/usr/bin/env python3
"""Run a lightweight second-pass quality review after result writes."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.platform.config import configure_claude_runtime_env, resolve_second_review_model  # noqa: E402

configure_claude_runtime_env()


def _is_result_write(file_path: str) -> bool:
    return "logs/results/" in file_path


def _has_runtime_credentials() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def _build_review_prompt(content: str) -> str:
    return (
        "Review the structured result below.\n"
        "Check for sensitive data leakage, missing policy support, and contradictions.\n"
        "Reply with PASS or BLOCK:reason only.\n\n"
        f"{content}"
    )


def _build_review_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        allowed_tools=[],
        hooks={},
        max_turns=1,
        cwd=str(PROJECT_ROOT),
        setting_sources=["project"],
        permission_mode="bypassPermissions",
        model=resolve_second_review_model(),
    )


def _resolve_result_payload(content: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    response = parsed.get("response")
    if isinstance(response, dict):
        return response
    return parsed


def _should_run_second_review(payload: dict[str, object] | None) -> bool:
    resolved = payload
    if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
        resolved = payload.get("response")
    if not isinstance(resolved, dict):
        return False
    verdict = str(resolved.get("verdict") or "")
    risk_score = resolved.get("risk_score")
    manual_review_reason = str(resolved.get("manual_review_reason") or "")
    min_risk_score = int(os.getenv("SECOND_REVIEW_MIN_RISK_SCORE", "70"))
    high_risk_manual_review_reasons = {
        "data_conflict",
        "pre_approval_mismatch",
        "missing_approval",
        "invoice_invalid",
    }

    if verdict == "rejected":
        return True
    if isinstance(risk_score, int) and not isinstance(risk_score, bool) and risk_score >= min_risk_score:
        return True
    if verdict == "manual_review" and manual_review_reason in high_risk_manual_review_reasons:
        return True
    return False


async def _run_second_review(content: str) -> str:
    prompt = _build_review_prompt(content)
    options = _build_review_options()
    chunks: list[str] = []
    final_result = ""

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in getattr(message, "content", []):
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
        elif isinstance(message, ResultMessage):
            if getattr(message, "is_error", False):
                raise RuntimeError(message.result or "Claude SDK review hook returned an error result.")
            final_result = (message.result or "").strip()

    return final_result or "\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def main() -> int:
    hook_input = json.load(sys.stdin)
    tool_input = hook_input.get("tool_input", {})
    file_path = str(tool_input.get("file_path", ""))

    if not _is_result_write(file_path):
        return 0

    if not _has_runtime_credentials():
        return 0

    content = str(tool_input.get("content", ""))
    if not _should_run_second_review(_resolve_result_payload(content)):
        return 0
    result = asyncio.run(_run_second_review(content)).strip()
    if result.startswith("BLOCK"):
        print(json.dumps({"error": f"Secondary review failed: {result}"}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
