# A-003 自审：审后业务记忆沉淀层

## 结论

- VERDICT: PASS

## 本轮目标

- 为审后业务记忆定义独立 schema
- 把“已归档结果 -> 结构化记忆资产”的路径放回 Claude system 域
- 明确记忆资产必须保留 `request_id / result_file` 回链，且不进入 Python 业务逻辑

## 实际改动

- 新增 `knowledge/_schema/case-memory.schema.json`
  - 定义 `memory_id / domain / memory_type / applicable_when / checkpoints / policy_refs / recommended_verdict / source_trace` 等字段
  - `source_trace.request_id` 与 `source_trace.result_file` 为必填
  - `distilled_by` 固定为 `system-memory-distill`
- 新增 `.claude/commands/distill-memory.md`
  - 定义从 `logs/results/by-request/...` 提炼记忆的命令入口
- 新增 `.claude/skills/system/memory-distill/SKILL.md`
  - 约束 system 域只沉淀可复用业务模式
  - 明确禁止把路径错误、网络失败、网关异常等基础设施噪音写成业务记忆
- 新增 `knowledge/memory/expense/.gitkeep`
- 新增 `knowledge/memory/hr/.gitkeep`
- 新增 `knowledge/memory/legal/.gitkeep`
- 更新 `.claude/CLAUDE.md`
  - system 域现在同时承载 `system-rule-init` 与 `system-memory-distill`
- 更新 `.claude/skills/system/SKILL.md`
  - 把 memory distill 纳入 system 能力目录
- 更新 `.ai_state/design/agent-next-phase-blueprint.md`
  - 把记忆资产字段要求写进蓝图

## 验证

- 新增 `tests/test_memory_assets.py`
  - 验证 `case-memory.schema.json` 接受有效 payload
  - 验证缺少 `request_id` / `result_file` 的 payload 被拒绝
  - 验证 system skill / command / 全局路由已引用记忆沉淀能力
- `uv run pytest tests/test_memory_assets.py` 通过
- `uv run pytest` 通过，当前共 36 项
- `uv run ruff check server tests` 通过

## 为什么这版更对

1. 业务记忆现在有了独立于规则层和日志层的资产结构，不会把“运行事实”和“复用经验”混在一起。
2. 记忆沉淀放在 Claude system 域，而不是 Python stores 或服务逻辑里，继续守住了边界。
3. 记忆资产强制保留 `request_id / result_file` 回链，未来不管是人工追溯还是自动查询，都能追到原始结论。
4. 明确排除了基础设施噪音，避免把一次性路径错误、网络失败当成“业务知识”沉淀进去。

## 风险与遗留

- 当前 A-003 落地的是“记忆层结构和沉淀入口”，还没有真正把现有某个归档结果自动沉淀成 `knowledge/memory/...` 下的具体业务资产；这一步需要结合 A-004 的真实闭环来做首个高质量样本。
- 记忆资产 schema 目前偏“人工可读 + 机器可校验”的折中结构，后续如果查询面要做更细粒度聚合，可能还会再拆一些字段。
- 目前 `distill-memory` 还是 Claude 命令，不在 Python API 暴露，这符合边界，但也意味着短期内主要通过 Claude/CLI 工作流触发，而不是服务接口触发。

## 下一步建议

- 进入 A-004：打通单条审核业务闭环
- 优先用一个真实、规则可闭合的案例，完成：
  - `/audit`
  - `audit-result`
  - `review-delta`
  - `distill-memory`
  这一整条链的首次实战闭环
