# Audit Result Chinese Display Design

## Goal

把审核结果输出契约升级为“结构化数据 + 审核意见”双层模型：

- 内部仍保留 `approved / rejected / manual_review`
- 对外继续保留完整结构化数据，供页面和后续流程对接
- 对外强制新增 `result`、`conclusion`、`explanation`
- 所有审核意见必须使用中文表达，不能再出现英文结论或英文理由

## Scope

本轮只处理审核结果的输出契约和写出前校验，不改动具体报销规则内容，也不改动 Python 侧业务判断逻辑。

涉及文件：

- `.claude/contracts/common/audit-result.schema.json`
- `.claude/skills/common/result-format/SKILL.md`
- `.claude/hooks/check-before-write.py`
- `tests/test_bootstrap.py`

按需小改：

- `.claude/agents/expense/auditor.md`

不涉及：

- `knowledge/expense/*.json`
- `expense-audit` 子技能的具体规则判定逻辑
- HTTP 上传或多材料编排入口

## Context

当前输出结果存在三个问题：

1. `verdict` 使用英文三态，适合内部流转，但不适合直接展示给财务或业务用户。
2. 当前结果里虽然已经有 `extracted_data`、`reasons`、`policy_refs`、`evidence_chain`，但没有单独、稳定的前端展示字段来表达“审核意见”。
3. `reasons` 与 `evidence_chain` 没有被强制要求为中文，Claude 可能输出英文意见。
4. `manual_review` 虽然语义上不是“不合规”，但当前没有固定中文展示口径，也没有强制解释“为什么系统不能自动放行”。

## Design

### 1. 保留内部三态，不在核心判定层降维

内部审核状态继续使用：

- `approved`
- `rejected`
- `manual_review`

原因：

- Python 侧、skills、hooks、测试已经围绕三态建立约束。
- `manual_review` 与 `rejected` 的语义不同，不能在内部直接压扁为二态。
- 对外展示再映射成 `true/false`，可以兼顾机器处理和人工阅读。

### 2. 保留结构化数据，同时新增审核意见字段

现有结构化字段必须继续保留，至少包括：

- `claim_id`
- `verdict`
- `reasons`
- `policy_refs`
- `risk_score`
- `extracted_data`
- `evidence_chain`
- `reviewed_by`
- `timestamp`

在此基础上，统一结果 schema 再新增以下审核意见字段：

- `result`: `true | false`
- `conclusion`: `合规 | 不合规 | 待人工复核`
- `explanation`: 中文长句说明

这意味着页面对接时可以同时拿到：

- 机器可消费的结构化字段
- 人可直接阅读的中文审核结论

skill 不允许在两者之间二选一；必须同时产出。

映射规则固定为：

- `approved -> result=true, conclusion=合规`
- `rejected -> result=false, conclusion=不合规`
- `manual_review -> result=false, conclusion=待人工复核`

### 3. explanation 必须引用制度依据并解释结论

`explanation` 不是简单摘要，而是面向财务复核人员的说明性结论。

约束如下：

- 必须使用中文
- 必须说明“根据什么规定判断什么事项”
- 应优先引用 `policy_refs` 对应的本地规则条款
- 在条款不完整但仍需人工复核时，也要明确写出“现有材料不足以自动判定”的原因

推荐句式：

- `approved`: `根据《...》第...条，结合已提交的...材料，判断该事项合规，依据是...。`
- `rejected`: `根据《...》第...条，结合已提交的...材料，判断该事项不合规，原因是...。`
- `manual_review`: `根据《...》第...条，结合已提交的...材料，当前无法自动判定该事项合规，原因是...，还需补充...。`

### 4. manual_review 的中文结论固定为“待人工复核”

`manual_review` 的中文展示必须固定为 `待人工复核`，不能写成 `不合规`。

同时必须在 `explanation` 中说明至少一类阻断原因：

- 缺少关键附件
- 关键字段缺失
- 证据冲突
- 规则未覆盖
- OCR/扫描质量不足

如果缺少补充说明，只输出“待人工复核”是不合格结果，因为财务仍然需要重新读材料才能知道为什么系统没法放行。

### 5. reasons / evidence_chain 也要收口为中文

为了避免结果中出现“中文结论 + 英文细项”的混杂输出，本轮进一步约束：

- `reasons[]` 必须为中文
- `evidence_chain[].finding` 必须为中文
- `evidence_chain[].conclusion` 必须为中文

`policy_refs` 保持 `rule_id` 原样，不翻译。

### 6. 写出前 hook 增加中文展示校验

`check-before-write.py` 应在写结果文件前做最小校验：

- 现有结构化字段仍然必须存在，不能因为新增审核意见而删掉原始结构化输出
- 新字段 `result`、`conclusion`、`explanation` 必须存在
- `conclusion` 必须与 `verdict` 一致
- `manual_review` 时，`conclusion` 必须是 `待人工复核`
- `explanation` 不能为空

本轮不在 hook 中做复杂中文语言学判断，只做结构与映射一致性校验。

## Output Contract

目标输出结构如下：

```json
{
  "claim_id": "",
  "verdict": "approved | rejected | manual_review",
  "result": true,
  "conclusion": "合规 | 不合规 | 待人工复核",
  "explanation": "根据《费用报销管理制度》相关条款，结合已提交材料，判断该事项合规。",
  "reasons": [],
  "policy_refs": [],
  "risk_score": 0,
  "extracted_data": {},
  "evidence_chain": [],
  "reviewed_by": "",
  "timestamp": ""
}
```

其中：

- `extracted_data`、`reasons`、`policy_refs`、`evidence_chain` 继续服务于页面结构化展示、筛选、详情展开和二次处理
- `result`、`conclusion`、`explanation` 服务于首页摘要、卡片结论和人工复核提示

## Acceptance

1. Claude 返回结果时，结构化数据和审核意见字段同时存在，不能缺任一侧。
2. Claude 输出的审核意见默认是中文，不再只返回英文 `manual_review` 或英文 `reasons`。
3. 对外总是给出 `result=true/false`、中文 `conclusion` 和 `explanation`。
4. `manual_review` 固定展示为 `待人工复核`，并明确写出不能自动放行的原因。
5. 内部仍保留 `approved / rejected / manual_review`，不破坏现有三态流转。
6. hook 会拦截缺失中文展示字段、缺失结构化字段或映射不一致的结果。

## Risks

1. 现有 API/CLI 消费方如果假设结果只包含旧字段，需要同步兼容新增字段。
2. 页面如果直接绑定旧字段名，需要确认是继续使用 `extracted_data` 还是额外映射成前端 view model。
3. 仅靠 skill 约束仍可能出现个别英文短语，因此 hook 和测试需要一起收口。
4. `policy_refs` 是规则 ID，不是自然语言条款文本；`explanation` 的制度依据表述仍依赖 Claude 按 skill 提示正确组织。
