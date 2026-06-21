# Expense UI 修复 — Codex Handoff

> 来源：用户 2026-06-21 实测报销审核页反馈 7 项。经 CC triage：**7 项全部为前端展示/布局**
> （后端 audit retry/list 端点已齐全、数据契约合法）。本文件交 codex 实施。
> CC 同步处理一个**独立**的服务端数据硬化（见末尾「服务端并行改动」），不影响前端实施。

## 涉及文件
- `agent-front/src/features/audit/audit-task-detail-page.tsx`（详情页，#1-#5）
- `agent-front/src/features/audit/audit-tasks-page.tsx`（列表页，#6-#7）
- `agent-front/src/features/audit/format.ts`（#4 风险维度中文映射）

验收：`npm --prefix agent-front run lint && npm --prefix agent-front run build` 全过；
后端在 9999、前端 dev 5173，浏览器逐项核对。

---

## #1 「已完成」状态徽标移到「任务状态 EXP-…」标题右侧，左右分布
- 文件：`audit-task-detail-page.tsx` 第 254-260 行（任务状态 Card 的 `CardHeader`）。
- 现状：`className='gap-3 md:flex-row md:items-start md:justify-between'`——窄屏下标题与
  `TaskStatusBadge` 纵向堆叠。
- 改：让标题（case_id / claim_id，如 `EXP-20260620-1178`）与 `TaskStatusBadge` **始终同一行、
  左右分布**。把 header 改为 `flex flex-row items-center justify-between gap-3`（去掉 `md:` 前缀
  使其在所有断点都左右排）。

## #2 「重新审核」按钮移到「任务详情」卡右上角（与 #1 同思路，右对齐）
- 文件：`audit-task-detail-page.tsx`。现状：第 281-291 行，按钮在日期网格下方、整行左对齐。
- 改：把「重新审核」Button 从 `CardContent` 底部（281-291 行的 `<div className='flex flex-wrap gap-2'>…`）
  挪到任务状态 Card 的 `CardHeader` 右侧——与 `TaskStatusBadge` 同区（标题在左，徽标+重审按钮在右）。
  保留 `runRetry` 逻辑（第 207-215 行）与 `disabled={action === 'retry'}` 态不变，仅移动位置。
  建议：header 右侧用一个 `flex items-center gap-2` 容器装 Badge + 重审 Button。

## #3 删除「人工复核原因 data_conflict」展示块
- 文件：`audit-task-detail-page.tsx` 第 93-98 行（`ResultCards` 内的 `manual_review_reason` Alert）。
- 改：**整段删除**这个 `{result.manual_review_reason ? (<Alert>…</Alert>) : null}` 块。
- 背景：该字段是原始英文枚举（data_conflict 等），与下方中文 `reasons` 重复；用户要求去掉展示。
  （数据层面 CC 会保证该字段仅在 verdict=manual_review 时存在，见末尾；但前端这里无论如何都不再展示。）

## #4 风险维度指标项英文→中文
- 文件：`format.ts`（`normalizeRiskDimensions`，第 32-54 行附近）+ 详情页第 114 行 `{dimension.name}`。
- 现状：`dimension.name` 直接渲染后端枚举值（英文）。后端 `name` 枚举固定为 5 个：
  `invoice / amount / approval / budget / anomaly`（见 `.claude/contracts/common/audit-result.schema.json:85`）。
- 改：加一个映射表并在展示处用它（不要改后端输出，后端枚举是契约）。建议在 `format.ts` 导出：
  ```ts
  export const riskDimensionLabels: Record<string, string> = {
    invoice: '发票',
    amount: '金额',
    approval: '审批',
    budget: '预算',
    anomaly: '异常',
  }
  ```
  详情页第 114 行改为 `{riskDimensionLabels[dimension.name] ?? dimension.name}`（未知 key 回退原值）。

## #5 「证据与依据」里「审核理由」与「证据链」合并为一块
- 文件：`audit-task-detail-page.tsx` `EvidenceCards`（第 129-179 行）。
- 现状：三个独立 `<details>`：审核理由（reasons，142-151）、策略引用（refs，152-161）、证据链（evidence，162-175）。
- 改：把**审核理由 + 证据链**合并成一个区块（策略引用保持独立不动）。合并后建议：一个标题
  「审核理由与证据链」，内部先列 reasons（中文句子列表），再列 evidence_chain 卡片（source/finding/conclusion）。
  保留各自的空判断（reasons/evidence 为空则不渲染对应子段）；外层 Card 与「策略引用」`<details>` 结构不变。
  > 注：合并是视觉合并，数据仍来自 `result.reasons` 与 `result.evidence_chain` 两个字段，别丢任一来源。

## #6 发票审核列表补「重新审核」按钮
- 文件：`audit-tasks-page.tsx` 第 263-301 行（actions 列）。
- 现状：第 278 行 `{task.status === 'failed' ? (<重审按钮>) : null}`——只有 failed 才显示重审。
- 改：让「重审」对 **completed 与 failed** 都可用（用户要在已完成记录上也能重审）。即把条件改为
  `task.status === 'failed' || task.status === 'completed'`（accepted/running 仍不显示，避免对在途任务重复排程）。
  复用现有 `runAction(task.request_id, 'retry')`（第 184-203 行）与 `retryTask`（后端 `POST /audit/tasks/{id}/retry` 已存在）。

## #7 「新建报销审核」按钮移到「报销审核记录」卡标题右侧，左右摆放
- 文件：`audit-tasks-page.tsx`。
- 现状：第 354-359 行，「新建报销审核」按钮在页面顶部 header 行（与「报销审核」大标题同行）。
- 改：把该 Button 从页面顶部移到「报销审核记录」Card 的 `CardHeader`（第 365-368 行）右侧，与
  `CardTitle 报销审核记录` 左右分布。把该 `CardHeader` 改为 `flex flex-row items-center justify-between`
  （标题+描述在左，按钮在右）。页面顶部 header 行（347-360）相应去掉按钮，只留标题+副标题。

---

## 服务端并行改动（CC 处理，前端无需关心）
- `server/common/output_contracts.py` `normalize_audit_result`：当 `verdict != "manual_review"` 时
  剥离 `manual_review_reason`，避免 approved/rejected 结论残留无意义枚举（#3 的数据层根因）。
  这是独立的数据洁净化，与前端 #3 删展示互不依赖。
