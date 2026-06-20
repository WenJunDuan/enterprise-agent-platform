# Codex 设计评审 — tender 数据模型优化

> Reviewer: Codex CLI v0.141.0 (gpt-5.5) · 2026-06-20 · 对象: design.md(初版) · 121K tokens 评审
> 命令: `codex exec -s read-only "$(< logs/codex-review/design-instructions.txt)"`（网关恢复后成功）

## VERDICT: **APPROVE-WITH-CHANGES**

方案 B（`tender_projects` 一等实体）方向正确，比 group_id 字符串分组更符合"多投标人/回看/价格横比"业务模型。明确否决的替代：EAV 不适合、JSON-only 不能作分组主索引、`conversation_id` 不能复用（worker 每次评标新建会话，语义是模型会话非招标实体）。

## Findings（已纳入修订）

| # | 级别 | 问题 | 采纳的修订 |
|---|---|---|---|
| 1 | P1 | bid 名册不能只靠 `tender_tasks`——删任务会丢该投标人，但结论仍在 `results` → `/projects/{id}/bids` 漏人 | Phase 1 用 **`results.project_id` ∪ 活跃 `tender_tasks`** 合并出名册（删任务后完成的投标人仍从 results 显示）；`tender_bids` 投影表列为 Phase 2 升级 |
| 2 | P1 | 显式 `POST /projects` 不防双击/并发重复建 | 加 `UNIQUE(tenant, tender_no) WHERE tender_no IS NOT NULL` 部分索引 + create 做 **get-or-create 幂等**；无 tender_no 允许多条 |
| 3 | P1 | archive 透传 project_id 不能落进 `**opts`（会被传给 `build_options` SDK 选项） | `project_id` 做成 `run_agent_json`/`archive_result_payload` 的**显式可选参数**，写入 `ResultRecord`/payload/results 列；worker 后置 update 仅作补偿 |
| 4 | P2 | `group_id` 不应泄漏到 tender 路由 | 泛型 TaskStore 内部用 `group_id`，tender 边界统一 `project_id`，加 wrapper `list_tender_tasks_by_project` |
| 5 | P2 | API 面略多 | Phase 1 收敛为 5 端点：`POST/GET /projects`、`GET /projects/{id}`、`POST /projects/{id}/evaluate`、`GET /projects/{id}/results`；`/bids` 作详情子资源；`/compare` defer Phase 2；旧 `/tender/evaluate` 挂 NULL 不自动建 project |

## §7 决策（codex 判断，已采纳）
1. B over A（同意），升级为 "B + result/bid 投影策略"。
2. 链接列：TaskStore 内部 `group_id`，tender 边界 `project_id`，results 用 `project_id`。
3. 自动建 vs 显式建：v1 显式建；旧 `/tender/evaluate` 先 legacy NULL。
4. archive 透传 vs worker 后置：选 archive 透传，worker 后置只做补偿/迁移。

## 额外输入（非 codex，本会话发现）
前端 `agent-front/src/features/contract/tender-review/types.ts` 已有 `TenderProject` 类型（mock UI），字段作后端 schema 金标准：`code`(招标编号)/`name`(项目名)/`method`/`status`(doing/review/done/archived)/`bidderCount`/`recommendedBidder`/`controlPrice`(标底)；`ReviewBidder.rank`、`CompareGroup`(价格横比)→ 价格横比是前端已期待项。聚合字段(bidderCount/rank/recommended)**计算不存储**。
