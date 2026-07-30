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
from datetime import datetime, timezone
from typing import Any


from server.common.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    StructuredJSON,
    register_schema_processor,
)
from server.platform.paths import PROJECT_ROOT


_KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"


def _rule_ref_check_enabled() -> bool:
    """Rule-ref hallucination gate switch. **默认开**；空规则集自动跳过
    （见 ``_load_known_rule_ids``：无 gitignored ``knowledge/`` 的 CI/fixture 不会误挂），
    设 ``RULE_REF_CHECK=0`` 可关。"""
    return os.getenv("RULE_REF_CHECK", "1").strip().lower() in {"1", "true", "yes", "on"}


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


def _load_rule_details() -> dict[str, dict[str, str]]:
    """扫 ``knowledge/{domain}/*.rules.json`` 建 ``rule_id → {rule_id, name, source_text}`` 映射。

    供 ``enrich_audit_decision`` 把承重 ``policy_refs`` 的裸 rule_id（如 ``tender_evalmethod_001``）
    解析成可读规则名 + 法定原文，前端直接展示法定依据文本而非内部规则号（#6）。无 ``knowledge/``
    或读不出 → 空 dict（调用方对未知 id 兜底显 id，向后兼容、不崩）。
    """
    details: dict[str, dict[str, str]] = {}
    if not _KNOWLEDGE_DIR.is_dir():
        return details
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
                rid = rule["rule_id"]
                details[rid] = {
                    "rule_id": rid,
                    "name": str(rule.get("description") or rid),
                    "source_text": str(rule.get("source_text") or ""),
                }
    return details


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
        desc = str(
            reason.get("description") or reason.get("message") or reason.get("reason") or ""
        ).strip()
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
        pairs = [(item.get("name"), item.get("score")) for item in value if isinstance(item, dict)]
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
        # #6：承重 policy_refs（裸 rule_id）解析成 {rule_id, name, source_text} 供前端直接展示法定
        # 依据原文（不再显示 tender_evalmethod_001 这类内部号）。enrich 在 schema 校验之后跑（同
        # result/conclusion 派生），故新增字段不过硬校验。未知 id 兜底 {name:id, source_text:""}（不崩、
        # 前端可显 id）。空/无 refs → 不加该字段。
        refs = structured_output.get("policy_refs")
        if isinstance(refs, list) and refs:
            rule_details = _load_rule_details()
            structured_output["policy_refs_detail"] = [
                rule_details.get(r, {"rule_id": r, "name": r, "source_text": ""})
                for r in refs
                if isinstance(r, str)
            ]
        # risk_dimensions 契约为对象数组；模型给成 {name: score} 映射或 0-100 量纲时归一。
        if "risk_dimensions" in structured_output:
            normalized_dims = _coerce_risk_dimensions(structured_output["risk_dimensions"])
            if normalized_dims is not None:
                structured_output["risk_dimensions"] = normalized_dims
    return structured_output


_VALID_RISK_DIM_NAMES = {"invoice", "amount", "approval", "budget", "anomaly"}


def _cleanse_risk_dimensions(output: dict[str, Any]) -> None:
    """Filter ``risk_dimensions`` in-place, keeping only schema-compliant items.

    risk_dimensions 是共享契约中的可选风险元数据。网关模型（qwen 等）给的格式常不规范——
    公共调用链继续清洗/丢弃，由需要固定维度的业务域追加更严格的语义闸。

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


def _validate_risk_dimensions(output: dict[str, Any]) -> None:
    """Require the complete fixed dimension set for the expense-audit alias."""
    _cleanse_risk_dimensions(output)
    dimensions = output.get("risk_dimensions")
    names = (
        [dimension.get("name") for dimension in dimensions]
        if isinstance(dimensions, list)
        else []
    )
    if len(names) != len(_VALID_RISK_DIM_NAMES) or set(names) != _VALID_RISK_DIM_NAMES:
        raise JSONContractError(
            "audit result field `risk_dimensions` must contain exactly invoice, amount, "
            "approval, budget, and anomaly."
        )


def _strip_unknown_policy_refs(output: dict[str, Any]) -> None:
    """剥 policy_refs 里非真实 rule_id 的项（模型偶把废标原因句子/描述当 rule_id 塞进来）。

    防幻觉初衷不变（编造引用不入库），但改「剥」而非「任一未知即整单拒」：保留真实 rule_id；若剥后
    承重结论(approved/rejected) 无任何真实依据 → 由 _validate_audit_result 的承重依据闸照常拒（触发重试，
    正确）。比整单拒省重试——混了真+假引用的结论保住真引用直接过（实测 deepseek 把废标描述当 ref）。
    仅 rule-ref check 开 + 加载到规则时生效（与校验闸同门，向后兼容）。
    """
    if not _rule_ref_check_enabled():
        return
    refs = output.get("policy_refs")
    if not isinstance(refs, list):
        return
    known = _load_known_rule_ids()
    if not known:
        return
    output["policy_refs"] = [ref for ref in refs if ref in known]


def _normalize_evidence_chain(output: dict[str, Any]) -> None:
    """Coerce each evidence_chain item to the schema shape {source, finding, conclusion}.

    剥模型自行追加的未知字段（rule_ref/relevance…）+ 补缺失必填（conclusion 等默认空串），防
    evidence_chain（展示元数据，**非承重**）的 additionalProperties:false / required 让整单评标契约
    失败、反复重试至失败或拖慢。非 list / 非 dict 项安全丢弃。Side-effect: 原地改写 *output*。
    """
    chain = output.get("evidence_chain")
    if not isinstance(chain, list):
        return
    output["evidence_chain"] = [
        {
            "source": str(item.get("source") or ""),
            "finding": str(item.get("finding") or ""),
            "conclusion": str(item.get("conclusion") or ""),
        }
        for item in chain
        if isinstance(item, dict)
    ]


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

    # 承重依据闸：approved/rejected 是承重结论，必须至少引一条规则依据。
    # 空 policy_refs 的"通过/拒绝"是无依据判决——schema 只能要求字段存在(可空)，这里补语义闸。
    if verdict in {"approved", "rejected"}:
        policy_refs = structured_output.get("policy_refs")
        if not isinstance(policy_refs, list) or not policy_refs:
            raise JSONContractError(
                f"audit result with verdict={verdict} must cite at least one policy_ref."
            )
        # 规则引用真伪闸（env-gated）：policy_refs 必须是真实存在的 rule_id，防模型编造规则号。
        # 这是「验证而非判断」——只查引用真伪，verdict 仍由 Claude 判。默认开(见 _rule_ref_check_enabled)。
        if _rule_ref_check_enabled():
            known = _load_known_rule_ids()
            if known:  # 加载到规则才校验；无 knowledge/ → 跳过(向后兼容)
                unknown = [ref for ref in policy_refs if ref not in known]
                if unknown:
                    raise JSONContractError(
                        f"policy_refs 引用了不存在的 rule_id（疑似编造）: {unknown}"
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
        raise JSONContractError(
            "init-rules cannot return status=initialized with empty categories."
        )
    if not isinstance(extracted_rule_count, int) or extracted_rule_count <= 0:
        raise JSONContractError(
            "init-rules cannot return status=initialized with extracted_rule_count <= 0."
        )


# 服务端权威元数据：reviewed_by/timestamp 模型不该(也不可靠地)产出；claim_id 缺失时回落任务 request_id。
# 在硬校验前盖章，避免把"服务端该填的字段"当成模型 bug 反复重试至失败。
_DEFAULT_REVIEWED_BY = "expense-auditor"

# audit-result.schema.json 顶层声明的字段（顶层 additionalProperties:false）。normalize 剥离此集合外
# 的模型多输出字段——实测根因:模型(deepseek)常多带 missing_fields/technical_subtotal 等无关键,顶层
# additionalProperties:false 会因此把【完整合理的结论整单拒】→反复重试至失败→降级 manual_review/空结论。
# ⚠ 改 audit-result.schema 顶层 properties 时必须同步此集合（test_output_contracts 有漂移守卫）。
_AUDIT_SCHEMA_TOP_FIELDS = frozenset(
    {
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
        "manual_review_reason",
        "risk_dimensions",
    }
)


def _stamp_server_metadata(output: dict[str, Any], request_id: str | None) -> None:
    """Stamp server-authoritative metadata + default the model-owned envelope (in-place)."""
    output.setdefault("claim_id", request_id or "UNKNOWN")
    output.setdefault("reviewed_by", _DEFAULT_REVIEWED_BY)
    output.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    # extracted_data 是事实底稿(模型职责)；偶发漏给时回落空对象,保结论可落库(降级而非掩盖)。
    output.setdefault("extracted_data", {})
    # 信封类必填字段兜底（多模型可靠性）：模型偶尔漏给这些 schema required 字段——实测 deepseek
    # 全量评标漏 `reasons` 致整单契约失败重试至失败。空默认安全：①不掩盖承重决策（verdict/explanation
    # 仍必填非空；approved/rejected 的 policy_refs 即便默认 [] 也会被承重依据闸要求非空 → 正确触发重试，
    # 不会放过无依据判决）；②risk_score 缺省给中性 50（不触发高风险复审，不伪造高危）。
    output.setdefault("reasons", [])
    output.setdefault("policy_refs", [])
    output.setdefault("evidence_chain", [])
    output.setdefault("risk_score", 50)


def normalize_audit_result(
    structured_output: StructuredJSON, request_id: str | None = None
) -> StructuredJSON:
    """前置规整：盖 server 元数据 + 拍平 envelope 格式，使硬 schema 校验只挡真问题。

    1. 元数据：claim_id(缺→request_id)/reviewed_by/timestamp/extracted_data 默认值。
    2. reasons/policy_refs：对象→字符串（防前端崩 + 满足 string[] 契约）。
    3. risk_dimensions：对象映射/0-100 量纲 → [{name∈枚举,score 0-10}]；非法项清除，
       后续契约要求固定五维完整。

    与 ``enrich_audit_decision`` 的分工：normalize 跑在硬 schema 校验**前**（只产 schema 内字段）；
    enrich 跑在校验**后**（派生 schema 外的 result/conclusion）。
    """
    if not isinstance(structured_output, dict):
        return structured_output
    _stamp_server_metadata(structured_output, request_id)
    # manual_review_reason 仅对 verdict=manual_review 有意义；approved/rejected 时模型偶尔仍带出
    # 旧枚举（如 data_conflict），会残留进结论误导前端/消费者 → 非 manual_review 一律剥离。
    if structured_output.get("verdict") != "manual_review":
        structured_output.pop("manual_review_reason", None)
    for field in ("reasons", "policy_refs"):
        value = structured_output.get(field)
        if isinstance(value, str):
            # 模型偶把 string[] 写成单个（常含多行编号）字符串——deepseek 习惯把 reasons 写成
            # "1. …\n2. …"，契约要求数组 → 整单校验失败重试至失败。按行拆成 string[]（满足契约、
            # 保留全部内容、可读），单行则单元素。
            value = [ln.strip() for ln in value.splitlines() if ln.strip()] or [value.strip()]
            structured_output[field] = value
        if isinstance(value, list):
            structured_output[field] = [_coerce_reason_to_str(item) for item in value]
    if "risk_dimensions" in structured_output:
        coerced = _coerce_risk_dimensions(structured_output["risk_dimensions"])
        if coerced is None:
            structured_output.pop("risk_dimensions", None)
        else:
            structured_output["risk_dimensions"] = coerced
            _cleanse_risk_dimensions(structured_output)  # 丢非枚举/越界项
            if not structured_output.get("risk_dimensions"):
                structured_output.pop("risk_dimensions", None)
    # evidence_chain 是展示元数据(非承重)：模型常给每项追加 rule_ref/relevance 等未知字段、或漏
    # conclusion → items 的 additionalProperties:false + required 整单拒→反复重试至失败/慢（实测
    # qwen/deepseek 评标 `evidence_chain/N` 反复挂 rule_ref/relevance）。剥到契约允许的
    # {source,finding,conclusion} + 补缺省，使其稳过校验，不因展示字段拖垮整单评标。
    _normalize_evidence_chain(structured_output)
    # policy_refs 里编造的 rule_id → 剥（留真实引用，承重无依据仍由承重依据闸拒）。
    _strip_unknown_policy_refs(structured_output)
    # result/conclusion 是服务端从 verdict 派生的【决策】字段（enrich 后才有）；
    # 模型【自报】它们＝篡改决策，必须拒、绝不静默剥离。
    for forbidden in ("result", "conclusion"):
        if forbidden in structured_output:
            raise JSONContractError(
                f"模型不得自报服务端派生的决策字段 `{forbidden}`（由 verdict 派生）"
            )
    # 其余 schema 未声明的顶层字段（模型多带 missing_fields/technical_subtotal 等【无害噪音】）→ 剥离，
    # 不因此整单拒→反复重试至失败（评标"结论根本没产出→降级 manual_review/空"的实测根因）。
    for key in list(structured_output.keys()):
        if key not in _AUDIT_SCHEMA_TOP_FIELDS:
            structured_output.pop(key, None)
    return structured_output


register_schema_processor(
    DEFAULT_OUTPUT_SCHEMA_NAME,
    normalize=normalize_audit_result,
    validate=_validate_audit_result,
    enrich=enrich_audit_decision,
    # F5：evidence-resolution 回查闸是 tender 专属（挂在 server/tender/evidence.py 的
    # TENDER_OUTPUT_SCHEMA_NAME 处理器上），DEFAULT（expense/audit 共用）不再挂 resolve hook——
    # expense/audit 调用链从不透传 evidence_source（apply_schema_semantics 的 resolve 分支本就
    # 双重门禁：evidence_source 非空 且 processor.resolve is not None），删除零行为影响。
)
register_schema_processor(
    INIT_RULES_REPORT_SCHEMA_NAME,
    validate=_validate_init_rules_report,
)
