---
name: common-memory-query
description: Use when 需要从 knowledge/memory/{domain}/ 中检索可复用的案例/异常/复核记忆，并作为辅助证据参与当前判断
---

# 通用记忆查询

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

## 输出建议

- 匹配记忆时，说明为什么当前案件与该记忆相似
- 记忆未命中时，明确返回空结果，不要编造“类似案例”
