# 交叉审查 Pass 1 — tender + 报销 前端 UI 改造

> 对象：`git diff -- agent-front/src`（generator subagent 第一版，patch 合入 main）。
> 方式：reviewer + spec-compliance 并行（铁律[Review强制]）。
> 综合裁定（CC 作 evaluator 收口）：**REWORK → 已修 → PASS**。

## 两方一致结论
- spec-compliance：契约 14 项 MISSING=0，但 **B⑤ partial / D① partial**，裁定 **REWORK**。
- reviewer：核心 **F1（P0，批量操作静默失效）** + F4，裁定合入前必修。

## Findings 处置

| ID | 级别 | 问题 | 处置 |
|---|---|---|---|
| F1/B⑤ | **P0** | 批量删/重审用列表缓存取 `bids[]`，但 `GET /tender/projects` 不返回 bids → 未加载详情的项目静默跳过 | **已修**：`collectBidRequestIds` 改为对每个选中项 `queryClient.fetchQuery(getTenderProject)` 取真实 `bids[].request_id`（命中缓存复用） |
| F2 | P0(类型) | `resolveTaskIds` 索引签名弱约束 | **已修**：删 `resolveTaskIds`，新路径用强类型 `TenderProjectDetailResponse.bids` |
| F4 | P1 | 批量循环 await，一个失败中断其余且不 invalidate | **已修**：`Promise.allSettled` + 始终 invalidate + `reportBatchFailures` 汇总失败抛用户可读错误 |
| F5 | P1 | 取消创建后 `projectForm` 不重置 | **已修**：`resetProjectForm()` + `screen-content` onCancel 调用 |
| F6 | P1 | `index.tsx` 仍传已废弃的 `onCreate` | **已修**：删 prop（index + page-heading） |
| F7/F10/D① | P1 | 创建页步骤条 `cursor-pointer` 但无跳步逻辑（伪可点击） | **已修**：单页表单无导航 → 无 `onStepClick` 时渲染非交互 `<div>`，保留与报销一致的视觉 |
| F8 | P1(a11y) | 追加投标弹窗文件 input 无 label 关联 | **已修**：input 加 `id` + Label 加 `htmlFor` |
| F9 | P2 | `funding_type` 类型含 `\| string` 使枚举失效 | **已修**：删 `\| string` |
| F3 | P1 | retry mock `status:'accepted'` 被疑非法 TaskStatus | **不改（已核实）**：`'accepted'` 是后端 tender 任务真实状态（`tender.py _submit_bid_evaluation`）；类型把 `status` 标成 audit `TaskStatus` 是**既有**建模小瑕，非本 PR 引入，留待单列 |

## 复验
- `eslint .` 0 错 / `tsc -b && vite build` ✓ / `bun test` **38 pass 0 fail**（main 树复跑）。

## 仍未覆盖（backlog，非本批）
- 空项目（无 bid）无删除端点 → 批量删对其为合理 no-op；如需"删项目"须后端加 `DELETE /tender/projects/{id}`。
- `TenderTaskStatusResponse.status` 类型应纳入 `'accepted'`（既有建模债）。
