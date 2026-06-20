# Tender 数据模型优化 — 招标项目实体 + 多投标人追加 + 结果回看（终版）

> Sprint/Goal 2026-06-20 · Path: **System** · 设计先行 → codex review(**APPROVE-WITH-CHANGES**) → 本终版可实施。
> 驱动：用户运营模型「一个招标 → 多家投标人陆续上传追加 → 每次只评一家 → 已出不重审 → 存 data」。
> 评审：`reviews/codex-design-review.md`（codex 5 findings 已全部纳入）+ 前端 `TenderProject` 类型对齐。

## 1. 背景与问题（现状已查证）

当前 tender 三表（单库 `data/db/platform.sqlite3`）：`tender_tasks`(泛型 TaskStore，执行态)、`results`(结论 payload)、`sessions`(会话审计)。每次 `/tender/evaluate`=一条孤立任务，**无招标分组键**，`conversation_id` 每次新建不可复用。三缺口：① 无"招标项目"概念(三家=三条孤立任务)；② 回看绑死任务(删任务→结论从回看消失)；③ 价格横比无锚。

## 2. 方案：B（tender_projects 一等实体）+ 投影合并策略

codex 确认 B over A（实体 > group_id 字符串列；EAV/JSON-only/conversation_id 均否决）。**招标项目是 owns N 个投标评标的领域实体**。前端 `agent-front/.../tender-review/types.ts` 的 `TenderProject` 已是这个模型（code/method/status/bidderCount/recommendedBidder/controlPrice + rank + 价格横比表），作 schema 金标准。

**分两期**：
- **Phase 1（本 goal）**：projects 实体 + 链接 + 5 个 project 端点 + 名册/回看（合并 results∪活跃 tasks）。"追加多家/按招标查看/结果回看"全可用。
- **Phase 2（后续）**：价格横比/排名/recommendedBidder 聚合 + `/compare` 端点 + （若合并查询变重）`tender_bids` 投影表。

## 3. 详细设计（Phase 1）

### 3.1 新表 `tender_projects`（字段对齐前端 TenderProject）
```
project_id    TEXT PRIMARY KEY      -- 服务端生成
tenant        TEXT NOT NULL
tender_no     TEXT                  -- 招标编号(前端 code，可空)
title         TEXT                  -- 项目名(前端 name)
tenderee      TEXT                  -- 招标人
method        TEXT                  -- 评标方法
control_price TEXT                  -- 标底/控制价(前端 controlPrice)
status        TEXT NOT NULL DEFAULT 'doing'  -- doing/review/done/archived(对齐前端)
created_at    TEXT NOT NULL
updated_at    TEXT NOT NULL
-- 索引: (tenant, created_at DESC)
-- 幂等: CREATE UNIQUE INDEX ... ON tender_projects(tenant, tender_no) WHERE tender_no IS NOT NULL  [codex P1.2]
```
聚合字段(bidderCount/score/rank/recommendedBidder) **计算不存储**（按需聚合 results，避免去同步）。

### 3.2 链接列（幂等 ALTER，加在现有表）
- `tender_tasks`：泛型 `TaskRecord` 加 nullable `group_id`（TaskStore **内部**字段）。**tender 边界统一叫 `project_id`，group_id 不泄漏到路由** [codex P2.4]；加 wrapper `list_tender_tasks_by_project(tenant, project_id)`。
- `results`：加 nullable `project_id` 列。

### 3.3 project_id 写入 results 链路（显式参数，非 **opts）[codex P1.3]
`project_id` 做成**显式可选参数**贯穿：`run_command_json → run_agent_json → archive_result_payload → ResultRecord/payload/results 列`。**绝不**走 `**opts`（会被 `build_options` 当 SDK 选项）。worker 后置 update 仅作补偿/迁移，不作主链路。

### 3.4 API 面（Phase 1 收敛为 5 端点）[codex P2.5]
| 端点 | 用途 |
|---|---|
| `POST /tender/projects` | 建招标项目；**get-or-create 幂等**(同 tenant+tender_no 已存在则返回现有) [codex P1.2] |
| `GET /tender/projects` | 列招标项目(tenant,分页,可按 status) |
| `GET /tender/projects/{id}` | 项目详情 + bid 名册汇总(合并 results∪活跃 tasks，计算 bidderCount/各家 status) |
| `POST /tender/projects/{id}/evaluate` | **追加一家投标评标**(挂该 project；body 同现 evaluate directory/upload) |
| `GET /tender/projects/{id}/results` | 该招标下所有结论回看(走 `results.project_id`，**独立于任务删除**) |

- `/bids` 名册并入 `GET /projects/{id}` 详情(子资源，不单列端点)；`/compare` 价格横比 **defer Phase 2**。
- **向后兼容**：旧 `POST /tender/evaluate` + `/tender/tasks/*` 不动；旧 evaluate 的 project_id 挂 **NULL**（legacy 散单），**不自动建 project**(避免重复) [codex P2.5/§7.3]。

### 3.5 bid 名册 = results.project_id ∪ 活跃 tender_tasks [codex P1.1]
`GET /projects/{id}` 的投标人名册合并两源（**删任务后已完成的投标人仍在 results，不漏人**）：
- 完成/失败且有结论 → `results WHERE project_id`(durable，带 claim_id/verdict)
- 在途(accepted/running) → `tender_tasks WHERE group_id AND status NOT IN(completed)`(claim_id 可能为空=评标中)
- 按 request_id 去重，优先 results。

### 3.6 命令侧（.claude）
`tender-evaluate.md` 把"招标项目标识"由散文改为钉 `extracted_data.tender_project_id`（招标编号优先），与列名口径一致，供回填/校验。

## 4. 影响范围
- 新：`server/stores/tender_project_store.py`（projects CRUD + get-or-create 幂等）。
- 改：`server/stores/task_store.py`(加 group_id 列+迁移+索引+list 过滤)、`server/stores/tender_task_store.py`(wrapper)、`server/stores/result_store.py`(加 project_id 列+迁移+archive 显式参数+按 project 查询)、`server/common/json_bridge.py`(project_id 显式参数透传)、`server/common/command_adapter.py`(透传)、`server/routes/tender.py`(5 端点)、`server/routes/tender_worker.py`(透传 project_id)、`.claude/commands/tender-evaluate.md`(钉字段)。
- 测试：project store(含幂等)+ 路由(5 端点+名册合并+回看独立于删除)+ 迁移幂等。
- `architecture/`(System ≥5 文件，ship 前更新现状档)。

## 5. 迁移与风险
- **加法式**：新表 + nullable 新列 + 幂等 ALTER(仿 result_store PRAGMA 检查)；既有行 project_id=NULL(legacy)，不丢数据、向后兼容。
- archive 加**可选**参数默认 None → audit 不传，零影响 [codex P1.3]。
- 泛型 TaskStore 加 nullable group_id → audit_tasks 多一空列，无害。
- 幂等建 project 防并发重复 [codex P1.2]。

## 6. 验收
- 同 project `POST /projects/{id}/evaluate` 追加多家 → `GET /projects/{id}` 名册列全部、`GET /projects/{id}/results` 回看全部结论；**删某 task 后其余结论回看不受影响**(codex P1.1 回归测试)。
- get-or-create 幂等：同 tenant+tender_no 重复 POST 返回同一 project_id。
- 旧 `/tender/evaluate` + `/tender/tasks/*` 不破(向后兼容测试)。
- `uv run pytest -q` 全绿 + ruff + 迁移幂等(重复 init 不报错)。
- System 路径：交叉审查(reviewer+spec-compliance+evaluator) → 更新 architecture → ship。

## 7. 决策（codex §7，已定）
1. **B + 投影合并策略**（Phase 1 合并 results∪tasks；tender_bids 投影 defer Phase 2）。
2. 链接列：TaskStore 内部 `group_id`，tender 边界 `project_id`，results 用 `project_id`。
3. v1 显式建 project（幂等）；旧 `/tender/evaluate` 挂 NULL 不自动建。
4. archive 透传选**显式参数**；worker 后置只补偿。
