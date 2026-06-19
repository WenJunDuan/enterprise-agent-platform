---
date: "2026-06-19"
sprint: "2026-06-19-contract-tender-review-mock"
doc_type: "decision"
status: "accepted"
---

# Decision: Contract Tender Review Domain

## Decision

招投标审核原型归入招投标/合同相关业务域，入口为 `/contracts/tender-review`，菜单分组为 `智能招投标审核`，菜单文案为 `项目管理`。

## Why

用户明确纠正该原型不是发票审核，也不属于 OCR。它处理投标文件、招标文件、评分对比和审核报告，业务语义更接近招采合规审查。

## Consequences

- `智能招投标审核` 组只保留 `项目管理` 与 `历史评审` 两个左侧入口。
- 旧 `合同审查清单` 入口和空白页移除。
- `/contracts/tender-review` 必须有独立 breadcrumb: `智能招投标审核 > 项目管理`。
- `分析中心`、`评分对比`、`审核报告` 只作为内部 mock 按钮流程，不作为菜单入口。
- 不复用或修改 `/audit/*` 发票审核流程，也不修改 `/ocr`。
- 初期只用 `features/contract/tender-review/mock-data.ts` 和 `model.ts`，后续真实接口替换应发生在该 feature 数据/model 边界内。
