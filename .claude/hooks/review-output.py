#!/usr/bin/env python3
"""Run a lightweight second-pass quality review after result writes."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - runtime dependency check
    Anthropic = None

from server.platform.config import configure_claude_runtime_env, resolve_second_review_model  # noqa: E402

configure_claude_runtime_env()


def main() -> int:
    hook_input = json.load(sys.stdin)
    tool_input = hook_input.get("tool_input", {})
    file_path = str(tool_input.get("file_path", ""))

    if "logs/results/" not in file_path:
        return 0

    if Anthropic is None or not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return 0

    content = str(tool_input.get("content", ""))
    client = Anthropic()
    response = client.messages.create(
        model=resolve_second_review_model(),
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": (
                    "Review the structured result below.\n"
                    "Check for sensitive data leakage, missing policy support, and contradictions.\n"
                    "Reply with PASS or BLOCK:reason only.\n\n"
                    f"{content}"
                ),
            }
        ],
    )

    result = response.content[0].text.strip()
    if result.startswith("BLOCK"):
        print(json.dumps({"error": f"Secondary review failed: {result}"}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
