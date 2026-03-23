# 文档维护规则

本文定义仓库文档的单一事实源、内容边界与更新规则，目标是避免同一信息在多处重复维护后逐渐漂移。

## 单一事实源

| 内容类型 | 唯一主位置 | 说明 |
| --- | --- | --- |
| 费控闭环业务设计 | `.ai_state/docs/expense-control-design.md` | 包含报销域最新业务边界、skill 设计、规则样例与数据样例 |
| 基础留档与完整背景 | `.ai_state/docs/enterprise-agent-dev-guide.md` | 包含完整背景、长示例、配置样例、目标目录蓝图 |
| 仓库入口与当前状态 | `README.md` | 只回答“这是什么、现在到哪了、先看什么” |
| 架构快速摘要 | `.ai_state/docs/architecture-summary.md` | 只做高价值概括和回链，不承载长代码样例 |
| 实施路线 | `.ai_state/docs/bootstrap-roadmap.md` | 只维护分阶段落地顺序、范围边界和完成判定 |
| 文档维护约束 | `.ai_state/docs/doc-maintenance.md` | 只维护文档分工、术语规范和更新规则 |

## 内容归属

- `README.md` 不承载长设计说明、完整代码骨架或大段部署细节。
- `.ai_state/docs/architecture-summary.md` 只保留摘要，不复制主文档中的长代码块、长 JSON 示例或整段目录树。
- `.ai_state/docs/expense-control-design.md` 负责报销域的最新业务闭环设计、expense skills、规则样例和事前事后数据样例。
- `.ai_state/docs/bootstrap-roadmap.md` 只描述落地顺序、阶段边界与完成判定，不重写架构原理。
- `.ai_state/docs/enterprise-agent-dev-guide.md` 继续保留详细示例、完整目录结构、配置片段和服务端代码骨架，作为基础留档。

## 术语规范

以下术语在仓库文档中保持统一，不随文档场景改名：

- `CLAUDE.md`
- agents
- skills
- knowledge
- hooks
- `server/core.py`
- evidence chain

如果未来需要引入中文别名，应在首次出现时用“中文说明 + 原术语”方式表达，而不是替换原术语。

## 更新规则

- 当详细背景或长示例变化时，先更新 `.ai_state/docs/enterprise-agent-dev-guide.md`，再检查 `README.md` 与 `.ai_state/docs/` 中的摘要是否需要同步。
- 当报销域业务流程、expense skills 或样例数据变化时，先更新 `.ai_state/docs/expense-control-design.md`，再同步 `README.md`、`.ai_state/docs/architecture-summary.md` 与 `.ai_state/docs/bootstrap-roadmap.md`。
- 当仓库实际状态变化时，优先更新 `README.md` 的“当前状态”，避免读者把目标设计误认为已实现。
- 当实施顺序变化时，只更新 `.ai_state/docs/bootstrap-roadmap.md`，不要在多个文档分别维护不同版本的路线图。
- 当新增代码目录并稳定后，再决定是否拆出独立的部署文档、API 文档或运维手册。

## 当前阶段的特殊约束

- 只要仓库仍处于文档初始化或最小实现阶段，就必须明确区分“当前现状”和“目标结构”。
- 任何提到 `.claude/`、`knowledge/`、`server/`、`tests/` 的描述，如果指的是规划内容，就应写成“目标结构”“规划中”或“待落地”。
- 在实际代码和运行产物稳定前，不单独维护部署文档、API 文档、运维手册。
