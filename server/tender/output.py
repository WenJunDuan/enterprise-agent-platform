"""Tender 专属输出后处理 + 注册表 key（F6 schema 分家，本模块新家，原 server/common/tender_output.py）。

``output_contracts.py`` 挂的 ``DEFAULT_OUTPUT_SCHEMA_NAME`` 是 expense/tender/audit **共享** 的
audit-result 契约策略（通用 normalize/validate/enrich）；评分一致性校验、废标/资格否决 gate、
解释文本规范化等 **仅 tender 评标** 用得到的 6 个 helper 落本模块。本模块额外提供三个 tender
**组合函数**（``normalize_tender_result``/``validate_tender_result``/``enrich_tender_result`` ——
各自「通用版 + tender-only 步骤」的拼装，顺序对应拆分前合并函数里的原始行号顺序，详见函数
docstring），并把它们注册到独立的 ``TENDER_OUTPUT_SCHEMA_NAME``，使 tender 评标校验彻底不再
挂在 expense/audit 共用的 ``DEFAULT_OUTPUT_SCHEMA_NAME`` 上（根治 D0 那类"tender 逻辑误伤
expense 解释"的跨域污染温床，也让 ``server/common/**`` 不再反向依赖 ``server/tender/**``）。

依赖方向严格单向：本模块 → ``server.common.output_contracts``（tender→common，合法下行；
``output_contracts`` 不 import 本模块，无环）。6 个 tender-only helper 函数体内仍对
``server.common.contract`` 使用惰性 import（沿用旧 tender_output.py 的既有写法，未改动）。
"""

from __future__ import annotations

import re
from typing import Any

import jsonschema

from server.common.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    StructuredJSON,
    register_schema_processor,
)
from server.common.output_contracts import (
    _validate_audit_result,
    enrich_audit_decision,
    normalize_audit_result,
)

# 不在模块顶层 import server.common.contract 的其余符号（JSONContractError/load_output_schema）：
# 会形成 contract → output_contracts → tender_output(旧名) → contract 的**加载期**环——当本模块被
# 最先 import 时，contract 末尾回头 import output_contracts，而 output_contracts 又来 import 本模块
# 尚未定义的函数 → ImportError（S4 交叉 review P1）。改在用到的函数内惰性 import，彻底断开该环。
# `DEFAULT_OUTPUT_SCHEMA_NAME`/`register_schema_processor` 与 `output_contracts` 的通用函数在
# 顶层 import 是安全的：`server.common.contract` 模块加载完成（含其末尾对 output_contracts 的
# import）后才会轮到 tender 包被 import，两者在本模块加载时已在 sys.modules 就绪，不产生新环。

PLAN_SCHEMA_NAME = "common/plan.schema.json"

TENDER_OUTPUT_SCHEMA_NAME = "tender/audit-result.schema.json"
# 仅注册表 key；物理 schema 复用 common/audit-result.json（见下方 register_schema_processor 的
# schema_path=DEFAULT_OUTPUT_SCHEMA_NAME）。刻意不在 .claude/contracts/tender/ 下建同名文件——
# 建了反而会被 resolve_output_schema_path 误当成"真的物理文件"而与共享 schema 产生内容漂移。

# ── 废标/资格否决 gate（tender S4：独立 gate 决定 verdict，与逐项 scoring 解耦）────────────

_UNCONFIRMED_TOKENS = {"false", "no", "0", "疑似", "待确认", "待核验", "unconfirmed", "manual"}


def _hit_unconfirmed(hit: dict[str, Any]) -> bool:
    """该废标命中是否被模型**明确标为未确认**（疑似 / 读不清 / 待人工核验）→ 不应触发 rejected。

    读不清的信用截图等疑似信号若被写进 disqualification_hits、又被门禁强制 rejected，
    会与"须人工核验"分析自相矛盾并误废标合规投标人：
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

    extracted_data 内部无 schema 形校验：模型可能写 ``"无"``（中文"没有"，truthy
    字符串！）/ ``{}`` / ``[{}]`` / ``[]`` 等假值——朴素 ``bool(...)`` 会把 ``"无"`` 当命中→误判
    rejected。故收窄为"非空 list + 至少一项是有内容的 dict"，把这些假值挡在外面。
    再排除模型**明确标为未确认**（疑似/读不清）的命中——它们不该强制 rejected（见 _hit_unconfirmed）。
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
    结构，恒 False，故对 expense 无影响。status 比较做大小写/空白容错。
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


# ── 解释文本规范化（tender：服务端重算得分小结 + 脱内部术语 + 资格不通过前缀）────────────

_USER_SUMMARY_MARKER = "得分小结："
_EVIDENCE_CHAIN_FIELDS = ("source", "finding", "conclusion")
_SCORING_HIT_KEYS = ("award_hits", "deduction_hits")
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


def _is_tender_explanation_output(output: dict[str, Any]) -> bool:
    """Tender-only guard for score-summary explanation rewriting.

    The common audit-result contract is shared by expense and tender. Only tender results carry
    scoring/eligibility structures that need server-side score recap normalization.
    """
    extracted = output.get("extracted_data")
    return isinstance(extracted, dict) and (
        "scoring" in extracted or "eligibility_checks" in extracted
    )


def _is_empty_evidence_chain(value: Any) -> bool:
    """Return whether a normalized evidence chain carries no non-blank evidence."""
    if value is None:
        return True
    if not isinstance(value, list):
        return False
    return not any(
        isinstance(item, dict)
        and any(str(item.get(field) or "").strip() for field in _EVIDENCE_CHAIN_FIELDS)
        for item in value
    )


def _evidence_entry_from_hit(item: dict[str, Any], hit: dict[str, Any]) -> dict[str, str] | None:
    """Map one scoring hit to the common evidence-chain shape, if it has content."""
    evidence = hit.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else hit
    source = evidence.get("source") or hit.get("source")
    finding = evidence.get("quote") or evidence.get("finding") or hit.get("finding")
    conclusion = hit.get("conclusion") or item.get("basis") or evidence.get("conclusion")
    entry = {field: str(value or "") for field, value in (
        ("source", source),
        ("finding", finding),
        ("conclusion", conclusion),
    )}
    return entry if any(entry.values()) else None


def _derive_scoring_evidence(extracted: Any) -> list[dict[str, str]]:
    """Collect scoring evidence, keeping score-moving hits before zero-point hits."""
    if not isinstance(extracted, dict) or not isinstance(extracted.get("scoring"), list):
        return []
    prioritized: list[dict[str, str]] = []
    fallback: list[dict[str, str]] = []
    for item in extracted["scoring"]:
        if not isinstance(item, dict):
            continue
        for hits_key in _SCORING_HIT_KEYS:
            hits = item.get(hits_key)
            if not isinstance(hits, list):
                continue
            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                entry = _evidence_entry_from_hit(item, hit)
                if entry is None:
                    continue
                target = prioritized if _hit_moves_score(hit, hits_key) else fallback
                target.append(entry)
    return prioritized + fallback


def _derive_tender_evidence_chain(output: dict[str, Any]) -> None:
    """Fill an empty tender evidence chain from deterministic scoring-hit evidence."""
    if not _is_empty_evidence_chain(output.get("evidence_chain")):
        return
    output["evidence_chain"] = _derive_scoring_evidence(output.get("extracted_data"))


def _finalize_user_explanation(output: dict[str, Any]) -> None:
    if not _is_tender_explanation_output(output):
        return
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


# ── 可选 plan 结构校验（tender extracted_data.plan，非承重）──────────────────────────────


def _normalize_optional_plan(output: dict[str, Any]) -> None:
    """extracted_data.plan 是【可选】结构化计划（非承重）：形不对就丢，而非整单评标契约失败重试。

    实测 glm 全量评标因 plan 节点不符 plan 契约 → 整单拒重跑 ~290s。plan 仅审计/未来并行用，丢之
    无损结论（散文计划/内联流本就不产 plan）。
    """
    from server.common.contract import load_output_schema  # 惰性 import，断模块加载期环

    extracted = output.get("extracted_data")
    if not isinstance(extracted, dict):
        return
    if extracted.get("plan") is None:
        return
    try:
        jsonschema.validate(extracted["plan"], load_output_schema(PLAN_SCHEMA_NAME))
    except (jsonschema.ValidationError, jsonschema.SchemaError):
        extracted.pop("plan", None)  # 形不对的可选 plan → 丢弃，不拖垮整单评标


def _verify_plan_shape(structured_output: dict[str, Any]) -> None:
    """若命令把 S1 计划升级为结构化 ``extracted_data.plan``，校验其满足 plan 契约。

    可选——未产出 plan（散文计划/内联单 agent 流）则跳过；产出了就必须类型正确
    （每节点 step/intent + 可选 reads/tools/produces/tag）。
    """
    from server.common.contract import JSONContractError, load_output_schema  # 惰性，断加载环

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


# ── 评分算术自洽校验（tender scoring；不替模型判分，只挡自相矛盾/无依据 0）────────────────

_SCORE_MODE_TOLERANCE = 0.01


def _is_real_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# 公开别名（D1 T1）：server.tender.eval 的 score_consistency 复用同一实数判定，避免跨模块
# import 私有名、也避免第二套语义分歧（生产 scoring 校验与 eval 回归闸必须同源判定）。
is_real_number = _is_real_number


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


def _verify_scoring_consistency(structured_output: dict[str, Any]) -> None:
    """评分项内部算术一致性——每项 0 ≤ score ≤ max。

    不替模型判分，只拒"给了超出量纲的分"这类自相矛盾输出（如 max=10 却给 15）。
    仅在 ``extracted_data.scoring`` 存在时触发；``score=null``（不可判定/manual_review 项）跳过。
    """
    from server.common.contract import JSONContractError  # 惰性 import，断模块加载期环

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


def _verify_score_mode_consistency(structured_output: dict[str, Any]) -> None:
    """按 criteria 各项 score_mode 校验 scoring 算术自洽，不一致记 warning（不阻断）。

    deduction 项 score=max−Σ扣、banded 项 score=选档分、additive 项 score=base+Σ加。
    **仅**校验 status=scored 且有对应明细的项；
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
    # 整单是否实质性不响应/投错标：只在此情形对"无依据 0"硬降级，避免误伤正常客观 0
    # ——如 additive「提供才加分」确认没加分内容、规则「未提供不得分」确认缺失，这些 0 是合理的）。
    # 用 _meaningful_disqualification_hits 防 "无"/[{}] 假值误触。**故意只看
    # disqualification_hits、不含 eligibility_checks**（与 verdict 纠偏的更宽口径不同）：
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
    # criteria 完整性 + score_mode 缺失兜底告警：遍历 criteria 各项，
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
        # mode 缺失默认 deduction 兜底；下面仅在有对应明细时才实际校验，无明细不误报。
        mode = citem.get("score_mode") or item.get("score_mode") or "deduction"
        expected: float | None = None
        detail = ""
        if mode == "deduction":
            total = _sum_hit_field(item.get("deduction_hits"), "deducted")
            if total is not None:
                expected = max_score - total
                detail = f"满分{max_score}−扣{total}"
            elif _SCORE_MODE_TOLERANCE < score < max_score and not item.get("deduction_hits"):
                # 明细完整性：部分扣分(0<score<max)却无 deduction_hits 逐条明细 = 笼统扣X分
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
                # 明细完整性：加了分(score>base)却无 award_hits 明细 → 笼统加分。
                warnings.append(
                    {
                        "code": "additive_scored_no_awards",
                        "item": item.get("item"),
                        "detail": f"加分项判 scored 得 {score} > 基础 {base} 却无 award_hits 明细，"
                        "请人工核验加分依据",
                    }
                )
        elif mode == "formula":
            # Formula 兜底：formula 判了 scored，但 criteria 项缺结构化 formula_spec 或含
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
                # source 全可闭合，但有变量未填 value（限价/本家报价没抽到）→ 无法确定性
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
        # absence-is-not-zero 兜底：模型反复把"投标无对应内容"
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
                # 确认缺失），也可能漏判 → 仅告警、不强改判断，避免误伤客观 0。
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


# ── Tender 组合函数（generic + tender-only steps；顺序对应拆分前合并函数的原始行号顺序）──────


def normalize_tender_result(
    structured_output: StructuredJSON, request_id: str | None = None
) -> StructuredJSON:
    """Tender 组合版 normalize。

    废标/资格否决 verdict 纠偏必须排在通用 normalize **之前**：拆分前的合并函数里，纠偏
    先于 manual_review_reason 清理（`verdict != manual_review` 才 pop）——若纠偏把 verdict 从
    manual_review 拍成 rejected，随后的清理才会正确剥掉残留的 manual_review_reason。倒过来跑，
    清理会看到"纠偏前"的 verdict，manual_review_reason 不会被剥（回归，
    `test_disqualification_hits_coerce_verdict_to_rejected` 会失败）。可选 plan 丢弃排在通用
    normalize **之后**：它只操作 `extracted_data.plan`，通用 normalize 的任何一步都不碰
    `extracted_data` 内部结构（`extracted_data` 本身是白名单顶层字段，整体保留），两者互不依赖，
    与拆分前的相对位置（原函数末尾）等价。
    """
    if isinstance(structured_output, dict):
        if structured_output.get("verdict") != "rejected" and _has_hard_disqualification(
            structured_output.get("extracted_data")
        ):
            structured_output["verdict"] = "rejected"
    structured_output = normalize_audit_result(structured_output, request_id)
    if isinstance(structured_output, dict):
        structured_output["reviewed_by"] = "tender-evaluator"
        if structured_output.get("evidence_chain") is None:
            structured_output["evidence_chain"] = []
        _normalize_optional_plan(structured_output)
    return structured_output


def validate_tender_result(structured_output: StructuredJSON) -> None:
    """Tender 组合版 validate：通用闸（verdict/policy_refs/风险维度清洗）之后追加评分一致性
    三闸。三者操作的字段互不相交（通用闸不碰 extracted_data.scoring/plan），排列顺序对结果无影响
    ——沿用拆分前 `_validate_audit_result` 内的原始调用顺序（scoring→score_mode→plan_shape）。
    """
    _validate_audit_result(structured_output)
    _verify_scoring_consistency(structured_output)
    _verify_score_mode_consistency(structured_output)
    _verify_plan_shape(structured_output)


def enrich_tender_result(structured_output: StructuredJSON) -> StructuredJSON:
    """Tender 组合版 enrich：通用派生（result/conclusion/policy_refs_detail/risk_dimensions）
    之后追加得分小结重算 + 术语脱敏——`_finalize_user_explanation` 在拆分前的合并函数里本来就是
    最后一条语句，这里原样保留在最后，顺序零变化。
    """
    structured_output = enrich_audit_decision(structured_output)
    if isinstance(structured_output, dict):
        _derive_tender_evidence_chain(structured_output)
        _finalize_user_explanation(structured_output)
    return structured_output


from server.tender.evidence import _hit_moves_score, resolve_audit_evidence  # noqa: E402

register_schema_processor(
    TENDER_OUTPUT_SCHEMA_NAME,
    normalize=normalize_tender_result,
    validate=validate_tender_result,
    enrich=enrich_tender_result,
    resolve=resolve_audit_evidence,
    schema_path=DEFAULT_OUTPUT_SCHEMA_NAME,
)
