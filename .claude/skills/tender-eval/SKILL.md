---
name: tender-eval
description: Use when 评标、招投标评分、投标文件合规审查，需要基于本地 tender 两层规则评分并输出可追溯结论
---

# 评标总控

> **判 0 / 人工复核的裁决口径只有一处**：`/tender-evaluate` S3 的「判分仲裁决策表」。本文件只讲规则从哪来与执行顺序，**不复述**裁决细则——两处各写一份必然漂移。

## 本地规则与评分标准（两层）

- **通则层国家法规**（稳定、跨项目，作**法律底座**）：《评标委员会和评标方法暂行规定》（发改委12号令）与《招标投标法实施条例》，由 `/init-rules <法规源文件> tender` 生成，**评标时由服务端注入上下文**（`=== 通则层国家法规 ===` 节，勿再 Read）。管废标 / 资格 / 一致性 / 程序的法定依据，**不含**具体项目的分值权重。
- **会话项目规则（criteria）**（每标一份，**不预建**）：本项目资格审查规则与评分项 / 满分 / 评分规则就在**它自己的招标文件载明的资格审查、初步评审和评标办法**里，评标时由 `/tender-evaluate` S1 从注入的招标文件底稿定位并解析为 `extracted_data.criteria`（`eligibility_rules[]` + 评分 `items[]`，对齐 `.claude/contracts/tender/criteria.schema.json`），随结论持久化作本次会话规则。资格审查是与评分项并列的**最高优先级**招标项，先于评分运行，不计入满分。

> 通则层 `rule_id` 形如 `tender_evalmethod_001` / `tender_regulation_003`（下划线连接），可作 `policy_refs`。criteria 来自招标文件评标办法、**无 `rule_id`**，其标准与命中写入 `evidence_chain`。

## 执行顺序（一次性，不往返）

1. 优先消费 `tender-extractor` 输出的结构化事实；若当前只有原始材料，不要直接猜字段，先回到提取阶段。
2. 从注入的招标文件底稿里**定位资格审查/初步评审与评标办法（评分标准）**，直读解析为 `extracted_data.criteria`（招标文件**没写的标准不臆造补充**）；法律底座与相似案例记忆均已由服务端注入，追溯直接引各法规文件顶层 `source_path` / `source_version`。
3. **先对照 `criteria.eligibility_rules[]` 运行资格审查**，写入 `extracted_data.eligibility_checks`；再对照 `criteria.items[]` 逐评分项判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, basis}`。承重 `policy_refs` 只引通则层真实 `rule_id`，criteria 命中写 `evidence_chain`；一次产出契约结果。
4. 每项判 0 还是人工复核，**逐条走决策表**，不在本文件另立例外。
