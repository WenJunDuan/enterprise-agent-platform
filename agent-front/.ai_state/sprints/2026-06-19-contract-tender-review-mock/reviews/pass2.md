## Spec Compliance (pass2)

> Superseded: this review targeted the earlier six-view implementation. The
> current user-corrected scope is documented in `../design.md`.

时间: 2026-06-19T02:54:50+08:00

审查对象: `git diff main...HEAD` 当前无提交差异；实际实现仍在 worktree 未提交区，因此本轮按 `git diff` + untracked files 对比 design/pass1。

### MISSING

- AC10/AC11 证据与 checklist 状态仍缺失。Design 要求 `bun run test`、`bun run lint`、`bun run build` 通过，并要求浏览器验收覆盖 `/contracts` 与 `/contracts/tender-review`（design.md:58, design.md:59）；当前 checklist 的验证项仍是 `status: pending` 且 `evidence_tool_use_ids: []`，并且 design_ref 仍指向 AC8/AC9 而非 AC10/AC11（checklist.yaml:37, checklist.yaml:38, checklist.yaml:39, checklist.yaml:40）。本轮未发现 sprint 目录下新增 evidence/验收记录文件。

### EXTRA

- scope creep: `.gitignore` 与既有 monitor/system `data/` 模块仍是 design 外变更。File Structure Plan 只列出 contract tender review、contracts routes、navigation registry、routeTree 相关文件（design.md:70）；实际新增 `.gitignore` 例外以纳入 `agent-front/src/features/monitor/oper-log/data/**` 和 `agent-front/src/features/system/user/data/**`（.gitignore:10, .gitignore:11, .gitignore:12, .gitignore:13, .gitignore:14），且新增/纳入的文件属于 monitor/system 域而非合同审查域（src/features/monitor/oper-log/data/business-type.ts:1, src/features/system/user/data/data.ts:1, src/features/system/user/data/schema.ts:1）。若这些是恢复既有被 ignore 的源码，属于合理仓库整理；但按本 sprint design 仍是额外范围，建议拆出或在设计中补充说明。

### DEVIATED

- 无阻塞偏离。上一轮 AC5 model-layer selector concern 已解决：design 要求 mock 数据与筛选/统计规则集中在 feature 数据/model 层，UI 不直接硬编码筛选统计（design.md:53）；当前 `getSelectedReviewItems`、`getSelectedDocuments`、`filterReviewHistory`、`getComparisonRows` 均在 model 层（src/features/contract/tender-review/model.ts:63, src/features/contract/tender-review/model.ts:74, src/features/contract/tender-review/model.ts:81, src/features/contract/tender-review/model.ts:102），UI 只通过 view model 调用这些 selector（src/features/contract/tender-review/index.tsx:173, src/features/contract/tender-review/index.tsx:177, src/features/contract/tender-review/index.tsx:194, src/features/contract/tender-review/index.tsx:207）。

### verdict

REWORK

理由: pass1 的 AC5 偏离已修复；`.gitignore`/既有 `data/` 模块应继续作为设计外 EXTRA 处理；AC10/AC11 的 checklist/evidence 缺失仍未解决，因此 spec-compliance 不通过。
