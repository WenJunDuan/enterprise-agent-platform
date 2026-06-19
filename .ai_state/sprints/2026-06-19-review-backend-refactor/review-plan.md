# Phase 0 · 后端重构质量复核计划

> roadmap item0 (`contract-audit-platform`) · read-only 门禁 · 2026-06-19

## 范围

- **diff 区间**: `bbf40ac..a337fd7`（起：分层设计 c1581d3 之前；止：codex 收尾）。
- **路径**: `server/ tests/ deploy/` + 顶层配置；**排除** `agent-front/ .ai_state/ knowledge/`。
- **规模**: 44 文件 +1536/-1169。四块：server 分层 / 企业日志 / 校验注册表(OCP) / data 存储重构。
- 命令: `git --no-pager diff bbf40ac..a337fd7 -- server/ tests/ deploy/`。

## 已有一轮 codex（session 2026-06-19-codex-review.md）

盲点集中在：迁移完整性 / schema drift / 统一库写锁放大。已修：migrate 两表 payload 泛化、
搬 sessions/events、_copy_table 列交集逐行 try、memory_store mtime 写锁守卫、BEGIN IMMEDIATE。
本轮验证这些修复是否彻底，并找新问题。

## 4 轮（按风险主题，用户确认）

| 轮 | 主题 | 焦点 | 执行者 |
|---|---|---|---|
| R1 | 数据/迁移完整性 | migrate 逐表 payload/blob/指针、schema drift、写锁、事务原子性、读路径归一 | reviewer + spec-compliance → evaluator |
| R2 | 架构/分层一致性 | 依赖单向无环、ops/deps 抽离、注册表 OCP、SRP/文件长度 | reviewer + spec-compliance → evaluator |
| R3 | 安全/健壮性 | 日志不泄密、错误脱敏、边界/失败注入、security-checklist | reviewer + spec-compliance → evaluator |
| codex | 独立交叉 | `codex exec -s read-only` 复审同范围 | codex |

## 产物

- `reviews/round1.md` / `round2.md` / `round3.md` / `codex-cross.md`
- 每轮 evaluator VERDICT(PASS/CONCERNS/REWORK/FAIL)；汇总 `reviews/summary.md`。
- 出 REWORK → 插修复子步骤(黄/红区按铁律路由) → 全绿 + 全量 pytest 通过 → item0 completed → 进 item1。
