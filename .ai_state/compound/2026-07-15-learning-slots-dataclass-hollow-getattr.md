# Learning · slots dataclass 上的 getattr 兜底是永久空壳，"向前兼容"要对照类型定义核验

- **日期**: 2026-07-15
- **场景**: D1 M1 补丁（eval 报告运维指标维度）。generator 用
  `getattr(meta, "retry_count", None)` 从 `AgentRunMeta` 取重试数，并声称
  "meta 未来补上该字段会自动被捡起"（向前兼容）。

## 事实

`AgentRunMeta` 是 `@dataclass(slots=True)`（server/common/agent_bridge.py:137）。
slots 类**不可能被外部附加未声明属性**（setattr 直接 AttributeError），所以：

1. 该 getattr 永远走兜底 → retry_count **永久 None**；
2. "未来自动捡起"的前提（有人往实例上挂字段）在 slots 下不成立——只有改 dataclass
   定义本身才行，而那正是补丁刻意回避的改动。

结果：design 明文的"契约重试次数"基线维度（S7 配套问题②）看似落地实为空壳，
且 811 测试全绿——因为测试 mock 的 meta 也没这字段，断言的就是 None。

## 教训

1. **getattr/hasattr 兜底出现在 review 面前时，先查目标类是否 slots/frozen**——
   兜底分支若在当前代码库中永远为真，它不是兼容层，是未实现的需求穿了兼容的衣服。
2. **"测试全绿"证明不了维度落地**：TDD 若从空壳假设出发（断言 None），红绿循环
   照样成立。评分/指标类需求要至少一条"非默认值路径"断言（如"2 次失败第 3 次
   成功 → retry_count==2"）才算真落地。
3. subagent 以"不动共享合同"为由收窄范围时，主 agent 应核验：需求数据的**产生点**
   在不在本 sprint 自有代码里（本例重试循环就在新建的 runner.py:218，attempt 现成）。
   范围收窄若使需求变空壳，正确动作是批准最小范围修订，不是收下空壳。

## 关联

- [[2026-06-26-learning-cross-review-catches-latent-bugs]]（复核抓潜伏缺陷的又一例）
- sprints/2026-07-02-eval-tender-scaffold/reviews/pass1.md M1 处置记录
