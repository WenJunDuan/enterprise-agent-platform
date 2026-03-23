# 费控闭环设计

本文是当前仓库中关于报销域的最新拆分文档，定义费控场景从事前审批到事后报销的完整闭环。基础留档、部署样例与早期统一草案仍保留在 [enterprise-agent-dev-guide.md](enterprise-agent-dev-guide.md)。

## 当前定位

- 本文描述的是目标流程；仓库中可能已经存在 `.claude/`、`knowledge/`、`data/`、`server/` 的基础骨架，但具体业务配置与实现仍待填充。
- 本文优先级高于基础留档中较早版本的报销域示例；后续如出现冲突，以本文为准。
- 本轮重点是费控闭环，不展开容器化和许可问题；相关背景继续沿用现有结论与后续实现确认。

## 业务闭环范围

当前报销域不再只看“报销单本身”，而是按“事前审批 + 事中票据 + 事后报销”的完整费控链路审查。

| 阶段     | 动作               | 核心判定                                       |
| -------- | ------------------ | ---------------------------------------------- |
| 事前     | 出差申请、招待申请 | 是否符合申请条件、预算额度、审批层级           |
| 事中票据 | 发票上传、行程变更 | 发票形式合规、抬头合规、票据类目匹配           |
| 事后     | 报销提交           | 事前申请与事后报销交叉比对、金额偏差、政策合规 |

关键变化是第三阶段不再做“孤立报销审核”，而是必须回查事前申请，判断“申请过的事项”和“实际花费的事项”是否一致。

## 当前优先场景

- 差旅报销：覆盖出差申请、行程、交通、住宿、餐补的闭环审核。
- 招待报销：覆盖招待申请、消费票据、人员比例、频次与标准的闭环审核。
- 普通报销：继续保留简化规则查询和金额校验路径，但优先级低于差旅与招待。

## 目标目录变化

以下仅列出相对现有设计新增或变化明显的部分。

```text
.claude/
├── agents/
│   └── expense/
│       ├── extractor.md
│       ├── auditor.md
│       └── reviewer.md
│
├── skills/
│   ├── rule-init/SKILL.md
│   ├── rule-query/SKILL.md
│   ├── amount-validate/SKILL.md
│   ├── anomaly-detect/SKILL.md
│   ├── evidence-chain/SKILL.md
│   ├── result-format/SKILL.md
│   ├── invoice-parse/SKILL.md
│   ├── pre-approval-match/SKILL.md
│   ├── travel-compliance/SKILL.md
│   ├── entertainment-compliance/SKILL.md
│   └── budget-check/SKILL.md
│
knowledge/
└── expense/
    ├── travel.rules.json
    ├── meal.rules.json
    ├── thresholds.json
    ├── entertainment.rules.json
    ├── invoice.rules.json
    └── budget-limits.json

data/
├── claims/
├── invoices/
└── pre-approvals/
```

## 新增技能职责

| Skill                      | 职责                       | 何时调用                 |
| -------------------------- | -------------------------- | ------------------------ |
| `invoice-parse`            | 发票/收据解析与形式校验    | 所有带票据附件的报销     |
| `pre-approval-match`       | 事前审批与事后报销交叉比对 | 差旅、招待等需预申请场景 |
| `travel-compliance`        | 差旅全链路合规校验         | 差旅报销                 |
| `entertainment-compliance` | 招待费合规校验             | 招待报销                 |
| `budget-check`             | 部门/项目/个人预算占用校验 | 事前申请和事后报销       |

## Skill 详细定义

### `invoice-parse`

```markdown
---
name: invoice-parse
description: 解析上传的发票或收据，提取结构化字段并校验发票基本合规性（抬头、税号、日期、金额）
---

# 发票解析与校验

## 触发条件

当收到发票文件（JSON/图片OCR结果）需要提取结构化数据并做基础校验时使用。

## 执行步骤

1. 读取 data/invoices/ 下的发票文件
2. 提取结构化字段：
   - invoice_no: 发票号码
   - invoice_type: 增值税专用/普通/电子/定额
   - seller: 销方名称
   - buyer: 购方名称（公司抬头）
   - buyer_tax_no: 购方税号
   - amount: 不含税金额
   - tax: 税额
   - total: 价税合计
   - date: 开票日期
   - items: 明细行（品名、数量、单价）
3. 读取 knowledge/expense/invoice.rules.json 获取校验规则
4. 基础校验：
   - 抬头是否匹配公司注册名称
   - 税号是否正确
   - 开票日期是否在报销有效期内（通常90天）
   - 发票类型是否被允许
   - 金额各项是否算术一致（amount + tax == total）

## 输出

{
"invoice_no": "",
"parsed_data": {},
"validations": [
{"check": "buyer_match", "pass": true/false, "detail": ""},
{"check": "date_valid", "pass": true/false, "detail": ""},
{"check": "amount_consistent", "pass": true/false, "detail": ""}
],
"overall_valid": true/false
}

## 注意

本 skill 不判定发票对应的费用是否合规（那是 auditor 的事），只负责发票本身的形式校验。
```

### `pre-approval-match`

```markdown
---
name: pre-approval-match
description: 将事后报销单与事前审批单（出差申请/招待申请）进行交叉匹配，检测偏差并判定是否在允许范围内
---

# 事前审批↔事后报销匹配

## 触发条件

当报销单关联了事前审批单号时，用此 skill 做交叉比对。

## 执行步骤

1. 从报销单中提取 pre_approval_id（事前审批单号）
2. 读取 data/pre-approvals/{pre_approval_id}.json 获取事前申请内容
3. 读取 knowledge/expense/thresholds.json 获取允许偏差范围
4. 逐维度比对：

   | 维度     | 事前申请字段         | 事后报销字段        | 偏差判定               |
   | -------- | -------------------- | ------------------- | ---------------------- |
   | 金额     | approved_amount      | actual_amount       | 超支比例是否在阈值内   |
   | 日期     | planned_dates        | actual_dates        | 是否有未申请的额外天数 |
   | 目的地   | planned_destination  | actual_destination  | 是否一致               |
   | 同行人   | planned_participants | actual_participants | 人数是否变化           |
   | 费用类目 | approved_categories  | actual_categories   | 是否有未审批的类目     |

5. 对每个偏差项判定：
   - 无偏差 → pass
   - 偏差在允许范围内（如金额超支 < 10%）→ pass_with_note
   - 偏差超出范围 → deviation，需要说明原因
   - 无事前申请 → missing_approval

## 输出

{
"pre_approval_id": "",
"match_result": "full_match | partial_match | mismatch | no_approval",
"deviations": [
{
"dimension": "amount",
"approved": 5000,
"actual": 5800,
"deviation_pct": 16,
"within_threshold": false,
"detail": "超支800元(16%)，阈值10%"
}
],
"requires_explanation": true/false
}
```

### `travel-compliance`

```markdown
---
name: travel-compliance
description: 综合校验出差报销的全流程合规性：事前申请→行程→住宿→交通→补贴的完整链路
---

# 出差报销综合合规校验

## 触发条件

当报销类别为差旅且需要做全链路合规判定时使用。

## 执行步骤

1. 读取 knowledge/expense/travel.rules.json 获取差旅政策
2. 按以下维度逐项校验：

### 事前申请校验

- 是否存在已审批的出差申请（调用 pre-approval-match skill）
- 申请是否在出发前提交（不允许事后补申请，除非规则允许）

### 行程合规

- 出差天数是否与申请一致
- 目的地是否与申请一致
- 是否存在绕路（A城出差却报销B城酒店）

### 住宿标准

- 按申请人职级匹配住宿标准上限
- 是否超标（读 thresholds.json 中 lodging 部分）
- 同城是否有住宿（通常不允许）

### 交通标准

- 交通方式是否符合职级（如普通员工不允许商务舱）
- 市内交通是否合理（单日交通费上限）

### 出差补贴

- 补贴天数是否与实际出差天数一致
- 补贴标准是否按目的地城市等级计算

## 输出

{
"travel_id": "",
"checks": [
{"category": "pre_approval", "pass": true/false, "detail": ""},
{"category": "itinerary", "pass": true/false, "detail": ""},
{"category": "lodging", "pass": true/false, "detail": ""},
{"category": "transport", "pass": true/false, "detail": ""},
{"category": "allowance", "pass": true/false, "detail": ""}
],
"overall": "compliant | non_compliant | needs_review"
}
```

### `entertainment-compliance`

```markdown
---
name: entertainment-compliance
description: 校验招待费报销的合规性：事前申请审批、招待标准、陪餐人数比例、频次限制
---

# 招待费合规校验

## 触发条件

当报销类别为业务招待/宴请且需要合规判定时使用。

## 执行步骤

1. 读取 knowledge/expense/entertainment.rules.json 获取招待政策
2. 按以下维度校验：

### 事前审批

- 是否有已审批的招待申请（调用 pre-approval-match skill）
- 招待事由是否合理（纯内部聚餐通常不允许走招待费）

### 标准校验

- 人均金额是否超标（按客户级别区分标准）
- 酒水占比是否超限
- 是否包含违禁消费项（如高档会所、KTV 等，从 rules 中读取黑名单）

### 比例与频次

- 公司陪餐人员 vs 客户人数比例是否合规
- 同一客户本月招待次数是否超限
- 同一申请人本月招待总额是否超限

### 附件完整性

- 是否有招待申请单
- 是否有消费明细（非笼统“餐费”发票）
- 是否有参与人员名单

## 输出

{
"entertainment_id": "",
"checks": [
{"category": "pre_approval", "pass": true/false, "detail": ""},
{"category": "standard", "pass": true/false, "detail": ""},
{"category": "ratio_frequency", "pass": true/false, "detail": ""},
{"category": "attachments", "pass": true/false, "detail": ""}
],
"overall": "compliant | non_compliant | needs_review"
}
```

### `budget-check`

```markdown
---
name: budget-check
description: 校验本次费用是否会导致部门/项目预算超支，读取budget-limits.json进行累计计算
---

# 预算额度校验

## 触发条件

当需要判断本次报销是否会超出预算额度时使用。适用于事前申请审批和事后报销两个阶段。

## 执行步骤

1. 读取 knowledge/expense/budget-limits.json 获取预算配置
2. 确定预算维度：
   - 部门级：department_id → 部门年度/季度/月度预算
   - 项目级：project_id → 项目总预算
   - 个人级：applicant_id → 个人月度报销上限
3. 计算已使用预算（读取 output/results/ 中已审批的历史记录）
4. 计算本次金额占剩余预算的比例

## 输出

{
"budget_scope": "department | project | personal",
"budget_id": "",
"total_budget": 100000,
"used_budget": 85000,
"this_claim": 8000,
"remaining_after": 7000,
"utilization_pct": 93,
"over_budget": false,
"warning": "预算使用率将达93%，接近上限"
}
```

## 更新后的 `expense-auditor`

```markdown
---
name: expense-auditor
description: 费控综合审核agent。根据报销类别调度不同的skill组合，完成事前事后交叉比对和全流程合规判定。不含任何业务规则。
tools: Read, Glob, Skill, Task
skills:
  - rule-query
  - invoice-parse
  - pre-approval-match
  - travel-compliance
  - entertainment-compliance
  - budget-check
  - amount-validate
  - anomaly-detect
  - evidence-chain
  - result-format
---

你是费控综合审核员。你不知道任何报销政策——所有规则通过 skill 从 knowledge/ 动态获取。

## 审核流程（按报销类别分支）

### 通用步骤（所有类别都执行）

1. 使用 invoice-parse skill 校验所有发票的形式合规性
2. 使用 budget-check skill 校验预算额度
3. 使用 anomaly-detect skill 检查异常模式

### 差旅报销

4. 使用 pre-approval-match skill 比对出差申请
5. 使用 travel-compliance skill 做全链路合规校验
6. 使用 amount-validate skill 逐项金额校验

### 招待报销

4. 使用 pre-approval-match skill 比对招待申请
5. 使用 entertainment-compliance skill 做招待合规校验

### 普通报销（办公用品、交通等）

4. 使用 rule-query skill 获取对应类别规则
5. 使用 amount-validate skill 金额校验

### 汇总

6. 使用 evidence-chain skill 组装完整证据链
7. 使用 result-format skill 输出标准化结果

## 判定逻辑

- 所有 skill 返回 pass → approved
- 任一 skill 返回 fail 且理由明确 → rejected
- 存在 deviation/needs_review/missing_approval → manual_review
- 多个维度同时异常 → rejected 且标记 high_risk

## 禁止事项

- 禁止用训练知识判定，一切从 knowledge/ 读取
- 禁止编造规则
- 无事前申请时不要自动放行，标记 manual_review
```

## 规则与数据样例

### `knowledge/expense/entertainment.rules.json`

```json
{
  "domain": "expense",
  "category": "entertainment",
  "version": "2024-v2",
  "effective_date": "2024-06-01",
  "rules": [
    {
      "rule_id": "expense.entertainment.001",
      "description": "业务招待须提前提交招待申请并获得部门负责人审批",
      "conditions": {
        "required_docs": ["招待申请单", "消费明细", "参与人员名单"]
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "业务招待须事前填写《招待申请单》，经部门负责人审批后方可执行。"
    },
    {
      "rule_id": "expense.entertainment.002",
      "description": "招待标准：普通客户人均不超过200元，重要客户人均不超过500元",
      "conditions": {
        "max_amount": 200,
        "applicable_roles": ["normal_client"],
        "frequency_limit": { "count": 3, "period": "monthly" }
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "普通客户招待标准为人均200元以内，每月同一客户招待不超过3次。"
    },
    {
      "rule_id": "expense.entertainment.003",
      "description": "公司陪餐人员与客户人数比例不得超过1:1",
      "conditions": {
        "max_company_ratio": 1.0
      },
      "action": "reject",
      "priority": 2,
      "confidence": "high",
      "original_text": "招待用餐时，公司参与人员人数不得超过受邀客户人数。"
    },
    {
      "rule_id": "expense.entertainment.004",
      "description": "禁止在高档会所、KTV、高尔夫球场等场所进行业务招待",
      "conditions": {
        "venue_blacklist": ["KTV", "高尔夫", "会所", "夜总会", "足浴"]
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "严禁在高消费娱乐场所进行业务招待活动。"
    },
    {
      "rule_id": "expense.entertainment.005",
      "description": "酒水费用不得超过餐费总额的30%",
      "conditions": {
        "max_alcohol_ratio": 0.3
      },
      "action": "escalate",
      "priority": 2,
      "confidence": "medium",
      "original_text": "招待用餐中酒水消费应控制在合理范围内。",
      "notes": "原文说'合理范围'较模糊，参照行业惯例设定为30%，confidence标记为medium"
    }
  ]
}
```

### `data/pre-approvals/PA-2024-0157.json`

```json
{
  "approval_id": "PA-2024-0157",
  "type": "travel",
  "applicant": {
    "id": "EMP-0042",
    "name": "张三",
    "department": "销售部",
    "role": "staff"
  },
  "status": "approved",
  "approved_by": "李四",
  "approved_at": "2024-10-15T09:30:00",
  "details": {
    "purpose": "拜访深圳客户ABC科技",
    "destination": "深圳",
    "planned_dates": ["2024-10-20", "2024-10-21", "2024-10-22"],
    "planned_participants": ["张三"],
    "approved_categories": ["交通", "住宿", "市内交通", "餐补"],
    "approved_amount": 5000,
    "budget_source": "销售部Q4差旅预算"
  }
}
```

### `data/claims/EXP-2024-0312.json`

```json
{
  "claim_id": "EXP-2024-0312",
  "pre_approval_id": "PA-2024-0157",
  "applicant_id": "EMP-0042",
  "submit_date": "2024-10-25",
  "category": "travel",
  "items": [
    {
      "type": "交通",
      "description": "北京→深圳 高铁二等座",
      "amount": 950,
      "date": "2024-10-20",
      "invoice_ref": "INV-001"
    },
    {
      "type": "住宿",
      "description": "深圳XX酒店 2晚",
      "amount": 1160,
      "date": "2024-10-20",
      "invoice_ref": "INV-002"
    },
    {
      "type": "住宿",
      "description": "深圳XX酒店 额外1晚（客户临时加会）",
      "amount": 580,
      "date": "2024-10-22",
      "invoice_ref": "INV-003"
    },
    {
      "type": "市内交通",
      "description": "出租车/地铁",
      "amount": 320,
      "date": "2024-10-20",
      "invoice_ref": "INV-004"
    },
    {
      "type": "餐补",
      "description": "3天出差餐补",
      "amount": 300,
      "date": "2024-10-22"
    }
  ],
  "total_amount": 3310,
  "attachments": ["INV-001", "INV-002", "INV-003", "INV-004"]
}
```

## 预期审核结果示例

对上面的差旅报销样例，`pre-approval-match` 应识别出：

- 总金额 `3310` 未超过申请金额 `5000`，预算维度可通过。
- 住宿多出 `1` 晚，导致实际行程比申请多 `1` 天。
- 偏差属于可解释但不能自动放行的情形。

因此 `expense-auditor` 的预期结论应为：

- `match_result = partial_match`
- `requires_explanation = true`
- `final verdict = manual_review`
- 理由聚焦“行程天数偏差需申请人说明”，而不是直接拒绝

## 设计原则回落到实现

- 每个 skill 只做一件事，方便独立替换与测试。
- `expense-auditor` 只负责编排，不直接硬编码政策。
- 所有判定都应回链到 `knowledge/expense/*.json` 中的规则或数据比对结果。
- `missing_approval`、`deviation`、`needs_review` 不自动放行，统一进入 `manual_review`。
