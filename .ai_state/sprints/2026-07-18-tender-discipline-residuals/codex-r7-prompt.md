你在隔离 git worktree（分支 `d11-r7-frontend`）里工作。任务：实现 D11 **C2/R7 前端 null guard**（FE-01/02/03，P2 防御，闭合 #4 报告 500 潜根因）。**这是 agent-front 前端任务，用户 2026-07-19 已授权。只改本 worktree，不 push，不碰 main。**

## 背景
tender-review 报告/工作台组件在数据字段缺失/undefined 时会崩（报告 500）或渲染 'undefined'/'NaN'/'N 分'/越界。加防御性 null guard：缺失数据优雅兜底，**不改有效数据的行为**。

## 目标文件 + 已知 gap（主 agent 已核 analysis-workbench-view.tsx）
`agent-front/src/features/contract/tender-review/components/{analysis-workbench-view.tsx, screen-content.tsx}`

已知 gap（analysis-workbench-view.tsx；同类模式在两文件都扫）：
1. **`DetailWorkbench`**：`activeCategory = data.categories.find(...) ?? data.categories[0]`，`categories` 为空时 undefined → `activeCategory.items.find`（:194）/`.items.map`（:239）崩。加 guard（activeCategory 兜底为含空 items 的对象，或整段空态兜底）。
2. **`props.data.projectInfo.name`（:58）/`.method`（:469）**：`projectInfo` undefined → 崩。加 guard/兜底。
3. **数组 `.map`/`.find`/`.length`**：`data.{reviewBidders, categories, paragraphs, scoringItems, bidderCards, overviewChecklist}` 部分已 `?? []`（:93/:465）、部分没有（:108/:144/:186/:219/:259/:469 直接用）→ 缺失时崩。统一 `?? []` 兜底。
4. **`item.loc + 1`（:385）**：loc undefined → "定位原文 · NaN"。guard。
5. `screen-content.tsx`：同类 getItemBadge/DetailSection 缺失字段渲染，自己扫 + 加 guard。

## 纪律
- 纯防御：缺失 → 优雅兜底（空态/占位/'—'），**不改有效数据渲染**；不引新依赖；沿用现有组件模式（cn / 占位风格）。
- 无 `any`；TS strict 下类型正确（别用 `as any` 绕过）。
- 跑：`cd agent-front`，若无 node_modules 先装依赖（该项目用 bun，`bun install`；bun 不可用则 `npm install`）→ `eslint .` 净 + `tsc -b && vite build` 过。若前端有测试脚手架（`bun test`）可加一条「undefined/空 data 不崩」断言；无脚手架则至少 lint + build 绿。
- 单独 commit（`fix(agent-front):`），不 push、不碰 main。
- 最终报告：改了哪些 guard（按文件）、lint/build 结果、有无加测试、任何 blocked。**遇设计与代码不符、或无法诚实通过 build：停下如实报告，别用 `as any`/`// @ts-ignore` 把红改绿。**
