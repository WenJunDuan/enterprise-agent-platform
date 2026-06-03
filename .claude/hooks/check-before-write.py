#!/usr/bin/env python3
"""Block incomplete structured results before they are written."""

from __future__ import annotations

import json
import sys


REQUIRED_FIELDS = [
    "claim_id",
    "verdict",
    "explanation",
    "reasons",
    "policy_refs",
    "risk_score",
    "extracted_data",
    "evidence_chain",
    "reviewed_by",
    "timestamp",
]


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _resolve_audit_result(payload: dict[str, object]) -> dict[str, object]:
    response = payload.get("response")
    envelope_keys = {"request_id", "tenant", "conversation_id", "schema_name"}
    if isinstance(response, dict) and any(key in payload for key in envelope_keys):
        return response
    return payload


def _collect_missing_fields(result: dict[str, object]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in result:
            missing.append(field)
            continue

        value = result.get(field)
        if field in {"claim_id", "verdict", "reviewed_by", "timestamp"}:
            if not _is_non_empty_string(value):
                missing.append(field)
            continue

        if field == "explanation":
            if not _is_non_empty_string(value):
                missing.append(field)
            continue

        if field == "risk_score":
            if isinstance(value, bool) or not isinstance(value, int):
                missing.append(field)
            continue

        if field == "extracted_data":
            if not isinstance(value, dict):
                missing.append(field)
            continue

        if field in {"reasons", "policy_refs", "evidence_chain"}:
            if not isinstance(value, list) or not value:
                missing.append(field)
            continue

        if not value:
            missing.append(field)

    return missing


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
    if not isinstance(result, dict):
        print(json.dumps({"error": "Structured result must be a JSON object."}))
        return 2

    audit_result = _resolve_audit_result(result)
    missing = _collect_missing_fields(audit_result)

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

    valid_verdicts = {"approved", "rejected", "manual_review"}
    verdict = audit_result.get("verdict")
    if verdict not in valid_verdicts:
        print(json.dumps({"error": "Structured result returned an unknown verdict."}))
        return 2

    if verdict == "approved" and not audit_result.get("policy_refs"):
        print(json.dumps({"error": "Approved results must include policy references from common-rule-query."}))
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
