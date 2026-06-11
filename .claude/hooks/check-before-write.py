#!/usr/bin/env python3
"""Block incomplete structured results before they are written."""

from __future__ import annotations

import json
import os
import sys


def _validation_enabled() -> bool:
    """写入结果守卫是 opt-in：默认关闭。

    内联审核当前由 Python 端 `validate_structured_output_semantics` 兜底；本 hook
    只在「模型经 Write 工具写结果」的流程里才有意义。待写入模型（内网 qwen3.6-27b，
    具备多模态）的产出能力验证通过后，设 `AUDIT_WRITE_VALIDATION_ENABLED=1` 启用本守卫。
    """
    return os.getenv("AUDIT_WRITE_VALIDATION_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


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

        if field in {"reasons", "evidence_chain"}:
            if not isinstance(value, list) or not value:
                missing.append(field)
            continue

        # policy_refs 允许为空数组（造假判定基于数据真实性而非命中规则，prompt/契约均允许）；
        # 仅校验类型。“approved 必须带 policy_refs” 由下方 verdict 专项校验负责。
        if field == "policy_refs":
            if not isinstance(value, list):
                missing.append(field)
            continue

        if not value:
            missing.append(field)

    return missing


def main() -> int:
    if not _validation_enabled():
        return 0
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

    if verdict == "manual_review":
        valid_reasons = {
            "missing_approval",
            "rule_gap",
            "data_conflict",
            "insufficient_evidence",
            "budget_exceeded",
            "invoice_invalid",
            "pre_approval_mismatch",
        }
        if audit_result.get("manual_review_reason") not in valid_reasons:
            print(json.dumps({"error": "manual_review results must include a valid manual_review_reason."}))
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
