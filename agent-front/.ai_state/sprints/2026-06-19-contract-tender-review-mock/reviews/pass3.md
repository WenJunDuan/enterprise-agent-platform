## Spec Compliance (pass3)

> Superseded: this review targeted the earlier six-view implementation. The
> current user-corrected scope is documented in `../design.md`.

时间: 2026-06-19T03:06:23+08:00

审查对象: `git diff main...HEAD --stat/name-only/log` 为空；当前实现主要在未提交工作区，因此按 `git diff`、untracked files、`checklist.yaml`、`evidence.yaml` 对比 `design.md`。

### MISSING

- AC11 仍未证明。Design 要求浏览器验收覆盖 `/contracts` 与 `/contracts/tender-review`，页面非空且无明显重叠（design.md:61）；当前证据只记录 Browser Use URL policy 拒绝访问本地 URL，明确写明 AC11 remains unproven（evidence.yaml:39），checklist 的 T5 仍为 `status: in_progress` 且 blocked_by 同样说明 AC11 browser verification is not proven（checklist.yaml:66）。这符合用户提示“应保持 not-proven”，但验收标准本身尚未满足。

### EXTRA

- 合理仓库卫生: `.gitignore` 除 design 允许的前端源码 `data/` 精确例外外（design.md:39, design.md:76），还新增了 `.agents/`、`.codex/`、`AGENTS.md` 忽略项（.gitignore:33）。这些不是合同审查 mock 功能文件计划的一部分（design.md:72），但与同文件中已文档化的仓库卫生修正同类，未扩大运行时 `data/` 或密钥范围。
- 合理流程/状态记录: 本轮工作区还包含根级 Athena/CC 状态更新，不在本 sprint File Structure Plan 内（design.md:72），包括 `.ai_state/_index.md` 新增 agent-front out-of-scope 决策指针（.ai_state/_index.md:96）、根 compound 决策更新（.ai_state/compound/2026-06-19-decision-agent-front-cc-out-of-scope.md:28）、旧 sprint evidence/tool-trace 收尾记录（.ai_state/sprints/2026-06-18-tender-domain/evidence.yaml:591, .ai_state/sprints/2026-06-18-tender-domain/tool-trace.jsonl:274）。这些是流程留痕，不是本功能实现。
- 合理 System-path 产物: design 的目标包含 System path 实现与验收（design.md:2, design.md:23），但 File Structure Plan 未列 architecture/cleanup/compound 产物（design.md:72）；实际新增 architecture 总入口和子系统档（agent-front/.ai_state/architecture/ARCHITECTURE.md:1, agent-front/.ai_state/architecture/frontend-contract-tender-review.md:1）、domain decision（agent-front/.ai_state/compound/2026-06-19-decision-contract-tender-review-domain.md:1）与 cleanup-pass（cleanup-pass.md:1）。按 Athena System/polish 流程合理，不视为 scope creep。

### DEVIATED

- 未发现阻塞性实现偏离。用户修正的合同审查/合同审核域已落到 `/contracts/tender-review`：design 要求合同组新增 `招投标审核` 且不回退到发票/OCR（design.md:19, design.md:53）；实际导航和 breadcrumb 为 `合同审查 > 招投标审核`（src/app/navigation/registry.ts:20, src/app/navigation/registry.ts:21），合同组同时保留 `合同审查清单` 与 `招投标审核`（src/app/navigation/registry.ts:41）。`/contracts` 作为父路由渲染 `Outlet`，原清单移动到 index route，新页面独立 route 接入（src/routes/_authenticated/contracts.tsx:1, src/routes/_authenticated/contracts/index.tsx:1, src/routes/_authenticated/contracts/tender-review.tsx:1）。
- mock/model 边界与交互方向一致。Design 要求 mock 数据集中在 feature 数据/model 层，UI 不直接硬编码筛选统计（design.md:55），且开始分析只展示进度并进入分析中心、不调真实接口（design.md:56）；实际 mock 数据在 `mock-data.ts`（src/features/contract/tender-review/mock-data.ts:3），筛选/统计/对比/报告在 `model.ts`（src/features/contract/tender-review/model.ts:43, src/features/contract/tender-review/model.ts:81, src/features/contract/tender-review/model.ts:102, src/features/contract/tender-review/model.ts:132），开始分析只用本地 interval/progress 切屏（src/features/contract/tender-review/use-tender-review-page.ts:40）。
- AC10 已有主工作区命令证据。Design 要求 test/lint/build 通过（design.md:60）；当前 evidence 在 `/Users/mi_manchi/workspace/enterprise-agent-platform/agent-front` 记录 `bun run test`、`bun run lint`、`bun run build` 均 PASS（evidence.yaml:3, evidence.yaml:9, evidence.yaml:15）。

VERDICT: REWORK

原因: 功能实现、合同域隔离、`.gitignore`/frontend `data/` 修正、AC10 证据均已对齐；但 AC11 是明确验收标准且当前只有阻塞记录，没有有效浏览器验收证据。
