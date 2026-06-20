---
name: common-memory-query
description: Use when 需要从 knowledge/memory/{domain}/ 中检索可复用的案例/异常/复核记忆，并作为辅助证据参与当前判断
---

# 通用记忆查询

## 三层记忆（优先级，G4）

判断时记忆按从属优先级使用，**绝不让案例记忆自我强化错误**：

1. **制度记忆（权威 / ground truth）** = `knowledge/{domain}/*.rules.json`。带版本号、人工策展。这是判决依据。
2. **案例记忆（情节 / 仅建议）** = `knowledge/memory/{domain}/`。带 `source_trace` 回链 + 置信衰减 + `decided_under_rule_version`。**召回只当线索，判决前必须拿当前制度规则复检**。
3. **工作记忆（短时）** = 本次任务内抽取的事实，ephemeral，不跨案件。

## 使用方法

1. 根据业务域定位 `knowledge/memory/{domain}/`。
2. 读取记忆资产时，优先筛选：
   - `category`
   - `recommended_verdict`
   - `manual_review_reason`
   - `tags`
3. 返回的结果至少包含：
   - `memory_id`
   - `title`
   - `summary`
   - `recommended_verdict`
   - `policy_refs`
   - `source_trace.request_id`
   - `source_trace.result_file`

## 使用原则

- 记忆是辅助证据，不是主规则来源。
- 记忆不能替代结构化规则；若记忆与当前规则冲突，以结构化规则为准。
- 当记忆只描述一次性环境噪音、路径错误、网络失败时，不应引用为业务依据。
- 如果命中高价值记忆，应把它作为补充证据加入 evidence chain，而不是单独覆盖当前结论。

### 规则版本复检与衰减（G4）

- **规则版本复检**：案例记忆的 `decided_under_rule_version` 若**低于**当前制度规则文件的版本，说明它是按旧规则下的结论——**必须用当前规则重新核对**，不一致则不引用（视为陈旧）。
- **陈旧标记**：记忆带 `superseded_by`（被某条新记忆取代）或 `valid_until` 已过期 → 不再作为建议。
- **置信衰减**：越久远 / 命中次数越少的案例记忆，权重越低；低置信记忆只作弱线索，不左右终局判断。
- **人工否决先例（高置信负样本）**：来自人工否决的案例记忆置信高，但仍**只提示风险、不自动判**，由当前规则与证据做终局判断。

## 输出建议

- 匹配记忆时，说明为什么当前案件与该记忆相似
- 记忆未命中时，明确返回空结果，不要编造“类似案例”
