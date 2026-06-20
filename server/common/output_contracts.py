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
import os
from typing import Any

import jsonschema

from server.common.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    StructuredJSON,
    load_output_schema,
    register_schema_processor,
)
from server.platform.paths import PROJECT_ROOT

PLAN_SCHEMA_NAME = "common/plan.schema.json"

_KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"


def _rule_ref_check_enabled() -> bool:
    """G1b-full 幻觉闸开关。默认关——避免无 knowledge/ 的 CI/fixture 误挂；
    部署侧 knowledge/ 规则稳定后设 ``RULE_REF_CHECK=1`` 即启用。"""
    return os.getenv("RULE_REF_CHECK", "").strip().lower() in {"1", "true", "yes", "on"}


def _load_known_rule_ids() -> set[str]:
    """扫 ``knowledge/{domain}/*.rules.json`` 收集所有 rule_id。

    用于幻觉闸：模型自报的 ``policy_refs`` 必须是真实存在的规则号（防编造 "TRAVEL-RULE-999"）。
    无 knowledge/ 或读不出 → 返回空集（调用方据此跳过校验，保持向后兼容）。
    """
    known: set[str] = set()
    if not _KNOWLEDGE_DIR.is_dir():
        return known
    for path in _KNOWLEDGE_DIR.glob("*/*.rules.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rules = data.get("rules") if isinstance(data, dict) else None
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if isinstance(rule, dict) and isinstance(rule.get("rule_id"), str):
                known.add(rule["rule_id"])
    return known

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
        # G1b-full（env-gated）：policy_refs 必须是真实存在的 rule_id，防模型编造规则号。
        # 这是「验证而非判断」——只查引用真伪，verdict 仍由 Claude 判。默认关(见 _rule_ref_check_enabled)。
        if _rule_ref_check_enabled():
            known = _load_known_rule_ids()
            if known:  # 加载到规则才校验；无 knowledge/ → 跳过(向后兼容)
                unknown = [ref for ref in policy_refs if ref not in known]
                if unknown:
                    raise JSONContractError(
                        f"policy_refs 引用了不存在的 rule_id（疑似编造）: {unknown}"
                    )

    _verify_scoring_consistency(structured_output)
    _verify_plan_shape(structured_output)
    _cleanse_risk_dimensions(structured_output)


def _verify_plan_shape(structured_output: dict[str, Any]) -> None:
    """G2：若命令把 S1 计划升级为结构化 ``extracted_data.plan``，校验其满足 plan 契约。

    可选——未产出 plan（散文计划/内联单 agent 流）则跳过；产出了就必须类型正确
    （每节点 step/intent + 可选 reads/tools/produces/tag）。
    """
    extracted = structured_output.get("extracted_data")
    if not isinstance(extracted, dict):
        return
    plan = extracted.get("plan")
    if plan is None:
        return
    try:
        jsonschema.validate(plan, load_output_schema(PLAN_SCHEMA_NAME))
    except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        raise JSONContractError(
            f"extracted_data.plan 不满足 plan 契约: {exc.message}"
        ) from exc


def _verify_scoring_consistency(structured_output: dict[str, Any]) -> None:
    """G1c（round4 验证非判断）：评分项内部算术一致性——每项 0 ≤ score ≤ max。

    不替模型判分，只拒"给了超出量纲的分"这类自相矛盾输出（如 max=10 却给 15）。
    仅在 ``extracted_data.scoring`` 存在时触发；``score=null``（不可判定/manual_review 项）跳过。
    """
    extracted = structured_output.get("extracted_data")
    if not isinstance(extracted, dict):
        return
    scoring = extracted.get("scoring")
    if not isinstance(scoring, list):
        return
    for item in scoring:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        max_score = item.get("max")
        if not _is_real_number(score) or not _is_real_number(max_score):
            continue  # null 分（未判定项）或非数 → 不在本闸范围
        if score < 0 or score > max_score:
            raise JSONContractError(
                f"评分项 score={score} 超出 [0, max={max_score}] 范围（item={item.get('item')!r}）"
            )


def _is_real_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
