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
import re
from datetime import datetime, timezone
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
    """G1b-full 幻觉闸开关。**默认开**（hardening sprint H1）——空规则集自动跳过
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

_USER_SUMMARY_MARKER = "得分小结："
_TECH_TERM_REPLACEMENTS = (
    ("manual_review_reason", "复核原因"),
    ("manual_review", "需人工复核"),
    ("cross_bid变量", "需要全部投标报价一起计算"),
    ("cross_bid", "需要全部投标报价一起计算"),
    ("bid_component", "本次报价数据"),
    ("tender_constant", "招标文件固定数据"),
    ("external_data", "外部资料"),
    ("live_event", "现场记录"),
    ("formula_spec", "公式明细"),
    ("score_mode", "评分方式"),
    ("extracted_data", "明细"),
    ("policy_refs", "依据"),
    ("evidence_chain", "证据"),
    ("risk_score", "风险分"),
    ("verdict", "结论"),
)


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


_UNCONFIRMED_TOKENS = {"false", "no", "0", "疑似", "待确认", "待核验", "unconfirmed", "manual"}


def _hit_unconfirmed(hit: dict[str, Any]) -> bool:
    """该废标命中是否被模型**明确标为未确认**（疑似 / 读不清 / 待人工核验）→ 不应触发 rejected。

    R2b（治 F01/F4：deepseek 把读不清的信用截图疑似信号写进 disqualification_hits、被门禁强制
    rejected，与其自身"须人工核验、常规理解应属自证清白"分析自相矛盾→误废标合规投标人）：
    `confirmed:false`/`null`、或 `confirmed` 为疑似类字符串 → 未确认。**未带 `confirmed` 字段 →
    向后兼容视为已确认（旧行为不变）**——只把"模型自己都说没确认"的疑似命中挡在 rejected 之外。
    """
    if "confirmed" not in hit:
        return False  # 向后兼容：未标 confirmed 视为已确认（不改旧行为）
    value = hit.get("confirmed")
    if isinstance(value, bool):
        return not value
    if value is None:
        return True
    return str(value).strip().lower() in _UNCONFIRMED_TOKENS


def _meaningful_disqualification_hits(extracted: Any) -> bool:
    """``disqualification_hits`` 是否为【非空 list 且含至少一个有内容、**且未被标为未确认**的 dict】。

    extracted_data 内部无 schema 形校验（codex R2 P1）：模型可能写 ``"无"``（中文"没有"，truthy
    字符串！）/ ``{}`` / ``[{}]`` / ``[]`` 等假值——朴素 ``bool(...)`` 会把 ``"无"`` 当命中→误判
    rejected。故收窄为"非空 list + 至少一项是有内容的 dict"，把这些假值挡在外面。
    R2b：再排除模型**明确标为未确认**（疑似/读不清）的命中——它们不该强制 rejected（见 _hit_unconfirmed）。
    """
    hits = extracted.get("disqualification_hits") if isinstance(extracted, dict) else None
    return isinstance(hits, list) and any(
        isinstance(hit, dict) and not _hit_unconfirmed(hit) and any(value for value in hit.values())
        for hit in hits
    )


def _has_hard_disqualification(extracted: Any) -> bool:
    """True when extracted_data carries a hard 废标/资格否决 (verdict→rejected gate trigger).

    命令 S4：有意义的 ``disqualification_hits``，或任一 ``eligibility_checks.status == 'fail'`` →
    整单废标/资格否决（独立 gate）。仅 tender 评标会带这些字段；expense 审核 extracted_data 无此
    结构，恒 False，故对 expense 无影响。status 比较做大小写/空白容错（codex R2 P2）。
    """
    if not isinstance(extracted, dict):
        return False
    if _meaningful_disqualification_hits(extracted):
        return True
    if _has_failed_eligibility(extracted):
        return True
    return False


def _has_failed_eligibility(extracted: Any) -> bool:
    """True when Claude has explicitly marked a qualification check as failed."""
    if not isinstance(extracted, dict):
        return False
    checks = extracted.get("eligibility_checks")
    if isinstance(checks, list):
        return any(
            isinstance(ch, dict) and str(ch.get("status") or "").strip().lower() == "fail"
            for ch in checks
        )
    return False


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
        _finalize_user_explanation(structured_output)
    return structured_output


def _format_score(value: float) -> str:
    rounded = round(value + 0.0, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}"


def _strip_existing_score_summary(text: str) -> str:
    idx = text.find(_USER_SUMMARY_MARKER)
    if idx == -1:
        base = text
    else:
        base = text[:idx]
    # Models often add a final arithmetic recap and may mis-add decimals. Drop that
    # recap and append the server-calculated one below.
    base = re.sub(r"综上[，,].*?(?:合计|总分).*?(?:。|$)", "", base, flags=re.DOTALL)
    return base.rstrip(" \n；。")


def _sanitize_explanation_terms(text: str) -> str:
    cleaned = text
    for raw, replacement in _TECH_TERM_REPLACEMENTS:
        cleaned = cleaned.replace(raw, replacement)
    cleaned = cleaned.replace("公式含需要全部投标报价一起计算", "需要全部投标报价一起计算")
    # Clean common snake_case leftovers that may appear when a model leaks internal field names.
    cleaned = re.sub(r"\b[a-z]+(?:_[a-z0-9]+)+\b", "相关字段", cleaned)
    return cleaned.strip()


def _score_summary(extracted: Any) -> str | None:
    if not isinstance(extracted, dict):
        return None
    scoring = extracted.get("scoring")
    if not isinstance(scoring, list) or not scoring:
        return None

    total_items = 0
    scored_items = 0
    pending_items = 0
    score_sum = 0.0
    scored_max = 0.0
    pending_max = 0.0
    total_max = 0.0
    for item in scoring:
        if not isinstance(item, dict):
            continue
        max_score = item.get("max")
        if not _is_real_number(max_score):
            continue
        total_items += 1
        total_max += float(max_score)
        score = item.get("score")
        if _is_real_number(score):
            scored_items += 1
            score_sum += float(score)
            scored_max += float(max_score)
        else:
            pending_items += 1
            pending_max += float(max_score)

    if total_items == 0:
        return None
    summary = (
        f"{_USER_SUMMARY_MARKER}评分表共 {total_items} 项，满分 {_format_score(total_max)} 分；"
        f"已有分数 {scored_items} 项，合计 {_format_score(score_sum)} 分"
    )
    if pending_items:
        summary += (
            f"；还有 {pending_items} 项、共 {_format_score(pending_max)} 分需要补充信息后确认"
        )
    summary += "。"
    return summary


def _finalize_user_explanation(output: dict[str, Any]) -> None:
    explanation = output.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        return
    cleaned = _sanitize_explanation_terms(_strip_existing_score_summary(explanation))
    extracted = output.get("extracted_data")
    if output.get("verdict") == "rejected" and _has_failed_eligibility(extracted):
        prefix = "资格审查不通过，按废标处理。"
        if "资格审查不通过" not in cleaned or "废标" not in cleaned:
            cleaned = f"{prefix}{cleaned}" if cleaned else prefix
    summary = None
    if not (output.get("verdict") == "rejected" and _has_hard_disqualification(extracted)):
        summary = _score_summary(extracted)
    output["explanation"] = f"{cleaned}\n\n{summary}" if summary else cleaned


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


def _strip_unknown_policy_refs(output: dict[str, Any]) -> None:
    """剥 policy_refs 里非真实 rule_id 的项（模型偶把废标原因句子/描述当 rule_id 塞进来）。

    防幻觉初衷不变（编造引用不入库），但改「剥」而非「任一未知即整单拒」：保留真实 rule_id；若剥后
    承重结论(approved/rejected) 无任何真实依据 → 由 _validate_audit_result 的 G1b 闸照常拒（触发重试，
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


def _normalize_optional_plan(output: dict[str, Any]) -> None:
    """extracted_data.plan 是【可选】结构化计划（G2，非承重）：形不对就丢，而非整单评标契约失败重试。

    实测 glm 全量评标因 plan 节点不符 plan 契约 → 整单拒重跑 ~290s。plan 仅审计/未来并行用，丢之
    无损结论（散文计划/内联流本就不产 plan）。
    """
    extracted = output.get("extracted_data")
    if not isinstance(extracted, dict):
        return
    if extracted.get("plan") is None:
        return
    try:
        jsonschema.validate(extracted["plan"], load_output_schema(PLAN_SCHEMA_NAME))
    except (jsonschema.ValidationError, jsonschema.SchemaError):
        extracted.pop("plan", None)  # 形不对的可选 plan → 丢弃，不拖垮整单评标


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

    # G1b（round4 F1 幻觉闸）：approved/rejected 是承重结论，必须至少引一条规则依据。
    # 空 policy_refs 的"通过/拒绝"是无依据判决——schema 只能要求字段存在(可空)，这里补语义闸。
    if verdict in {"approved", "rejected"}:
        policy_refs = structured_output.get("policy_refs")
        if not isinstance(policy_refs, list) or not policy_refs:
            raise JSONContractError(
                f"audit result with verdict={verdict} must cite at least one policy_ref."
            )
        # G1b-full（env-gated）：policy_refs 必须是真实存在的 rule_id，防模型编造规则号。
        # 这是「验证而非判断」——只查引用真伪，verdict 仍由 Claude 判。默认开(见 _rule_ref_check_enabled)。
        if _rule_ref_check_enabled():
            known = _load_known_rule_ids()
            if known:  # 加载到规则才校验；无 knowledge/ → 跳过(向后兼容)
                unknown = [ref for ref in policy_refs if ref not in known]
                if unknown:
                    raise JSONContractError(
                        f"policy_refs 引用了不存在的 rule_id（疑似编造）: {unknown}"
                    )

    _verify_scoring_consistency(structured_output)
    _verify_score_mode_consistency(structured_output)
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
        raise JSONContractError(f"extracted_data.plan 不满足 plan 契约: {exc.message}") from exc


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


_SCORE_MODE_TOLERANCE = 0.01


def _sum_hit_field(hits: Any, field: str) -> float | None:
    """累加 hits 列表里每条的数值字段；列表空或任一非数 → None（放弃校验，绝不误报）。"""
    if not isinstance(hits, list) or not hits:
        return None
    total = 0.0
    for hit in hits:
        if not isinstance(hit, dict):
            return None
        value = hit.get(field)
        if not _is_real_number(value):
            return None
        total += value
    return total


def _verify_score_mode_consistency(structured_output: dict[str, Any]) -> None:
    """按 criteria 各项 score_mode 校验 scoring 算术自洽，不一致记 warning（不阻断）。

    反馈子系统（tender-harness 第1轮）：deduction 项 score=max−Σ扣、banded 项 score=选档分、
    additive 项 score=base+Σ加。**仅**校验 status=scored 且有对应明细的项；
    null/manual_review/无明细/formula/pass_fail 一律跳过（防档次分等被当扣分误报）。
    不一致 → append ``extracted_data.validation_warnings``（{code,item,detail}）交人工复核，
    绝不打回重评（尊重"靠大模型判断"与区间打分制）。
    """
    extracted = structured_output.get("extracted_data")
    if not isinstance(extracted, dict):
        return
    scoring = extracted.get("scoring")
    if not isinstance(scoring, list):
        return
    # 整单是否实质性不响应/投错标（codex P1-1：只在此情形对"无依据 0"硬降级，避免误伤正常客观 0
    # ——如 additive「提供才加分」确认没加分内容、规则「未提供不得分」确认缺失，这些 0 是合理的）。
    # 用 _meaningful_disqualification_hits 防 "无"/[{}] 假值误触（codex R2 P1）。**故意只看
    # disqualification_hits、不含 eligibility_checks**（与 verdict 纠偏的更宽口径不同，codex R2 P2）：
    # 本降级针对"投错标/无可评事实"，而资格不符(eligibility fail)的投标往往仍有可评的业绩/方案，
    # 不应把其逐项分降级 manual_review。
    has_disqualification = _meaningful_disqualification_hits(extracted)
    # criteria 各项按 item 名索引（取 score_mode / base）。
    criteria_items: dict[str, dict[str, Any]] = {}
    criteria = extracted.get("criteria")
    if isinstance(criteria, dict):
        for citem in criteria.get("items") or []:
            if isinstance(citem, dict) and isinstance(citem.get("item"), str):
                criteria_items[citem["item"]] = citem
    warnings: list[dict[str, Any]] = []
    # criteria 完整性（codex P1-5）+ score_mode 缺失兜底告警（codex P1-4）：遍历 criteria 各项，
    # 缺 score_mode → 告警(校验按 deduction 兜底)；score_mode 与容器不匹配(deduction 无 deductions
    # 等) → 告警。均软提示不阻断。
    _CONTAINER_BY_MODE = {"deduction": "deductions", "banded": "bands", "additive": "awards"}
    for citem in criteria_items.values():
        name = citem.get("item")
        mode = citem.get("score_mode")
        if mode is None:
            warnings.append(
                {
                    "code": "criteria_missing_score_mode",
                    "item": name,
                    "detail": "评分项未声明 score_mode，校验按 deduction 兜底，请人工确认评分方式",
                }
            )
            continue
        required = _CONTAINER_BY_MODE.get(mode)
        # 容器键完全缺失才告警（可能漏提取）；空 [] 合法（招标文件无明列细则，靠 scoring_rule 整体判断）。
        if required and required not in citem:
            warnings.append(
                {
                    "code": f"criteria_{mode}_missing_{required}",
                    "item": name,
                    "detail": f"score_mode={mode} 但缺 {required}，请人工确认评分细则是否漏提取",
                }
            )
    for item in scoring:
        if not isinstance(item, dict) or item.get("status") != "scored":
            continue
        score = item.get("score")
        max_score = item.get("max")
        if not _is_real_number(score) or not _is_real_number(max_score):
            continue
        citem = criteria_items.get(item.get("item")) or {}
        # mode 缺失默认 deduction 兜底（codex P1-4）；下面仅在有对应明细时才实际校验，无明细不误报。
        mode = citem.get("score_mode") or item.get("score_mode") or "deduction"
        expected: float | None = None
        detail = ""
        if mode == "deduction":
            total = _sum_hit_field(item.get("deduction_hits"), "deducted")
            if total is not None:
                expected = max_score - total
                detail = f"满分{max_score}−扣{total}"
            elif _SCORE_MODE_TOLERANCE < score < max_score and not item.get("deduction_hits"):
                # R4 明细完整性：部分扣分(0<score<max)却无 deduction_hits 逐条明细 = 笼统扣X分
                # （违 tender-evaluate.md「禁止笼统扣X分」）。score==0 由下方 absence 兜底覆盖，不重复。
                warnings.append(
                    {
                        "code": "deduction_scored_no_hits",
                        "item": item.get("item"),
                        "detail": f"扣分项判 scored 得 {score}/{max_score}（已扣 {max_score - score}）"
                        "却无 deduction_hits 逐条明细，疑笼统扣分，请人工核验扣分依据",
                    }
                )
        elif mode == "banded":
            band = item.get("selected_band")
            if isinstance(band, dict) and _is_real_number(band.get("points")):
                expected = band["points"]
                detail = f"选档「{band.get('level')}」得{expected}"
        elif mode == "additive":
            total = _sum_hit_field(item.get("award_hits"), "awarded")
            base = citem.get("base", 0)
            if total is not None and _is_real_number(base):
                expected = base + total
                detail = f"基础{base}+加{total}"
            elif _is_real_number(base) and score > base and not item.get("award_hits"):
                # R4 明细完整性：加了分(score>base)却无 award_hits 明细 → 笼统加分。
                warnings.append(
                    {
                        "code": "additive_scored_no_awards",
                        "item": item.get("item"),
                        "detail": f"加分项判 scored 得 {score} > 基础 {base} 却无 award_hits 明细，"
                        "请人工核验加分依据",
                    }
                )
        elif mode == "formula":
            # G5 兜底（codex P1-3）：formula 判了 scored，但 criteria 项缺结构化 formula_spec 或含
            # 不可闭合变量（cross_bid/external_data/live_event/derived）→ 本不该单家自动算，warning
            # 提示人工（防 prompt 不可靠时模型 fallback 临场心算）。不硬降级（限价类可能确实算对了）。
            spec = citem.get("formula_spec")
            spec_vars = spec.get("variables") if isinstance(spec, dict) else None
            if not isinstance(spec_vars, list) or not spec_vars:
                warnings.append(
                    {
                        "code": "formula_scored_no_spec",
                        "item": item.get("item"),
                        "detail": "formula 项判了 scored 但缺结构化 formula_spec，疑似临场心算，请人工核验算分依据",
                    }
                )
            elif any(
                isinstance(v, dict)
                and v.get("source") in {"cross_bid", "external_data", "live_event", "derived"}
                for v in spec_vars
            ):
                warnings.append(
                    {
                        "code": "formula_scored_not_closeable",
                        "item": item.get("item"),
                        "detail": "formula 项判了 scored 但公式含横比/外部/现场变量，单家本算不了，请人工确认是否应 manual_review",
                    }
                )
            elif any(isinstance(v, dict) and v.get("value") is None for v in spec_vars):
                # codex P1-1：source 全可闭合，但有变量未填 value（限价/本家报价没抽到）→ 无法确定性
                # 代入，判了 scored 必是临场心算。warning 提示人工（不硬降级，prompt 已要求此情形 manual）。
                warnings.append(
                    {
                        "code": "formula_scored_missing_value",
                        "item": item.get("item"),
                        "detail": "formula 项判了 scored 但 formula_spec 有变量未填 value（缺限价或本家报价），无法确定性代入，请人工核验算分",
                    }
                )
        # formula / pass_fail / manual / 无明细 → expected 仍为 None，跳过。
        if expected is not None and abs(score - expected) > _SCORE_MODE_TOLERANCE:
            warnings.append(
                {
                    "code": f"score_mode_{mode}_mismatch",
                    "item": item.get("item"),
                    "detail": f"score={score} 与「{detail}={expected}」不一致，请人工复核",
                }
            )
        # A（absence-is-not-zero 兜底，dogfood 实测证明 prompt 强化不可靠：模型反复把"投标无对应内容"
        # 判 0 分 scored）：实得 0 分却标 scored 但【无评分依据明细】→ 降级 manual_review（无依据的 0 =
        # 无法判定，不是客观得 0）。**保留**：deduction 真扣减到 0（有 deduction_hits）、pass_fail
        # （客观"未满足"是有依据的 0）。
        if abs(score) < _SCORE_MODE_TOLERANCE:
            deducted_to_zero = (
                mode == "deduction"
                and isinstance(item.get("deduction_hits"), list)
                and bool(item.get("deduction_hits"))
            )
            justified = deducted_to_zero or mode == "pass_fail"
            if not justified and has_disqualification:
                # 整单实质性不响应/投错标：该项多半无可评事实（投标根本没投这块）→ 硬降级
                # manual_review，不留"评了判 0 通过"的假象。
                item["status"] = "manual_review"
                item["score"] = None
                item.setdefault("manual_review_reason", "insufficient_evidence")
                warnings.append(
                    {
                        "code": "scored_zero_demoted",
                        "item": item.get("item"),
                        "detail": "整单实质性不响应，该项实得 0 且无评分依据明细，已降级 manual_review",
                    }
                )
            elif not justified:
                # 正常案例：实得 0 但无明细，可能是合理客观 0（招标规则"提供才加分/不满足不得分"且
                # 确认缺失），也可能漏判 → 仅告警、不强改判断（codex P1-1：避免误伤客观 0）。
                warnings.append(
                    {
                        "code": "scored_zero_suspect",
                        "item": item.get("item"),
                        "detail": "实得 0 分但无评分依据明细，请人工确认是规则性 0（确认缺失）还是漏判",
                    }
                )
    if warnings:
        existing = extracted.get("validation_warnings")
        if isinstance(existing, list):
            existing.extend(warnings)
        else:
            extracted["validation_warnings"] = warnings


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
        raise JSONContractError(
            "init-rules cannot return status=initialized with empty categories."
        )
    if not isinstance(extracted_rule_count, int) or extracted_rule_count <= 0:
        raise JSONContractError(
            "init-rules cannot return status=initialized with extracted_rule_count <= 0."
        )


# 服务端权威元数据：reviewed_by/timestamp 模型不该(也不可靠地)产出；claim_id 缺失时回落任务 request_id。
# 在 G1 硬校验前盖章，避免把"服务端该填的字段"当成模型 bug 反复重试至失败（live eval 实测 [1M] 常漏这些）。
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
    # 仍必填非空；approved/rejected 的 policy_refs 即便默认 [] 也会被 G1b 闸要求非空 → 正确触发重试，
    # 不会放过无依据判决）；②risk_score 缺省给中性 50（不触发高风险复审，不伪造高危）。
    output.setdefault("reasons", [])
    output.setdefault("policy_refs", [])
    output.setdefault("evidence_chain", [])
    output.setdefault("risk_score", 50)


def normalize_audit_result(
    structured_output: StructuredJSON, request_id: str | None = None
) -> StructuredJSON:
    """G1 前置规整：盖 server 元数据 + 拍平 envelope 格式，使硬 schema 校验只挡真问题。

    1. 元数据：claim_id(缺→request_id)/reviewed_by/timestamp/extracted_data 默认值。
    2. reasons/policy_refs：对象→字符串（防前端崩 + 满足 string[] 契约）。
    3. risk_dimensions：对象映射/0-100 量纲 → [{name∈枚举,score 0-10}]；非法项清除；空则丢(可选字段)。

    与 ``enrich_audit_decision`` 的分工：normalize 跑在硬 schema 校验**前**（只产 schema 内字段）；
    enrich 跑在校验**后**（派生 schema 外的 result/conclusion）。
    """
    if not isinstance(structured_output, dict):
        return structured_output
    _stamp_server_metadata(structured_output, request_id)
    # 承重 verdict 一致性（R2）：废标/资格否决独立 gate 优先级最高——extracted_data.disqualification_hits
    # 非空，或任一 eligibility_checks.status=fail（命中硬废标/资格否决）→ verdict 必须 rejected
    # （命令 S4 法定规则）。模型偶把"投错标/实质性未响应"判成 manual_review（S4 在"废标→rejected"
    # 与"有 manual_review 项→manual_review"间优先级含糊，模型择后者，与其自己标的 disqualification_hits
    # 自相矛盾）→ 此处确定性纠偏。跑在硬校验**前** → 纠偏后的 rejected 仍过 policy_refs 真伪闸
    # （模型既已据废标条款标 disqualification_hits，通常已带 policy_refs；缺则校验失败触发重试，正确）。
    if structured_output.get("verdict") != "rejected" and _has_hard_disqualification(
        structured_output.get("extracted_data")
    ):
        structured_output["verdict"] = "rejected"
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
    # 降评标重试（D，零成本提速）：可选 plan 形不对 → 丢（非承重）；policy_refs 里编造的 rule_id → 剥
    # （留真实引用，承重无依据仍由 G1b 拒）。两者原本任一不合即整单契约失败、重跑整个 ~290s 评标。
    _normalize_optional_plan(structured_output)
    _strip_unknown_policy_refs(structured_output)
    # result/conclusion 是服务端从 verdict 派生的【决策】字段（enrich 后才有）；模型【自报】它们＝
    # 篡改决策（H1 反幻觉），必须拒、绝不静默剥离。
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


from server.common.evidence_resolution import resolve_audit_evidence  # noqa: E402

register_schema_processor(
    DEFAULT_OUTPUT_SCHEMA_NAME,
    normalize=normalize_audit_result,
    validate=_validate_audit_result,
    enrich=enrich_audit_decision,
    # R1：拿到本案底稿时回查结论里每条出处真伪（仅 tender_worker 透传 evidence_source 才触发；
    # audit/expense 不透传 → 跳过，零影响）。
    resolve=resolve_audit_evidence,
)
register_schema_processor(
    INIT_RULES_REPORT_SCHEMA_NAME,
    validate=_validate_init_rules_report,
)
