# Review 汇总 · agent-capability-redesign（G0+G1，交叉审查）

> 范围：`adf9c43..HEAD`（goal 设置 + G0a 删死域 + G1 验证闸）。reviewer + spec-compliance 并行（read-only）。

## VERDICT: **PASS**（有条件，findings 已修）

| 审查者 | 结论 | 要点 |
|---|---|---|
| reviewer | 健康，方向正确、执行干净 | F1/F2 P1（已修）、F3 P2（已修）、F4 INFO（命名,记 backlog） |
| spec-compliance | **PASS** | 范围**诚实**：G0b/G1c/G2-G5 如实标延后/未做，无虚报；expense/tender/ocr 未误改；D1/D2 延后理由成立 |

## findings 处置

| # | 级别 | 问题 | 处置 |
|---|---|---|---|
| F1 | P1 | `_validate_against_json_schema` 只捕 `ValidationError`，漏 `SchemaError`(schema 坏→500 暴露内部路径) | **已修**：补捕 `jsonschema.SchemaError` → 转 JSONContractError |
| F2 | P1 | G1b 缺 rejected 对称用例 + manual_review 豁免快照 | **已修**：加 `test_gate_rejects_rejected_without_policy_refs` + `test_manual_review_allowed_with_empty_policy_refs` |
| F3/M1 | P2 | audit.md:10 残留 "HR / legal 辅助域" 提及(死域) | **已修**：改为「跨域旁证(扫描件先 OCR)」 |
| F4 | INFO | `contract_max_retry` 命名删 legal 后语义偏(实为通用 JSON 重试计数) | backlog：下个 refactor 改名 |

## 收口

- 修复后 **267 passed / ruff clean / 6 分层守卫不退化**。
- spec-compliance 详档：`reviews/pass1.md`。

## 本 sprint 完成度（诚实）

- **done**：G0a（删 legal/contract+HR 死域，round4 F8）+ G1a（schema 形校验）+ G1b-lite（approved/rejected 须引 ≥1 ref）= round4 **最高优先级两项**（F8 + F1 BLOCKER 核心）。
- **deferred/remaining**：G0b 泛型化 TaskPipeline（仅剩 2 副本+触 working audit）、G1b-full（refs⊆注入规则集，需 domain→rules 管线）、G1c（算术重算，需 OCR 数）、G2（PLAN 类型化）、**G3（阻塞：无外部 API 凭证）**、G4（记忆三层，部分在 gitignored knowledge/）、G5（人工否决回路）。
