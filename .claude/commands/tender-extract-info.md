---
description: 招标信息抽取：从招标文件 OCR 底稿一次性抽取资格审查规则、评分标准（criteria）与招标基本信息（tender_info），聚焦招标文件，不读投标，不评分
allowed-tools: Read, Glob
---

读取招标文件 OCR 底稿（服务端已注入为确定性文本块），**在当前会话内一次性完成招标信息抽取并直接输出单个 JSON 对象**。

## 核心约束

- **只处理招标文件**，不读投标文件、不评分、不给分、不写结论。
- **优先使用服务端注入的 OCR 底稿上下文**（已由 `[` 标注页锚点并重点还原评分表格）；仅在底稿不完整时 `Read` 原文件补充。
- **直读即权威**：招标文件载明的内容直读解析，不凭训练记忆补充或臆造任何评分标准。
- **资格审查是最高优先级招标项**：凡招标文件出现「资格审查 / 资格性审查 / 资格评审 / 初步评审 / 符合性审查 / 响应性评审」等章节，须抽进 `criteria.eligibility_rules[]`，与评分 `items[]` 并列；它不计入 `total_max`，但评审时先于评分运行。
- **定位不到 → 降级不臆造**：找不到评标办法/评分标准时，`criteria` 各项标注 `tag: manual`、`score_mode: manual`，写明缺什么；不得现场编造规则。
- **输出只有一个 JSON 对象**，首字符是 `{`、末字符是 `}`。分析/思考只能写在 `<think></think>` 内，`</think>` 之后只准有这一个 JSON 对象。

---

## 执行步骤（单趟，无需 spawn 子 agent）

### 步骤 1 — 定位资格审查与评标办法/评分标准

`Read .claude/skills/tender-eval/references/s1-locate-criteria.md`（已注入的 OCR 底稿优先），按其中的定位优先级、关键排除与自检执行。

### 步骤 2 — 抽取 criteria（资格审查 + 评分标准）

按 `.claude/contracts/tender/criteria.schema.json` 当前规范完整解析项目规则：

- `source_ref`：评标办法在本招标文件的实际出处（文件 + 章节/标题 + 页）。
- `method`：综合评估法 / 经评审的最低投标价法 / 其他。
- `total_max`：满分合计。
- `eligibility_rules[]`：资格审查/资格评审/初步评审规则，逐条提取 `{id, check, requirement, evidence_required, stage, priority:"highest", external_data, source_quote, source_ref}`。**这些规则与 `items[]` 并列，但不计入总分；后续评审必须先运行它们。**外部网站/主体库/动态监管等上下文缺失时只标 `external_data:true`，不得在抽取阶段判失败。
- `items[]`：每项除 `{item, max, scoring_rule, source_ref, tag, category}` 外，**必须判定 `score_mode` 并提取对应结构化细则**（`category` = 该项在评标办法里的所属类目/章节原名，照标书原文，如 商务标 / 技术标 / 价格 / 信用 / 服务；标书分几类标几类、不套死三类，资格审查走 `eligibility_rules[]` 不重复；仅供报告动态分栏，不影响判分）：
  - `deduction`（满分扣减）→ 逐条 `deductions[]`：`{condition, points, unit, max_times, max_deduct, source_quote, source_ref}`。**扣分项全摘，不留到评标临场猜。**
  - `banded`（档次给分）→ `bands[]`：`{level, points, criteria, source_quote}`。
  - `additive`（基础分+加分）→ `base` + `awards[]`：`{condition, points, cap, source_quote}`。
  - `formula`（公式分）→ `formula`（原文）+ `formula_spec`：`{expression, variables[{name, source, value, unit, ref}], rounding, cap}`；变量 `source` 按白名单标 tender_constant/bid_component/cross_bid 等。
  - `pass_fail` / `manual`：客观通过或主观/现场/外部不可判定。
- `rejection_rules[]`：废标/资格否决条款逐条提取，`{id, condition, source_quote, source_ref}`。
- **`tag` 可判定性标签（与 score_mode 正交）**：全可依单份投标文件判定 → `scored`；含 cross_bid/external_data/live_event → 对应 manual tag。
- **`max:null` 是窄例外**：只有招标文件确实未给出该人工项分值，且该项同时满足 `score_mode:"manual"` 与 `tag!="scored"` 时才可输出 `max:null`。`scored/null`、非 manual/null 均属无效结果；已载明分值不得改成 null。整份 criteria 至少保留一个数值 `max` 项。

### 步骤 3 — 抽取 tender_info（招标基本信息）

按 `.claude/contracts/tender/tender-info.schema.json` 最大努力抽取（全 optional，抽到几填几，抽不到的字段省略）：

- `tender_no`：招标编号（封面/标题/招标公告处）。
- `project_name`：项目名称全称。
- `tenderee`：招标人/采购人名称。
- `control_price`：控制价/最高限价/预算，保留原文单位字符串。
- `method`：评标方法（与 criteria.method 一致）。
- `funding_hint`：资金来源提示（财政资金/国有资金/社会资本等），非必填。

---

## 输出规范

**输出仅一个 JSON 对象**，结构如下：

```json
{
  "criteria": { ...符合 criteria.schema.json... },
  "tender_info": { ...符合 tender-info.schema.json，仅包含抽取到的字段... }
}
```

**JSON 合法性（极重要）**：
- 字符串值内引用项目名/项目号/评分项时，**一律用中文引号「」或『』**，**严禁在字符串值里用半角双引号 `"`**（会破坏 JSON 解析）；确需则转义为 `\"`。
- 分析/思考只能写在 `<think></think>` 内；`</think>` 之后只准有这一个 JSON 对象，禁止任何英文散文或列表。
- 若定位不到评标办法，`criteria` 仍须有 `source_ref`、`method`（填「其他」或说明）、`total_max: 0`、`items: []`（可附一条 `score_mode: manual` 占位项说明原因）；不得返回不合法 JSON 或省略 criteria 对象。

参数: $ARGUMENTS
用法: /tender-extract-info data/submissions/acme/tender/tp-xxxx/req-xxxx
