#!/usr/bin/env python3
"""Block incomplete structured results before they are written."""

from __future__ import annotations

import json
import sys


def main() -> int:
    hook_input = json.load(sys.stdin)
    tool_input = hook_input.get("tool_input", {})
    file_path = str(tool_input.get("file_path", ""))

    if "logs/results/" not in file_path:
        return 0

    content = tool_input.get("content", "")
    try:
        result = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        print(json.dumps({"error": "Structured result must be valid JSON."}))
        return 2

    required_fields = ["claim_id", "verdict", "reasons", "policy_refs", "evidence_chain"]
    missing = [field for field in required_fields if not result.get(field)]

    if missing:
        print(
            json.dumps(
                {
                    "error": (
                        "Structured result is missing required fields: "
                        f"{', '.join(missing)}. Use common-evidence-chain and common-result-format."
                    )
                }
            )
        )
        return 2

    if result.get("verdict") == "approved" and not result.get("policy_refs"):
        print(json.dumps({"error": "Approved results must include policy references from common-rule-query."}))
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
