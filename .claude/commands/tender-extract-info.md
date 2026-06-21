---
description: 招标信息抽取：从招标文件 OCR 底稿一次性抽取评分标准（criteria）与招标基本信息（tender_info），聚焦招标文件，不读投标，不评分
allowed-tools: Read, Glob
---

读取招标文件 OCR 底稿（服务端已注入为确定性文本块），**在当前会话内一次性完成招标信息抽取并直接输出单个 JSON 对象**。

## 核心约束

- **只处理招标文件**，不读投标文件、不评分、不给分、不写结论。
- **优先使用服务端注入的 OCR 底稿上下文**（已由 `[` 标注页锚点并重点还原评分表格）；仅在底稿不完整时 `Read` 原文件补充。
- **直读即权威**：招标文件载明的内容直读解析，不凭训练记忆补充或臆造任何评分标准。
- **定位不到 → 降级不臆造**：找不到评标办法/评分标准时，`criteria` 各项标注 `tag: manual`、`score_mode: manual`，写明缺什么；不得现场编造规则。
- **输出只有一个 JSON 对象**，首字符是 `{`、末字符是 `}`。分析/思考只能写在 `<think></think>` 内，`</think>` 之后只准有这一个 JSON 对象。

---

## 执行步骤（单趟，无需 spawn 子 agent）

### 步骤 1 — 定位评标办法/评分标准

**完全复用 tender-evaluate.md S1 的定位指令**（已注入的 OCR 底稿优先）：

- 找含「序号 / 评分点名称 / 评审标准 / 最高分 / 最低分」或「评分项 / 分值 / 权重」的评分表。
- 章节标题含「开标 / 评标 / 评审 / 资格审查 / 商务技术标 / 报价标」即是；**不限于《评标办法》字样**。
- **关键排除**：绝对不要把「考核方案 / 绩效考核 / 季度考核 / 履约考核 / KPI」等中标后阶段的表当评分表——它们同样列分值，但属履约阶段，误取会导致整套 criteria 取错。
- 定位后自检：各项 `max` 之和是否 = `total_max`；对不上 → 回去重定位。

### 步骤 2 — 抽取 criteria（评分标准）

按 `.claude/contracts/tender/criteria.schema.json` v2 规范完整解析评分标准：

- `source_ref`：评标办法在本招标文件的实际出处（文件 + 章节/标题 + 页）。
- `method`：综合评估法 / 经评审的最低投标价法 / 其他。
- `total_max`：满分合计。
- `items[]`：每项除 `{item, max, scoring_rule, source_ref, tag}` 外，**必须判定 `score_mode` 并提取对应结构化细则**：
  - `deduction`（满分扣减）→ 逐条 `deductions[]`：`{condition, points, unit, max_times, max_deduct, source_quote, source_ref}`。**扣分项全摘，不留到评标临场猜。**
  - `banded`（档次给分）→ `bands[]`：`{level, points, criteria, source_quote}`。
  - `additive`（基础分+加分）→ `base` + `awards[]`：`{condition, points, cap, source_quote}`。
  - `formula`（公式分）→ `formula`（原文）+ `formula_spec`：`{expression, variables[{name, source, value, unit, ref}], rounding, cap}`；变量 `source` 按白名单标 tender_constant/bid_component/cross_bid 等。
  - `pass_fail` / `manual`：客观通过或主观/现场/外部不可判定。
- `rejection_rules[]`：废标/资格否决条款逐条提取，`{id, condition, source_quote, source_ref}`。
- **`tag` 可判定性标签（与 score_mode 正交）**：全可依单份投标文件判定 → `scored`；含 cross_bid/external_data/live_event → 对应 manual tag。

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
