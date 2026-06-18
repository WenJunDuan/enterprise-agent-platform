"""JSON contract helpers: schema loading, normalisation, and semantic validation.

Shared platform scaffolding for *model-output conformance* — validating and
normalising what Claude returns against the declared output schema. This is not
business logic (the audit/tender/… decisions are made on the Claude side); it
only enforces the output contract, so it lives in ``common`` and is depended on
by feature domains, never the other way around. Pure functions, no SDK import.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.platform.paths import PROJECT_ROOT

CONTRACTS_DIR = PROJECT_ROOT / ".claude" / "contracts"
DEFAULT_OUTPUT_SCHEMA_NAME = "common/audit-result.schema.json"
INIT_RULES_REPORT_SCHEMA_NAME = "system/init-rules-report.schema.json"
StructuredJSON = dict[str, Any] | list[Any]

# `verdict` is the single source of truth; `result` (bool) and `conclusion` (label)
# are derived from it server-side so the model never has to keep three fields in sync.
AUDIT_DECISION_DERIVATION: dict[str, tuple[bool, str]] = {
    "approved": (True, "合规"),
    "rejected": (False, "不合规"),
    "manual_review": (False, "待人工复核"),
}


class JSONContractError(ValueError):
    """Raised when a Claude response does not satisfy the JSON contract."""


def _coerce_reason_to_str(reason: Any) -> str:
    """把单条 reason 拍平成字符串。

    契约里 reasons / policy_refs 是字符串数组，但模型(尤其网关模型)可能给成对象
    （如 {code, description, severity}）→ 前端按字符串渲染对象会触发 React #31 崩溃。
    """
    if isinstance(reason, str):
        return reason
    if isinstance(reason, dict):
        desc = str(reason.get("description") or reason.get("message") or reason.get("reason") or "").strip()
        severity = str(reason.get("severity") or "").strip()
        text = f"[{severity}] {desc}" if severity and desc else desc
        return text or json.dumps(reason, ensure_ascii=False)
    return str(reason)


def _scale_risk_dimension_score(raw: Any) -> int:
    """把维度分归一到契约的 0-10 区间。

    契约要求 score ∈ [0, 10]，但模型常按 0-100 量纲给（与 risk_score 同尺度）。
    >10 视为百分制并除以 10；最终 clamp 到 0-10。
    """
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0
    if score > 10:  # 模型用了 0-100 量纲，映射回契约的 0-10
        score /= 10.0
    return max(0, min(10, round(score)))


def _coerce_risk_dimensions(value: Any) -> list[dict[str, Any]] | None:
    """把 risk_dimensions 归一成契约形态：[{name, score(0-10)}]。

    契约是对象数组，但模型可能给成对象映射 {name: score}（如 {anomaly: 85}）。
    前端按数组渲染（.map / .length），拿到对象会显示异常或漏渲染，这里统一拍平。
    """
    if isinstance(value, dict):
        pairs: list[tuple[Any, Any]] = list(value.items())
    elif isinstance(value, list):
        pairs = [
            (item.get("name"), item.get("score")) for item in value if isinstance(item, dict)
        ]
    else:
        return None
    normalized = [
        {"name": str(name), "score": _scale_risk_dimension_score(score)}
        for name, score in pairs
        if name is not None and str(name).strip()
    ]
    return normalized or None


def enrich_audit_decision(structured_output: StructuredJSON) -> StructuredJSON:
    """Inject `result`/`conclusion` derived from `verdict`; normalize string-list fields."""
    if isinstance(structured_output, dict):
        derived = AUDIT_DECISION_DERIVATION.get(str(structured_output.get("verdict")))
        if derived is not None:
            structured_output["result"], structured_output["conclusion"] = derived
        # reasons / policy_refs 契约为字符串数组；模型给成对象数组时拍平，避免前端渲染崩溃。
        for field in ("reasons", "policy_refs"):
            value = structured_output.get(field)
            if isinstance(value, list):
                structured_output[field] = [_coerce_reason_to_str(item) for item in value]
        # risk_dimensions 契约为对象数组；模型给成 {name: score} 映射或 0-100 量纲时归一。
        if "risk_dimensions" in structured_output:
            normalized_dims = _coerce_risk_dimensions(structured_output["risk_dimensions"])
            if normalized_dims is not None:
                structured_output["risk_dimensions"] = normalized_dims
    return structured_output


def resolve_output_schema_path(schema_name: str) -> Path:
    """Resolve a schema path under `.claude/contracts` without allowing path escape."""
    schema_path = (CONTRACTS_DIR / schema_name).resolve()
    contracts_root = CONTRACTS_DIR.resolve()
    if contracts_root not in schema_path.parents:
        raise JSONContractError(f"Schema path escapes contracts root: {schema_name}")
    if not schema_path.is_file():
        raise JSONContractError(f"Structured output schema not found: {schema_name}")
    return schema_path


def load_output_schema(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Load a JSON schema from `.claude/contracts`."""
    schema_path = resolve_output_schema_path(schema_name)
    try:
        loaded = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - exact error text is incidental
        raise JSONContractError(f"Structured output schema is invalid JSON: {schema_name}") from exc

    if not isinstance(loaded, dict):
        raise JSONContractError(f"Structured output schema must be a JSON object: {schema_name}")
    return loaded


def build_output_format(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Build the SDK `output_format` payload for structured outputs."""
    return {"type": "json_schema", "schema": load_output_schema(schema_name)}


def validate_structured_output_semantics(
    schema_name: str,
    structured_output: StructuredJSON,
) -> None:
    """Apply semantic validation rules that JSON Schema alone cannot express."""
    if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
        if not isinstance(structured_output, dict):
            raise JSONContractError("audit result structured output must be a JSON object.")

        verdict = structured_output.get("verdict")
        if verdict not in AUDIT_DECISION_DERIVATION:
            raise JSONContractError("audit result returned an unknown verdict.")

        if not str(structured_output.get("explanation") or "").strip():
            raise JSONContractError("audit result field `explanation` must be non-empty.")

        if verdict == "manual_review":
            reason = structured_output.get("manual_review_reason")
            valid_reasons = {
                "missing_approval",
                "rule_gap",
                "data_conflict",
                "insufficient_evidence",
                "budget_exceeded",
                "invoice_invalid",
                "pre_approval_mismatch",
            }
            if reason not in valid_reasons:
                raise JSONContractError(
                    "audit result with verdict=manual_review must include a valid manual_review_reason."
                )

        # risk_dimensions 是可选的风险元数据。网关模型（qwen 等）给的格式常不规范——
        # 不规范就清洗/丢弃，绝不因为一个可选字段让整单审核失败（核心是 verdict/explanation）。
        valid_dim_names = {"invoice", "amount", "approval", "budget", "anomaly"}
        dimensions = structured_output.get("risk_dimensions")
        if isinstance(dimensions, list):
            structured_output["risk_dimensions"] = [
                dim
                for dim in dimensions
                if isinstance(dim, dict)
                and dim.get("name") in valid_dim_names
                and isinstance(dim.get("score"), int)
                and not isinstance(dim.get("score"), bool)
                and 0 <= dim["score"] <= 10
            ]
        elif dimensions is not None:
            structured_output.pop("risk_dimensions", None)

        return

    if schema_name != INIT_RULES_REPORT_SCHEMA_NAME:
        return

    if not isinstance(structured_output, dict):
        raise JSONContractError("init-rules structured output must be a JSON object.")

    source_path = str(structured_output.get("source_path") or "").strip()
    if not source_path:
        raise JSONContractError("init-rules result must include a non-empty source_path.")

    status = structured_output.get("status")
    if status != "initialized":
        return

    written_files = structured_output.get("written_files")
    categories = structured_output.get("categories")
    extracted_rule_count = structured_output.get("extracted_rule_count")

    if not isinstance(written_files, list) or not written_files:
        raise JSONContractError(
            "init-rules cannot return status=initialized with empty written_files."
        )
    if not isinstance(categories, list) or not categories:
        raise JSONContractError("init-rules cannot return status=initialized with empty categories.")
    if not isinstance(extracted_rule_count, int) or extracted_rule_count <= 0:
        raise JSONContractError(
            "init-rules cannot return status=initialized with extracted_rule_count <= 0."
        )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型文本里抽取**最终**的 JSON 对象。

    针对 reasoning 模型：思考/草稿（常含一段草稿 JSON）在 </think> 之前，真正答案在
    之后；所以先截到最后一个 </think> 之后，去掉 ```json 围栏，扫出所有平衡的 {...}，
    返回**最后一个**能解析成 dict 的（最终答案通常在最后）。这样不会误抓推理里的草稿。
    用于"文本模式"：网关模型（如 qwen）直接输出 JSON 文本，由服务端解析。
    """
    if not text:
        return None
    # reasoning 模型把草稿放 </think> 之前，真正答案在最后一个 </think> 之后
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    cleaned = text.replace("```json", "").replace("```", "")
    # 扫出所有平衡的顶层 {...}
    objects: list[str] = []
    i = 0
    n = len(cleaned)
    while i < n:
        if cleaned[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        closed_at = -1
        for j in range(i, n):
            ch = cleaned[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    objects.append(cleaned[i : j + 1])
                    closed_at = j
                    break
        i = closed_at + 1 if closed_at != -1 else n
    # 最终答案在最后：从后往前返回第一个能解析成 dict 的
    for candidate in reversed(objects):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None
