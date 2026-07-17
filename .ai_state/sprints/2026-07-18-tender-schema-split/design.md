# tender-schema-split · F6(schema 分家) + F5(evidence 拆分) — design

> roadmap: 2026-07-doc-intelligence（承接 D2 拆出项）
> path: **Refactor（红区）** · effort M · depends_on: D2（已 merge，260a140/2288862，main 834 绿）
> 前置阅读（已读，本设计建立在其结论上）：
> - `.ai_state/compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md`
> - `.ai_state/sprints/2026-07-16-tender-feature-package/design.md`「Round 1/2 · Critic Findings」+「Round 1 修订应答」+「Round 2 后 · D2 范围定稿」
> 红区纪律：subagent(`generator`) + 原生 `isolation: worktree` 强制；每个 Task 单独 commit，pytest 全绿再进下一个。

## 背景（WHY）

D2 的 Round-2 critic（主 agent 已独立核验，见上述 compound 决策）证伪了 Round-1 的判断——F6
（tender schema 分家）不是"contract 机制的向后兼容小改"，而是**共享 contract 层的行为重构**：

- `server/common/output_contracts.py:30-37` 从 `server/common/tender_output.py` import 6 个
  tender 专属校验/规范化函数，**直接内嵌**进 3 个共享函数体：
  - `normalize_audit_result`（:388-457）在 :409 调 `_has_hard_disqualification`（废标/资格否决
    verdict 纠偏）、在 :443 调 `_normalize_optional_plan`（可选 plan 形不对丢弃）。
  - `_validate_audit_result`（:263-312）在 :309-311 调 `_verify_scoring_consistency` /
    `_verify_score_mode_consistency` / `_verify_plan_shape`。
  - `enrich_audit_decision`（:165-194）在 :193 调 `_finalize_user_explanation`（服务端重算得分
    小结 + 内部术语脱敏 + 资格不通过前缀）。
- 这 3 个函数在 :462-470 被**单一处理器**注册进 `_SCHEMA_PROCESSORS[DEFAULT_OUTPUT_SCHEMA_NAME]`
  （`common/audit-result.schema.json`）——expense/audit/tender 三个业务域的结论**共用同一个 key**，
  所以 tender 专属校验无条件跑在 expense/audit 结果上（虽然经代码核验，6 个 helper 都有 tender-only
  guard，对 expense/audit 数据是 no-op——`_is_tender_explanation_output` 守卫、
  `extracted_data.disqualification_hits`/`eligibility_checks`/`scoring`/`plan` 在 expense 数据里
  恒不存在——但"共用同一注册表 key"本身仍是分层污染，且 `contract.py:252` 的 import-time 副作用
  会把纯 audit 调用也拉进 `server.common.tender_output` 模块）。
- 要把 tender 逻辑真正搬进 `server/tender/`（D2 的既定目标，`server/tender/` 已落地
  worker/compare_worker/doc_pipeline/runner/eval），必须先把这 3 个函数**一分为二**：通用版留
  `output_contracts.py` 挂 `DEFAULT_OUTPUT_SCHEMA_NAME`；tender 组合版搬进
  `server/tender/output.py` 挂一个新 tender 专属 schema key——否则 `server/common/` 会反向依赖
  `server/tender/`，撞 `tests/test_layering.py::test_common_does_not_import_feature_or_upper_layers`
  （forbidden 元组已含 `"server.tender"`，只是 tender_output.py 目前还在 `common/` 内，尚未触发）。
- 同理，`server/common/evidence_resolution.py` 的 `resolve_audit_evidence`（tender 评标出处回查
  闸，含 scoring 降级语义）与其中的通用语料检索原语（`normalize_text`/`parse_corpus`/
  `CorpusIndex`/`existence_ratio`/...，D7 结构化检索要复用、ocr 测试也已依赖）混在一个文件里，
  同样需要按"是否携带 scoring 语义"拆分（F5，用户已拍板：通用留 common，tender 专属迁 tender）。

主 agent 本轮**在 D2 已核实基础上补做的额外核验**（下述内容超出 D2 design 的记录范围，是本设计
新增的关键发现，务必写入实现）：

1. **`server/common/contract.py:56-58` `build_output_format` 也直接 `load_output_schema(schema_name)`**
   ——它是 `json_bridge.py:168` 构造 SDK `output_format`（模型侧结构化输出约束）的唯一入口。若
   schema_path 别名机制只补 `_validate_against_json_schema`（Round-1 F1 的原始范围），tender 传入
   新 key 后 `build_output_format(TENDER_OUTPUT_SCHEMA_NAME)` 会去找不存在的
   `.claude/contracts/tender/audit-result.schema.json` → `JSONContractError` → **tender-evaluate-json
   在 T4 切换 schema_name 后必炸**，且不会被任何现有测试捕获（现有测试都直接调
   `apply_schema_semantics`，没有测过 `build_output_format` 的物理解析）。本设计的 T1 把两处统一到
   一个 `_resolve_physical_schema_name` helper。
2. **除 `tests/test_contract_registry.py`（38 处）外，`tests/test_tender_criteria_flow.py`
   （23 处，22 个真实调用点）与 `tests/test_evidence_resolution.py`（4 处，2 个真实调用点）也用
   `DEFAULT_OUTPUT_SCHEMA_NAME` 驱动 tender 行为**——D2 design 只提到 `test_contract_registry.py`
   的 38 处，本设计核实后确认还有这两个文件必须同批迁移，否则会静默留下"用 DEFAULT key 测 tender
   行为"的死角（迁移后如果这些测试不改，会失败——不是静默通过，但会被误判为"设计漏项"而非"预期
   迁移"，故这里显式登记）。
3. **`tests/test_tender_routes.py:23` 的 `EVAL_SCHEMA` 常量在 `test_worker_forwards_to_evaluate_bid_and_persists`
   （约 :225-263）里真实断言 `runner.py` 转发的 `schema_name`**——T4 切换 `runner.py:223` 后此断言
   必炸，必须同步改常量来源。`tests/test_cli_tender_evaluate.py:18` 同理（D2/Round-2 F2 已记录，
   本设计确认其余 5 个含 `"common/audit-result.schema.json"` 字面量的测试文件——
   `test_tender_read_layer.py`/`test_codex_p2_rework_fixes.py`/`test_tender_compare.py`/
   `test_domain_profile.py`——都只是构造 fixture/mock 返回值，**不断言该字面量**，核实后确认无需
   改动，避免过度改动无关测试）。

## 方案（HOW）

### T1 — contract.py：`schema_path` 别名机制（机制先行，纯增量，零行为变更）

`server/common/contract.py`：

1. `SchemaProcessor`（:61-79，frozen dataclass）加一个可选字段：

   ```python
   # schema_path: 物理 .claude/contracts 文件名覆盖（可选）。None（默认）＝物理文件与注册表 key
   # 同名（现状，audit/expense 零变化）；设置时，本 key 的处理器链挂在 schema_name 下，但硬 schema
   # 校验 / SDK output_format 复用 schema_path 指向的另一物理文件——供 tender 专属处理器链复用
   # 共享 audit-result.json，不必产出 byte-identical 副本。
   schema_path: str | None = None
   ```

2. `register_schema_processor`（:85-100）加同名可选关键字参数，透传进 `SchemaProcessor(...)`。

3. 新增一个私有 helper（放在 `_SCHEMA_PROCESSORS` 定义之后，`_validate_against_json_schema` 之前）：

   ```python
   def _resolve_physical_schema_name(schema_name: str) -> str:
       """Resolve the physical `.claude/contracts/` file for a registry key.

       A registered processor may declare `schema_path` to reuse a different physical
       schema file than its own registry key (tender's key reuses the shared
       audit-result.json without a byte-duplicate file). Unregistered keys, or
       processors without schema_path, resolve to themselves — audit/expense unchanged.
       """
       processor = _SCHEMA_PROCESSORS.get(schema_name)
       if processor is not None and processor.schema_path:
           return processor.schema_path
       return schema_name
   ```

4. **两个调用点都要改**（这是本设计相对 D2/Round-1 的关键订正，Round-1 只提了第一个）：
   - `apply_schema_semantics`（:159-165）：`_validate_against_json_schema(schema_name, ...)` →
     `_validate_against_json_schema(_resolve_physical_schema_name(schema_name), ...)`。
   - `build_output_format`（:56-58）：`load_output_schema(schema_name)` →
     `load_output_schema(_resolve_physical_schema_name(schema_name))`。

   （`processor = _SCHEMA_PROCESSORS.get(schema_name)` 这一行——用于取 normalize/validate/enrich/
   resolve hook 的查表——**不变**，仍用原始 `schema_name`；只有"去哪个物理文件做形校验/建
   output_format"这两处改用解析后的名字。两者职责不同，不要合并成一次查表。）

TDD：先写一个独立单测（可放 `tests/test_core_pure.py` 或 `test_contract_registry.py` 新增一节），
用 `register_schema_processor("test/alias-demo.schema.json", validate=lambda o: None,
schema_path=DEFAULT_OUTPUT_SCHEMA_NAME)` 注册一个别名 key，断言：
(a) `apply_schema_semantics("test/alias-demo.schema.json", <合法 audit-result payload>)` 通过硬
schema 校验（证明用了 audit-result.json 的形）；
(b) `build_output_format("test/alias-demo.schema.json")["schema"] == load_output_schema(DEFAULT_OUTPUT_SCHEMA_NAME)`
（证明 SDK output_format 也解析到同一物理文件）；
测试结束 `_SCHEMA_PROCESSORS.pop("test/alias-demo.schema.json", None)` 清理（照抄
`test_register_new_schema_takes_effect_without_editing_dispatcher` 的收尾模式）。
此步不改任何既有行为（`DEFAULT_OUTPUT_SCHEMA_NAME`/`INIT_RULES_REPORT_SCHEMA_NAME` 两个既有
processor 都没设 `schema_path` → `_resolve_physical_schema_name` 原样返回 `schema_name` → 两个
既有调用点行为不变）。**commit 1，pytest 全绿。**

### T2 — F6 三函数拆分 + tender_output.py 搬家 + TENDER_OUTPUT_SCHEMA_NAME 注册

**新增 `server/tender/output.py`**（内容 = `server/common/tender_output.py` 全文 `git mv` 过来，
更新模块 docstring 说明新家 + 组合函数，其余 6 个 helper 函数体/`PLAN_SCHEMA_NAME`/
`is_real_number` 别名等**原样不动**），追加：

```python
TENDER_OUTPUT_SCHEMA_NAME = "tender/audit-result.schema.json"
# 仅注册表 key；物理 schema 复用 common/audit-result.json（见下方 register_schema_processor 的
# schema_path=DEFAULT_OUTPUT_SCHEMA_NAME）。刻意不在 .claude/contracts/tender/ 下建同名文件——
# 建了反而会被 resolve_output_schema_path 误当成"真的物理文件"而与共享 schema 产生内容漂移。
```

三个组合函数（每个都是"先/后各插一步 tender-only 逻辑，中间调通用版"——**顺序不是随意选的**，
下面逐个写明为什么这样排能保证与拆分前的合并函数行为完全等价）：

```python
def normalize_tender_result(
    structured_output: StructuredJSON, request_id: str | None = None
) -> StructuredJSON:
    """Tender 组合版 normalize。

    废标/资格否决 verdict 纠偏必须排在通用 normalize **之前**：拆分前的合并函数里，纠偏
    （:409）先于 manual_review_reason 清理（:415，`verdict != manual_review` 才 pop）——若纠偏
    把 verdict 从 manual_review 拍成 rejected，随后的清理才会正确剥掉残留的
    manual_review_reason。倒过来跑，清理会看到"纠偏前"的 verdict，manual_review_reason 不会被剥
    （回归，`test_disqualification_hits_coerce_verdict_to_rejected` 会失败）。可选 plan 丢弃排在
    通用 normalize **之后**：它只操作 `extracted_data.plan`，通用 normalize 的任何一步都不碰
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
    最后一条语句（:193），这里原样保留在最后，顺序零变化。
    """
    structured_output = enrich_audit_decision(structured_output)
    if isinstance(structured_output, dict):
        _finalize_user_explanation(structured_output)
    return structured_output
```

`normalize_tender_result`/`validate_tender_result`/`enrich_tender_result` 里的
`normalize_audit_result`/`_validate_audit_result`/`enrich_audit_decision` 是**通用版**，从
`server.common.output_contracts` import（tender→common，合法下行）。

文件末尾注册（**先不带 `resolve=`**——`resolve_audit_evidence` 此刻仍在
`server/common/evidence_resolution.py`，T3 才搬家；这里先从原路径 import 挂上，T3 只改一行
import 来源，不改这个注册调用本身）：

```python
from server.common.evidence_resolution import resolve_audit_evidence  # noqa: E402（T3 会改成
# from server.tender.evidence import resolve_audit_evidence）

register_schema_processor(
    TENDER_OUTPUT_SCHEMA_NAME,
    normalize=normalize_tender_result,
    validate=validate_tender_result,
    enrich=enrich_tender_result,
    resolve=resolve_audit_evidence,
    schema_path=DEFAULT_OUTPUT_SCHEMA_NAME,
)
```

（此刻 `server/tender/output.py` import `server/common/evidence_resolution.py` 是 tender→common
下行，合法；`evidence_resolution.py` 还没有任何 tender 专属内容搬进 `server/tender/`，所以这一步
本身不违反 layering。）

**同步改 `server/common/output_contracts.py`**：
- 删掉 :30-37 的 `from server.common.tender_output import (...)` 整块。
- `normalize_audit_result`（:388-457）删掉 :403-412（disqualification 纠偏）与 :441-443
  （`_normalize_optional_plan` 调用）两处；其余（元数据盖章/reasons·policy_refs 归一/
  risk_dimensions 归一/evidence_chain 归一/剥编造 policy_refs/禁模型自报 result·conclusion/
  剥未知顶层字段）原样保留——这些都是 `output_contracts.py` 本地定义的通用逻辑，不是 tender
  helper。
- `_validate_audit_result`（:263-312）删掉 :309-311 三行 tender verify 调用；`_cleanse_risk_dimensions`
  （:312，本地通用函数）保留。
- `enrich_audit_decision`（:165-194）删掉 :193 的 `_finalize_user_explanation(structured_output)`
  调用；其余不变。
- :462-470 对 `DEFAULT_OUTPUT_SCHEMA_NAME` 的注册**调用本身不用改**（仍是
  `normalize=normalize_audit_result, validate=_validate_audit_result,
  enrich=enrich_audit_decision, resolve=resolve_audit_evidence`——只是这三个函数名指向的函数体
  已经变薄；`resolve=resolve_audit_evidence` T2 阶段先不动，T3 再拆）。

**其他 import 路径同步修复**（同一 commit，否则 pytest 立刻红）：
- `server/tender/eval.py:34` `from server.common.tender_output import is_real_number` →
  `from server.tender.output import is_real_number`。
- `tests/test_tender_output.py:15` `from server.common import tender_output as to` →
  `from server.tender import output as to`；:25 的子进程 import 字符串
  `"import server.common.tender_output"` → `"import server.tender.output"`。
- `server/tender/__init__.py` 追加（G2/F3 自注册触发点，见 T4 前的说明）：
  ```python
  from server.tender import output  # noqa: F401 — 触发 TENDER_OUTPUT_SCHEMA_NAME 自注册
  ```
  加在文件末尾即可（此时 `output.py` 还没被任何生产入口的 schema_name 实际使用，但**注册**本身
  应从这一步就生效——`server/tender/__init__.py` 是唯一保证"只要有人 import `server.tender` 或
  其任一子模块（runner/worker/eval/evidence），Python 都会先跑本文件"的地方，Python 包初始化
  语义保证这一点，不依赖谁具体 import 了 `output` 子模块）。

**测试迁移（T2 范围，共 41 个测试函数，见下表；不含 T3 的 evidence 相关 2 个）**：

`tests/test_contract_registry.py`（19 个测试函数迁 `TENDER_OUTPUT_SCHEMA_NAME`，其余 19 个留
`DEFAULT_OUTPUT_SCHEMA_NAME` 不动）：

| 迁移到 TENDER（19 个，行号为迁移前） | 留 DEFAULT（19 个，无需改） |
|---|---|
| `test_disqualification_hits_coerce_verdict_to_rejected`(:86) | `test_unregistered_schema_is_passthrough`(:30) |
| `test_unconfirmed_disqualification_does_not_coerce_rejected`(:103) | `test_empty_schema_name_is_passthrough`(:36, parametrized) |
| `test_confirmed_disqualification_still_coerces_rejected`(:128) | `test_empty_schema_name_requires_text_mode`(:46, parametrized) |
| `test_eligibility_fail_coerces_verdict_to_rejected`(:163) | `test_builtin_audit_schema_validates_and_enriches`(:74) |
| `test_no_disqualification_leaves_verdict_untouched`(:176) | `test_builtin_audit_schema_rejects_bad_verdict`(:81) |
| `test_falsy_disqualification_does_not_coerce`(:189, parametrized ×8) | `test_string_reasons_coerced_to_list_not_rejected`(:146) |
| `test_eligibility_fail_case_insensitive_coerces`(:242, parametrized ×3) | `test_missing_envelope_fields_defaulted_not_rejected`(:202) |
| `test_malformed_optional_plan_dropped_not_rejected`(:418) | `test_evidence_chain_extra_fields_normalized_not_rejected`(:218) |
| `test_scoring_consistency_rejects_score_over_max`(:445) | `test_gate_rejects_missing_required_field`(:259) |
| `test_scoring_consistency_allows_null_score`(:453) | `test_gate_rejects_additional_property`(:267) |
| `test_scoring_consistency_allows_valid_score`(:464) | `test_gate_rejects_wrong_type`(:273) |
| `test_plan_present_valid_passes`(:475) | `test_gate_rejects_bad_enum_value`(:279) |
| `test_plan_present_malformed_dropped_not_rejected`(:483) | `test_gate_rejects_approved_without_policy_refs`(:288) |
| `test_no_plan_skips_plan_check`(:490) | `test_gate_rejects_rejected_without_policy_refs`(:294) |
| `test_r4_deduction_scored_partial_without_hits_warns`(:533) | `test_manual_review_allowed_with_empty_policy_refs`(:302) |
| `test_r4_deduction_full_score_without_hits_no_warn`(:554) | `test_rule_ref_check_on_by_default_rejects_unknown_ref`(:316) |
| `test_r4_deduction_with_hits_no_completeness_warn`(:575) | `test_rule_ref_check_disabled_allows_unknown_ref`(:328) |
| `test_r4_additive_scored_above_base_without_awards_warns`(:597) | `test_rule_ref_check_on_rejects_fabricated_ref`(:339) |
| `test_r4_manual_review_item_no_completeness_warn`(:618) | `test_mixed_policy_refs_strips_fabricated_keeps_real`(:400) |
| | `test_rule_ref_check_on_but_no_rules_loaded_skips`(:432) |
| | `test_register_new_schema_takes_effect_...`(:496)／`test_processor_dataclass_defaults_are_none`(:520)——机制测试，不涉及 schema key |
| | `test_enrich_adds_policy_refs_detail`(:353)／`test_enrich_no_policy_refs_detail_when_empty`(:375)／`test_load_rule_details_real_rules_if_present`(:381)／`test_rule_ref_check_on_allows_real_ref`(:389)——直调 `_oc.enrich_audit_decision`/`_oc._load_rule_details`，不经 `apply_schema_semantics`，无需改 |

改法：文件顶部 `from server.common.contract import (DEFAULT_OUTPUT_SCHEMA_NAME, ...)` 旁加
`from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME`；上表左列每个测试体内把
`apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, ...)` 的第一个参数换成
`TENDER_OUTPUT_SCHEMA_NAME`（纯文本替换，断言内容不变——这是本设计反复强调的"行为保真"：38 处
断言中的 19 处只换 key，不改期望值）。

`tests/test_tender_criteria_flow.py`：文件顶部同样加 `TENDER_OUTPUT_SCHEMA_NAME` import；**22 个
真实调用点**（行号：268/282/292/364/399/428/457/480/544/567/588/638/686/704/730/755/778/903/
915/927/939/958）全部把 `DEFAULT_OUTPUT_SCHEMA_NAME` 换成 `TENDER_OUTPUT_SCHEMA_NAME`（这个文件
标题就是"Tender 评标改造验收测试"，除了 9 个纯 `jsonschema.validate(..., load_output_schema(CRITERIA_SCHEMA))`
的 criteria 形校验测试（跟 audit-result schema key 无关，:129-258）和 2 个直调
`oc.enrich_audit_decision` 的 D0 跨域防污染测试（:330-356，本就该继续测**通用版**——它们的意图正是
证明"expense 数据不受 tender 逻辑影响"，通用版天然满足）之外，其余全部涉及 tender 行为，全部迁）。
`test_audit_schema_whitelist_no_drift`（:803-814）不涉及 apply_schema_semantics，不用改。

**layering 确认（不新增测试，是判断依据，写入验收标准）**：`tests/test_layering.py::
test_common_does_not_import_feature_or_upper_layers`（forbidden 元组已含 `"server.tender"`）在
本 commit 完成后必须仍然绿——它已经是一般化的 rglob 扫描（`server/common/*.py` 任何文件都会被
扫到），本 commit 完成后 `output_contracts.py` 不再 import 任何 `server.tender.*`，该测试**无需
新增代码**即可正确断言"没有 common→tender 反向边"。不额外写一个功能重复的守卫测试（铁律
[反过度工程]：已有测试已完整覆盖这个不变量，重复写一个只测同一件事的新测试是冗余）。

**commit 2，pytest 全绿（含上述全部迁移的测试文件）。**

### T3 — F5 evidence 拆分

**新增 `server/common/corpus.py`**（通用语料解析 + 匹配打分原语，从
`server/common/evidence_resolution.py` 搬）：

| 搬入 corpus.py | 说明 |
|---|---|
| `_f`/`_i`（:51-63） | 通用 env float/int 读取，两侧都要用 |
| `_resolve_threshold`/`_absent_threshold`（:67-72） | **注意**：这两个虽然在原文件里紧挨着
tender-only 的 `_enabled`/`_downgrade_enabled` 写在配置区，但它们只被 `_classify`（下面确认留
common）调用——必须跟着 `_classify` 一起留 common，不能想当然按"配置区都是 tender 的"分给
evidence.py，否则 `_classify` 会反向依赖 tender 模块 |
| `_kgram`/`_max_corpus_chars`（:83-90） | 只被 `existence_ratio` 调用，留 common |
| `_page_window`（:79-81） | **同上注意**：只被 `page_status` 调用，`page_status` 留 common，`_page_window` 必须跟着留 common |
| `_TIER_RE`/`_FILE_RE`/`_PAGE_RE`/`_tier_of`（:96-109） | 底稿切段的通用正则/推断 |
| `normalize_text`（:112-126） | 通用规范化 |
| `_FILE_HEAD_SPLIT_RE`/`_parse_file_head`（:129-141） | 文件头解析 |
| `_normalize_filename`（:144-148） | 文件名规范化 |
| `parse_corpus`（:151-204） | 底稿切段 |
| `class CorpusIndex`（:207-264） | file-level 索引 |
| `_cap_corpus`（:270-275） | 语料截断 |
| `existence_ratio`（:278-296） | 存在性匹配度 |
| `page_status`（:299-325） | file/page 精度细化 |
| `_PAGE_IN_SOURCE_RE`/`parse_source`（:330-340） | 出处解析 |
| `_classify`（:346-352） | 双阈值三档分类 |

**新增 `server/tender/evidence.py`**（tender 专属评分证据回查闸，从
`server/common/evidence_resolution.py` 搬，import corpus 原语 `from server.common.corpus import
(CorpusIndex, existence_ratio, normalize_text, page_status, parse_corpus, parse_source, _classify)`）：

| 搬入 evidence.py | 说明 |
|---|---|
| `_enabled`/`_downgrade_enabled`/`_annotate_resolved`（:33-48） | resolve 闸开关，仅本模块用 |
| `_min_quote_chars`（:75-77） | 仅 `_check_one` 用 |
| `_DOWNGRADE_NOTE`/`_LOW_CLARITY_NOTE`（:449-450） | 降级标注文案 |
| `_check_one`（:355-395） | 单条出处回查 |
| `_hit_moves_score`（:398-411） | 命中是否移动得分 |
| `_check_hits`（:414-446） | 评分项 hits 批量回查 |
| `_downgrade_scoring_item`（:453-475） | scored→manual_review 幂等迁移 |
| `_flag_low_clarity_sources`（:478-497） | 低置信文件点名标注 |
| `resolve_audit_evidence`（:500-643） | resolve hook 入口（内部 :629 惰性 `from
server.common.output_contracts import enrich_audit_decision` **不用改**——那是通用 enrich，仍在
common/，路径没变，只是调用方所在文件从 common 挪到了 tender，import 目标字符串本身不变） |

删除 `server/common/evidence_resolution.py`（内容已完全分流到上述两个新文件）。

**`server/tender/output.py` 改一行 import**：
`from server.common.evidence_resolution import resolve_audit_evidence` →
`from server.tender.evidence import resolve_audit_evidence`（注册调用本身 :`register_schema_processor(
TENDER_OUTPUT_SCHEMA_NAME, ..., resolve=resolve_audit_evidence, ...)` 不变）。

**`server/common/output_contracts.py` 去掉 resolve 挂载**：:460 的
`from server.common.evidence_resolution import resolve_audit_evidence` 整行删除；:462-470 对
`DEFAULT_OUTPUT_SCHEMA_NAME` 的注册调用去掉 `resolve=resolve_audit_evidence,` 这一个关键字参数
（`normalize`/`validate`/`enrich` 三个不变）。**这是"expense/audit 结论不再跑 evidence-resolution
闸"的落地点**——反正 expense/audit 从不透传 `evidence_source`（`apply_schema_semantics` 的
`resolve` 分支本就 `if evidence_source and processor.resolve is not None`，双重条件），删掉这个
kwarg 对 expense/audit 现有测试**零行为影响**，纯粹是让"共享层不再牵一根从没用过的线"。

**测试迁移**：
- `tests/test_evidence_resolution.py`：
  - :11-17 的 import 块拆成两行：
    `from server.common.corpus import (CorpusIndex, existence_ratio, normalize_text, parse_corpus, parse_source)`
    + `from server.tender.evidence import resolve_audit_evidence`。
  - :621-624 的 `from server.common.evidence_resolution import (_normalize_filename, _parse_file_head)`
    → `from server.common.corpus import (_normalize_filename, _parse_file_head)`。
  - `test_pipeline_no_evidence_source_skips_resolution`（:590-598）与
    `test_pipeline_with_evidence_source_runs_resolution`（:601-614）：两处局部 `from
    server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME, apply_schema_semantics` 改成额外
    import `from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME`，调用改用
    `TENDER_OUTPUT_SCHEMA_NAME`（这两个测试的 payload 本就是 tender 载荷——`_full_audit_result()`
    的 `reviewed_by: "tender-evaluator"` + `scoring` 字段——且断言的正是 evidence-resolution 降级
    行为，DEFAULT 拆分后不再挂 resolve hook，必须迁）。
  - 其余测试都直调 `resolve_audit_evidence(...)`（不经 `apply_schema_semantics`），只需import路径改，行为不变。
- `tests/test_boq.py:167-171`：`from server.common.evidence_resolution import (CorpusIndex,
  existence_ratio, normalize_text, parse_corpus)` → `from server.common.corpus import (...)`（同名）。
- `tests/test_ocr_pipeline.py:686-690`：同上。

**commit 3，pytest 全绿。**

### T4 — 生产调用点切换到 `TENDER_OUTPUT_SCHEMA_NAME`

- `server/tender/runner.py`：:23 `from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME`
  → `from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME`；:223
  `schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,` → `schema_name=TENDER_OUTPUT_SCHEMA_NAME,`。
  （`server/tender/worker.py` 不用改——它只调用 `runner.run_tender_evaluation`，从不自己传
  `schema_name`，D2 design 的任务清单把 worker.py 也列进"call-site 更新"是不准确的，本设计订正：
  worker.py 本身零改动。）
- `server/cli.py`：新增顶部 import `from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME`；
  :212（`tender_evaluate_json` 内 `run_command_json(..., schema_name=DEFAULT_OUTPUT_SCHEMA_NAME)`）
  改 `schema_name=TENDER_OUTPUT_SCHEMA_NAME`。:169（`audit_json` 命令）的
  `schema_name=DEFAULT_OUTPUT_SCHEMA_NAME` **不动**（那是 audit 域，非 tender）。这是本设计
  唯一一处允许"common/output.py 之外的模块 import server.tender"的新增点——`cli.py` 属于 app
  层（`test_layering.py` 没有约束 app 层不能 import features，这本来就合法），且这正是 G2 要求
  的"CLI 路径必须真实 import server.tender.output 才会触发自注册"的落地方式。

**测试迁移**：
- `tests/test_cli_tender_evaluate.py`：:18 `EVAL_SCHEMA = "common/audit-result.schema.json"` 改成
  `from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME as EVAL_SCHEMA`（保留常量名
  `EVAL_SCHEMA` 不变，只换来源，最小化 diff）；:89/:93 断言不用改（比较的是 `EVAL_SCHEMA` 变量，
  变量值自动跟着换）。
- `tests/test_tender_routes.py`：:23 同样把 `EVAL_SCHEMA = "common/audit-result.schema.json"`
  改成 `from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME as EVAL_SCHEMA`。此文件里
  `EVAL_SCHEMA` 同时驱动一处真实断言（`test_worker_forwards_to_evaluate_bid_and_persists`，约
  :225-263，`assert calls["schema_name"] == EVAL_SCHEMA`，是 monkeypatch `runner.run_command_json`
  后从真实 `worker→runner` 调用链里捕获的值，T4 切换后必须匹配新 key）与三处纯 fixture 构造
  （:464/:503/:551，直接调 `archive_result_payload(schema_name=EVAL_SCHEMA, ...)` 模拟"已归档的
  历史结论"，不断言该值，改不改都不影响这三个测试通过，但统一用常量而非裸字面量更贴近"这确实是
  一条 tender 结论"的语义，顺手改掉不算范围膨胀）。
- 核实过、**确认无需改动**的字面量用例（同样含 `"common/audit-result.schema.json"`，但都只是
  构造 mock 返回值/fixture，不断言该值 == 生产实际传参，行为不受 T4 影响）：
  `tests/test_tender_read_layer.py`（:34 等 5 处，`_fake_meta`/mock 签名占位）、
  `tests/test_codex_p2_rework_fixes.py`（:69，同类 `_fake_meta`）、
  `tests/test_tender_compare.py`（:68，`_archive_bid` 测试 helper，compare 域用独立的
  `COMPARE_SCHEMA_NAME`，不受本次影响）、`tests/test_domain_profile.py`（:38，expense 域
  `DomainProfile.result_contract` fixture，与 tender 无关）。

**commit 4，pytest 全绿。**

### T5 — 自注册回归测试（G2/F3：隔离子进程，不被同进程内其它测试的 import 顺序掩盖）

在 `tests/test_tender_output.py` 追加两个子进程测试（照抄已有的
`test_tender_output_independently_importable` 模式，:18-29）：

```python
def test_package_import_registers_tender_schema():
    """G2/F3: importing the server.tender package (any submodule) must self-register
    TENDER_OUTPUT_SCHEMA_NAME — proven in a fresh interpreter so no other test's import
    order can accidentally pre-warm the registry."""
    code = (
        "import server.tender\n"
        "from server.common.contract import _SCHEMA_PROCESSORS\n"
        "from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME\n"
        "assert TENDER_OUTPUT_SCHEMA_NAME in _SCHEMA_PROCESSORS, "
        "'server.tender import did not self-register the tender schema processor'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_cli_import_registers_tender_schema():
    """G2: the CLI entrypoint specifically must trigger self-registration — this is the
    exact gap Round-2 critic flagged (cli.py→command_adapter→json_bridge→contract had zero
    server.tender import). Importing server.cli in a fresh interpreter must be enough."""
    code = (
        "import server.cli\n"
        "from server.common.contract import _SCHEMA_PROCESSORS\n"
        "from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME\n"
        "assert TENDER_OUTPUT_SCHEMA_NAME in _SCHEMA_PROCESSORS, "
        "'importing server.cli did not self-register the tender schema processor'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

第二个测试若在 T4 之前跑会红（`cli.py` 那时还没 import `server.tender.output`）——这正是它要
守住的回归；顺序上 T5 必须排在 T4 之后。

**commit 5，pytest 全绿。**

### T6 — 收尾核验

- `uv run pytest -q` 全绿（基线 834 + 本 sprint 新增的别名机制单测 + 2 个自注册子进程测试 —
  净增约 3-5 条，其余都是"迁移"不是"新增"）。
- `uv run ruff check .` 干净。
- 人工确认（不新增代码）：`tests/test_layering.py::test_common_does_not_import_feature_or_upper_layers`
  绿 = "expense/audit 结论证明不再跑 tender 校验" + "无 common→tender 反向边"双重证据（该测试是
  text-level import 扫描，`server/common/output_contracts.py`/`server/common/corpus.py` 里任何一行
  `from server.tender...`/`import server.tender...` 都会被它抓到；本 sprint 结束时两个文件都不会
  再有这样的 import，测试自然绿，不需要专门再造一个断言同一件事的新测试）。
- `git grep -n "common.tender_output\|common\.evidence_resolution"` 应该只剩注释/历史文档引用，
  不再有 `import` 语句命中（收尾自检命令，不是新增机制）。
- polish / architecture 归档更新（`.ai_state/architecture/`）留给下游 polish stage（本 design 只
  覆盖 impl 前置的 design-gate，铁律[门禁即律法] 的 architecture 更新义务由 polish skill 承接，
  不在本 sprint 的 T1-T6 内重复处理）。

## 影响范围

| 类别 | 文件 |
|---|---|
| 机制层改动 | `server/common/contract.py`（`SchemaProcessor`/`register_schema_processor`/`apply_schema_semantics`/`build_output_format` 四处） |
| 拆分/瘦身 | `server/common/output_contracts.py`（删 6-helper import + 3 函数体各删 1-3 行 tender 步骤 + 删 resolve 挂载） |
| 新建（tender 专属） | `server/tender/output.py`（= 旧 `server/common/tender_output.py` + 组合函数 + 注册）、`server/tender/evidence.py`（= 旧 `evidence_resolution.py` 的 tender 半） |
| 新建（common 通用） | `server/common/corpus.py`（= 旧 `evidence_resolution.py` 的通用半） |
| 删除 | `server/common/tender_output.py`、`server/common/evidence_resolution.py` |
| 生产调用点 | `server/tender/runner.py`（import + :223）、`server/cli.py`（新 import + :212）、`server/tender/__init__.py`（自注册 import）、`server/tender/eval.py:34` |
| 测试迁移（schema key） | `tests/test_contract_registry.py`（19/38）、`tests/test_tender_criteria_flow.py`（22/23）、`tests/test_evidence_resolution.py`（2/4） |
| 测试迁移（import 路径） | `tests/test_tender_output.py`、`tests/test_evidence_resolution.py`、`tests/test_boq.py`、`tests/test_ocr_pipeline.py` |
| 测试迁移（schema 常量来源） | `tests/test_cli_tender_evaluate.py`、`tests/test_tender_routes.py` |
| 新增测试 | `server/common/contract.py` 别名机制单测（T1）、`tests/test_tender_output.py` 两个子进程自注册测试（T5） |
| 核实无需改动 | `tests/test_core_pure.py`（15 处 DEFAULT，全通用）、`tests/test_tender_contracts.py`（只读物理 schema 文件，与注册表 key 无关）、`tests/test_tender_read_layer.py`/`test_codex_p2_rework_fixes.py`/`test_tender_compare.py`/`test_domain_profile.py`（字面量不参与断言） |
| 不动 | `server/audit/runner.py`、`server/ops/diagnostics.py`、`server/tender/compare_worker.py`（独立 `COMPARE_SCHEMA_NAME`）、`server/tender/worker.py`、`.claude/contracts/**`（零新增/零修改物理 schema 文件） |

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 3 函数拆分顺序错误导致行为漂移（如 manual_review_reason 残留、evidence_chain 归一顺序变化） | T2 的三个组合函数文档逐条写明"为什么这样排"，每条都能对应回原合并函数的行号顺序；19+22+2=43 个迁移测试断言的是**原始预期值**，不是重新设计的新预期——顺序错了会被这些测试当场抓住 |
| `build_output_format` 未同步 schema_path 解析，T4 切换后 tender-evaluate-json 生产端报 "schema not found" | T1 把 `apply_schema_semantics` 和 `build_output_format` 统一走同一个 `_resolve_physical_schema_name`，且 T1 自带的别名机制单测直接断言两者解析到同一物理 schema，先于 T4 落地 |
| 自注册静默失效（谁都没 import `server.tender.output`，`apply_schema_semantics` 悄悄退化成裸 JSON 校验，不报错） | T5 两个隔离子进程测试分别钉住"import 包"和"import CLI 入口"两条路径，且第二个测试若排在 T4 之前会真实失败（验证了测试本身有效，不是摆设） |
| resolve hook 从 DEFAULT 摘除后 expense/audit 现有 evidence-resolution 相关测试回归 | 已核实 `apply_schema_semantics` 的 resolve 分支本就双重门禁（`evidence_source` 非空 **且** `processor.resolve is not None`）；expense/audit 调用链从不透传 `evidence_source`（`server/audit/runner.py` 未见 `evidence_source=` 传参），删除 kwarg 对其零影响，且全量 pytest 会覆盖 |
| 测试迁移遗漏（"38 处"之外还有隐藏的 DEFAULT-key tender 测试） | 已用 `grep -rn "DEFAULT_OUTPUT_SCHEMA_NAME" tests/*.py` 对全部 9 个命中文件逐一读源码分类（不是只看 grep 计数），结论写入本设计影响范围表；`test_core_pure.py`/`test_tender_contracts.py` 等已核实排除，理由各自写明，不是"看起来像就跳过" |
| 红区多 commit 之间存在"设计上暂时不一致"的窗口（如 T2-T4 之间生产入口仍传 DEFAULT，tender 校验短暂不生效） | 这些中间态只存在于 worktree 内部提交序列中，merge 前不会被部署；每个 commit 仍要求 pytest 全绿（因为该 commit 自身的测试断言已同步迁移），窗口期风险仅是"设计意图未完全落地"而非"红色/挂起的测试"，符合 D2 design 里 F8 红区纪律的既定含义 |
| ruff/layering 对新文件（corpus.py/output.py/evidence.py）漏检 | T2/T3 完成后跑 `uv run pytest -q`（含 `test_layering.py`）+ `uv run ruff check .`；两者都是已有的、按目录 rglob 的通用检查，新文件天然被覆盖，不需要新增专门检查这两个新文件的测试 |

## 验收标准

- [ ] T1：`SchemaProcessor.schema_path` 字段 + `register_schema_processor(schema_path=...)` +
      `_resolve_physical_schema_name` 落地；`apply_schema_semantics` 与 `build_output_format`
      都走该 helper；别名机制单测绿；`uv run pytest -q` 全绿；单独 commit。
- [ ] T2：`server/tender/output.py` 落地（6 helper + `TENDER_OUTPUT_SCHEMA_NAME` + 3 个组合函数 +
      注册，先不带 `resolve=`）；`server/common/output_contracts.py` 三函数瘦身完成，顶部 6-helper
      import 已删；`server/tender/__init__.py` 追加自注册 import；`eval.py`/`test_tender_output.py`
      import 路径已改；`tests/test_contract_registry.py` 19 个函数 + `tests/test_tender_criteria_flow.py`
      22 个调用点已迁 `TENDER_OUTPUT_SCHEMA_NAME`，断言内容不变；`uv run pytest -q` 全绿；单独 commit。
- [ ] T3：`server/common/corpus.py`（通用原语，含易错的 `_page_window`/`_resolve_threshold`/
      `_absent_threshold` 归属校验——跟随 `page_status`/`_classify` 留 common，不是简单按"配置区"
      切）+ `server/tender/evidence.py`（resolve hook + scoring 助手）落地；
      `server/common/evidence_resolution.py` 已删；`output.py` 的 resolve import 已改；
      `output_contracts.py` 的 DEFAULT 注册已去掉 `resolve=` kwarg；
      `test_evidence_resolution.py`/`test_boq.py`/`test_ocr_pipeline.py` import 路径已改，
      `test_evidence_resolution.py` 2 个测试已迁 `TENDER_OUTPUT_SCHEMA_NAME`；`uv run pytest -q`
      全绿；单独 commit。
- [ ] T4：`runner.py`（import + :223）、`cli.py`（新 import + :212）已切换到
      `TENDER_OUTPUT_SCHEMA_NAME`；`test_cli_tender_evaluate.py`/`test_tender_routes.py` 的
      `EVAL_SCHEMA` 已改来源；`uv run pytest -q` 全绿；单独 commit。
- [ ] T5：两个隔离子进程自注册测试（包级 + CLI 级）落地且绿；`uv run pytest -q` 全绿；单独 commit。
- [ ] T6：`uv run pytest -q` 全绿（≥834，新增净测试数已知）；`uv run ruff check .` 干净；
      `tests/test_layering.py::test_common_does_not_import_feature_or_upper_layers` 绿（零新增代码
      验证"无 common→tender 反向边"）；`git grep` 确认无残留旧 import 路径。
- [ ] 行为保真：43 个迁移测试（T2 的 19+22，T3 的 2）断言值**逐一未改**，只换了 `apply_schema_semantics`
      第一个参数——这是"tender 行为在新 key 下与拆分前一致"的证据，而不是"重新设计后凑巧过了"。
- [ ] 分层：`server/common/**` 任意文件对 `server/tender/**` 的 import 计数 = 0（`test_layering.py`
      现有断言 + `git grep -rn "from server.tender\|import server.tender" server/common/` 应无命中）。

## 备选（放弃）

- **新建 byte-identical `.claude/contracts/tender/audit-result.schema.json`**（Round-1 F1 的选项
  b）：会产生两份内容相同的 schema 文件，未来共享 schema 改一处忘改另一处即产生漂移，需要额外的
  漂移守卫测试（仿 `_AUDIT_SCHEMA_TOP_FIELDS`）。`schema_path` 别名机制零文件复制、零漂移风险，
  已在 Round-1 拍板选择，本设计延续，不重新展开。
- **F5 整体搬迁不拆分**（Round-1 F5 选项 b，"记技术债"）：会让 `test_ocr_pipeline.py`/`test_boq.py`
  反向依赖 `server.tender.evidence`（ocr 是比 tender 更底层的服务层，语义上不应该耦合 tender 包），
  且 D7（结构化检索）会需要复用这些通用原语，届时又要二次搬迁。用户已在 D2 阶段拍板选项 a（拆分），
  本设计按拍板执行。
- **`_resolve_physical_schema_name` 只修 `apply_schema_semantics`，不修 `build_output_format`**
  （沿用 Round-1 F1 原始范围）：已在本设计"背景"一节证明这会导致 T4 落地后 tender-evaluate-json
  生产报错且无测试能提前捕获，属于必须补的范围，不是可选项，故不再单列为备选。
- **T2/T3 拆得更细（如把"移动 tender_output.py"和"改 output_contracts.py 三函数"分成两个
  commit）**：已在设计推演阶段验证——中间态会让 `server/common/output_contracts.py` 要么仍 import
  尚未瘦身的 tender helper（违反"共享层不再依赖 tender"的目标状态），要么需要一次性的临时反向
  import 作为过渡胶水（用完即删的一次性代码，不产生长期价值，纯粹增加 diff 噪音）。两条路径都不如
  把"移动 + 拆分 + 注册"揉进同一个原子 commit 干净，故按当前 T2 粒度执行。

---

## Round 1 · Critic 修订应答（2026-07-18，opus critic → NEEDS_REVISION，主 agent 落实）

> opus 独立复核（含实测 monkeypatch 验证）判 NEEDS_REVISION：1 P0（F1 行为保真漏洞）+ 1 P2（F2 文档完整性）。
> 三个待核实点**全 CONFIRMED**：build_output_format 确为第二物理 schema 解析点且无漏第三处（diagnostics/
> credit_api/PLAN_SCHEMA 都不会被别名）；测试迁移计数精确（38/22/2）；F5 边界逐函数 28 定义比对完全正确、
> 无反向依赖。**本节为 impl 前必补，generator 以本节为准（覆盖上文 T3 中"import 路径没变不用改"的表述）。**

**F1 [P0] → resolve_audit_evidence 二次 enrich 必须用 tender 组合版（修 + 补 TDD 守卫）**
- 根因（critic 实测确认）：`evidence_resolution.py:629`（T3 迁往 `server/tender/evidence.py` 的同段）里
  `resolve_audit_evidence` 在 evidence 降级触发 verdict `approved→manual_review` 后，惰性
  `from server.common.output_contracts import enrich_audit_decision` 重算 result/conclusion。但 T2 已把
  **通用版** `enrich_audit_decision` 瘦身（删 `_finalize_user_explanation`）——原 T3 只判"import 路径字符串
  没变、不用改"，漏了"被 import 的函数体行为已被 T2 改变"。后果：拆分后 verdict 已翻 manual_review、评分已降
  null，但 explanation 仍是陈旧"…合计 40 分"，**静默失真呈现给人工复核**。全量 pytest 绿也测不出
  （`test_pipeline_with_evidence_source_runs_resolution` 断言 evidence/scoring/verdict/result，**不断言 explanation**）。
- **修复（T3 强制）**：`server/tender/evidence.py` 的 `resolve_audit_evidence` 二次 enrich 改惰性
  `from server.tender.output import enrich_tender_result`（tender 组合版，含 `_finalize_user_explanation`；
  同样惰性 import 断模块加载期环，不新增环）。**不得**用 common 的瘦身通用版。
- **新增回归测试（T3/T5 强制，TDD 守卫，非走过场）**：断言"evidence 降级触发 verdict 翻转后 explanation 含
  刷新后的『得分小结：…』（反映降级后的 score=null/合计变化）"。generator 须**先在拆分前基线写此测试并确认
  当前通过**（保真基线），**再证明：拆分后若二次 enrich 误用通用瘦身版 → 此测试失败；改用
  `enrich_tender_result` → 转绿**。这条即 F1 保真的守卫。

**F2 [P2] → 测试迁移"无需改动"表补一行**
- `tests/test_tender_info_extraction.py:830/904` 各有一处 `schema_name="common/audit-result.schema.json"`
  字面量（在 `_fake_meta()` 构造 AgentRunMeta 替身里），与已核实免动的 `test_tender_read_layer.py`/
  `test_codex_p2_rework_fixes.py` 同类 inert 占位、**从不被断言**，免动。含该字面量的文件实为 7 个（critic
  grep 核实），本设计迁移分类补齐这一条，坐实完整性 claim。

**门禁状态**：除 F1 外全部经 opus 独立核验为真。F1 修复具体、可 TDD 守卫；主 agent 判**修订后 ready 进 impl**
（红区 worktree 强制：generator + `isolation:worktree`，T1-T6 每步单 commit + pytest 绿再进下一，**F1 回归测试
为 T3 硬门**）。impl 后照常走 review 三件套 + evaluator，F1 保真是 spec-compliance 重点核查项。
