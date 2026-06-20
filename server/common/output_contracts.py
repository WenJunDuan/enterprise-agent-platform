"""Built-in platform output contracts (registered into the contract registry).

平台自带的**共享**模型输出契约，装进 ``server.common.contract`` 的注册表：

- ``common/audit-result.schema.json``：审核结论输出契约（verdict→result/conclusion 派生 +
  reasons/risk_dimensions 归一）。由**所有产 audit-result 的业务域**（audit/tender/expense…）
  共用——它是平台共享输出契约，不是某个业务域私有，故属 common，不下放到 audit/。
- ``system/init-rules-report.schema.json``：init-rules CLI 报告契约。

机制（registry / schema 加载 / JSON 抽取）在 ``server.common.contract``；本模块只装"内置策略"
并注册（policy）。新业务域要新 schema，从自己模块调 ``register_schema_processor`` 即可，无需改此处。
``contract.py`` 在末尾 import 本模块以确保内置契约随注册表一起就绪。
"""

from __future__ import annotations

import json
from typing import Any

from server.common.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    StructuredJSON,
    register_schema_processor,
)

# `verdict` is the single source of truth; `result` (bool) and `conclusion` (label)
# are derived from it server-side so the model never has to keep three fields in sync.
AUDIT_DECISION_DERIVATION: dict[str, tuple[bool, str]] = {
    "approved": (True, "合规"),
    "rejected": (False, "不合规"),
    "manual_review": (False, "待人工复核"),
}


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


_VALID_RISK_DIM_NAMES = {"invoice", "amount", "approval", "budget", "anomaly"}


def _cleanse_risk_dimensions(output: dict[str, Any]) -> None:
    """Filter ``risk_dimensions`` in-place, keeping only schema-compliant items.

    risk_dimensions 是可选的风险元数据。网关模型（qwen 等）给的格式常不规范——
    不规范就清洗/丢弃，绝不因为一个可选字段让整单审核失败（核心是 verdict/explanation）。

    Side-effect: mutates *output* directly (removes or filters ``risk_dimensions``).
    """
    dimensions = output.get("risk_dimensions")
    if isinstance(dimensions, list):
        output["risk_dimensions"] = [
            dim
            for dim in dimensions
            if isinstance(dim, dict)
            and dim.get("name") in _VALID_RISK_DIM_NAMES
            and isinstance(dim.get("score"), int)
            and not isinstance(dim.get("score"), bool)
            and 0 <= dim["score"] <= 10
        ]
    elif dimensions is not None:
        output.pop("risk_dimensions", None)


def _validate_audit_result(structured_output: StructuredJSON) -> None:
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

    # G1b（round4 F1 幻觉闸）：approved/rejected 是承重结论，必须至少引一条规则依据。
    # 空 policy_refs 的"通过/拒绝"是无依据判决——schema 只能要求字段存在(可空)，这里补语义闸。
    if verdict in {"approved", "rejected"}:
        policy_refs = structured_output.get("policy_refs")
        if not isinstance(policy_refs, list) or not policy_refs:
            raise JSONContractError(
                f"audit result with verdict={verdict} must cite at least one policy_ref."
            )

    _cleanse_risk_dimensions(structured_output)


def _validate_init_rules_report(structured_output: StructuredJSON) -> None:
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


register_schema_processor(
    DEFAULT_OUTPUT_SCHEMA_NAME,
    validate=_validate_audit_result,
    enrich=enrich_audit_decision,
)
register_schema_processor(
    INIT_RULES_REPORT_SCHEMA_NAME,
    validate=_validate_init_rules_report,
)
