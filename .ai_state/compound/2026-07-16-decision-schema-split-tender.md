---
doc_type: decision
slug: schema-split-tender
date: 2026-07-16
sprint: 2026-07-16-tender-feature-package
tags: [architecture, contract, tender, layering, roadmap-2026-07]
---

# Decision · F6 schema 分家：tender 输出契约处理器与 audit/expense 解耦

- **拍板人**: 用户（AskUserQuestion，方案 A vs B）
- **范围**: D2（tender-feature-package），program 级契约机制
- **触发**: D1 design Round 2 F6 [P1] + 深评 #7（compound/2026-07-03-explore-arch-deep-review-deltas.md）

## 根因（已核验代码）

```
contract.py:252 (末尾 import output_contracts, 确保内置契约就绪)
  → output_contracts.py:30-37 import tender_output 6 校验函数
  → output_contracts.py:460 import evidence_resolution.resolve_audit_evidence
  → output_contracts.py:462-470 全挂在共享 DEFAULT_OUTPUT_SCHEMA_NAME(audit-result)
```

双重耦合：① **分层**——common(output_contracts) → tender_output/evidence，若 D2 把这两模块迁进
server/tender/(feature) 即 common→feature 逆向依赖，撞 layering 守卫；② **行为**——tender 专属校验
（scoring/plan/disqualification 一致性）无条件跑在 expense/audit 结果上，纯 audit 调用也被
contract.py:252 副作用拉入 tender 模块。

## 决策：方案 A（schema 分家）

- tender 6 校验 hook + `resolve_audit_evidence` 挂 **tender 专属 schema 名**；audit/expense 用纯通用
  处理器（不再跑 tender 校验）。
- `tender_output`/`evidence_resolution` 从 tender 模块自注册 `register_schema_processor` → 合法迁入
  server/tender/（feature 自注册，output_contracts 不再 import 它们）。
- tender_worker/runner 改传 `schema_name=TENDER_SCHEMA`（现传 DEFAULT_OUTPUT_SCHEMA_NAME）。

## 依据

1. 彻底解耦（分层 + 行为纠缠一次解干净），与 D1 OCR 方案 i 分层拍板同调（[[2026-07-15-decision-ocr-service-layer]]）。
2. D2 "tender 逻辑全归位" 目标达成；D7 结构化 RAG 要复用 evidence_resolution 匹配内核（深评 #10），
   届时 evidence 在 server/tender/ 而非 common，边界更清。
3. 行为接缝（schema 名变更）风险由 **D1 eval 回归闸** + 针对性接缝测试兜底——D1 正是为这类改动建的闸。

## 放弃：方案 B（两模块留 common）

零行为变更、最省事，但 tender 逻辑仍散在 common，耦合债留到 D7；D2 "归位" 目标打折扣。

## critic / 定稿待定项

- tender schema：**新 json 文件** vs **复用 audit-result.json + 独立处理器注册**（倾向后者：结论
  schema 须仍符合 .claude/contracts/common/audit-result.schema.json，只处理器链分家）。
- 接缝测试三条：expense 不跑 tender 校验 / tender 校验不变 / 纯 audit import 不拉 tender。

## 关联

- [[2026-07-15-decision-ocr-service-layer]]（D1/D2 共用的另一 program 级分层拍板）
- sprints/2026-07-16-tender-feature-package/design.md F6 节（实现路径 5 步）
- compound/2026-07-03-explore-arch-deep-review-deltas.md #7（schema 分家原始提案）
