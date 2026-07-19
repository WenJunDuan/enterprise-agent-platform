---
name: tender-eval
description: Use when 评标、招投标评分、投标文件合规审查，需要基于本地 tender 两层规则评分并输出可追溯结论
---

# 评标总控

## 本地规则与评分标准

- **通则层国家法规**（稳定、跨项目，作**法律底座**）：
  - `knowledge/tender/evalmethod.rules.json` ←《评标委员会和评标方法暂行规定》（发改委12号令）
  - `knowledge/tender/regulation.rules.json` ←《招标投标法实施条例》
  - 由 `/init-rules <法规源文件> tender` 生成；管废标 / 资格 / 一致性 / 程序的法定依据，**不含**具体项目的分值权重。
- **会话项目规则（criteria）**（每标一份，**不预建**）：本项目资格审查规则与评分项 / 满分 / 评分规则就在**它自己的招标文件载明的资格审查、初步评审和评标办法**里，评标时由 `/tender-evaluate` 在 S1 按 `references/s1-locate-criteria.md` **定位并直读招标文件**解析为 `extracted_data.criteria`（`eligibility_rules[]` + 评分 `items[]`，对齐 `.claude/contracts/tender/criteria.schema.json`），随结论持久化作本次会话规则。资格审查是与评分项并列的最高优先级招标项，先于评分运行，不计入满分。

> 通则层 `rule_id` 形如 `tender_evalmethod_001` / `tender_regulation_003`（下划线连接），可作 `policy_refs`。criteria 来自招标文件评标办法、**无 `rule_id`**，其标准与命中写入 `evidence_chain`。

## 执行顺序（一次性，少往返）

1. 优先消费 `tender-extractor` 输出的结构化事实；若当前只有原始材料，不要直接猜字段，先回到提取阶段。
2. `Read` 招标文件，按 `references/s1-locate-criteria.md` **定位其中的资格审查/初步评审与评标办法（评分标准）**，直读解析为 `extracted_data.criteria`（招标文件**没写的标准不臆造补充**）；并读通则层 `evalmethod` / `regulation` 法规作法律底座，读取顶层 `source_path` / `source_version` 作为追溯。
3. 读取 `knowledge/memory/tender/` 中的相似案例 / 异常记忆作为 `memory:` 辅助证据（不能替代结构化规则）。
4. **先对照 `criteria.eligibility_rules[]` 运行资格审查**，写入 `extracted_data.eligibility_checks`；再对照 `criteria.items[]` 逐评分项判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, basis}`。承重 `policy_refs` 只引通则层真实 `rule_id`，criteria 命中写 `evidence_chain`；一次产出契约结果。

## 不可判定项 → manual_review（绝不判 0）

评分项命中以下任一标签时，该项 `status: "manual_review"`、`score: null`，并使整体 `verdict` 至少为 `manual_review`：

- `requires_live_event`：现场环节，如项目负责人答辩、现场演示——投标文件里没有，不代表得 0。
- `requires_external_data`：外部数据，如企业信用评价（来自政府 / 行业公示表），不在投标文件内。
- `requires_cross_bid_comparison`：需横向比较，如**依基准价 / 评标均价 / 最低价的价格分**（须对所有有效投标报价统一计算）。**例外（G5 固定限价类）**：依招标文件**已载明固定限价**算的价格分（公式变量全为招标常量 + 本家报价，如「每低于最高限价 1% 得 1 分」）是可单家算的 `tag:scored` / `score_mode:formula`，**不走本横比 manual**——以 `/tender-evaluate` S3 + `formula_spec` 为准。

## 资格审查最高优先级

- `criteria.eligibility_rules[]` 与评分 `items[]` 并列，是先运行的招标项，不计入 `total_max`。
- 资格审查输出 `extracted_data.eligibility_checks`。证据明确不满足才 `fail`；外部信用、主体库、动态监管、截图读不清等无法在当前上下文确认时写 `manual`，不得直接判失败。
- 资格失败优先决定 `verdict=rejected`，但不得把后续评分项一律清零；评分明细仍按招标文件规则保留。
- 综合意见：资格不通过时直接说明按废标处理；资格通过时再汇总已有分数和待补充信息。无论整单是否废标，明细都继续展示。

> 原则：文档里"找不到证据" ≠ "客观得 0 分"。把不可判定项判 0 是范畴错误，会系统性低估投标人，且对方无从申辩。这类项一律 `manual_review`，并写清需要什么（现场记录 / 外部评价表 / 全部投标报价）。

## 低清页证据复核：先重识别再判分

- 底稿中某页扫描件、印章或表格读不清时，先定位对应的真实文件绝对路径和【第N页】锚点，调用 ocr-page 按页重识别，再用重识别文本补充当前评分项的证据与结论。
- 调用形态只能是：uv run python .claude/skills/ocr-page/ocr.py <绝对文件路径> [--pages N 或 N-M] [--seal]。文件必须是当前评标目录内的真实文件；不要拼接 shell 运算符或改写路径。
- 重识别输出中的【第N页】是证据定位的权威页锚，引用时原样保留其中的 N，不使用文档印刷页码替代。
- OCR 失败、结果仍与原材料矛盾或无法确认时，降为 manual_review 并说明缺口；不得据此判 0 分，也不得臆造页码或内容。

## 降级规则（输出 manual_review）

出现以下任一情况时，停止给出确定性通过结论：

- 未命中结构化规则（`rule_gap`）
- 关键字段缺失：投标报价、拟派项目负责人、业绩项目经理、资格证明
- 拟派项目负责人与业绩 / 承诺书中的姓名不一致或归属冲突（`data_conflict`）
- 多份材料互相冲突且无法唯一解释
- 缺招标文件 / 招标文件里定位不到资格审查或评标办法（无法取本项目 `criteria`），或通则层法规存在覆盖缺口（后者可用 `system-rule-init` 补齐）
