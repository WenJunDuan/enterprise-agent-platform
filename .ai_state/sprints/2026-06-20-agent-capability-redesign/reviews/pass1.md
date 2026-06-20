## Spec Compliance (spec-compliance, 2026-06-20T00:00:00Z)

### MISSING (功能做少了)
- M1: .claude/commands/audit.md L10 仍保留原文"只有在确需多业务域协同（HR / legal 辅助域）时才调度子 agent"（pre-existing，本次 diff 未触碰该行）。checklist G0a 声称 audit.md "摘 HR/legal 辅助域调度 [done]"，而实际 diff 仅删除 L29-30 两条触发条件，L10 描述性提及原样留存。语义上仍暗示 HR/legal 为可调度辅助域，与 F8 "从编排移除干净"要求轻微不符（非路由代码层面，影响程度低）。

### EXTRA (功能做多了)
- E1 [合理 refactor]: .claude/CLAUDE.md 多域协同示例换成"报销材料是扫描件→OCR→expense"，替代被删的 3 条 legal/HR 示例。design.md 未显式要求此修改，顺手修缮，合理。
- E2 [合理 refactor]: .ai_state/architecture/ARCHITECTURE.md 增加"真实业务域 round4 校准"段，标注三真实域与已删死域。与 design.md L61"顺手裹挟"意图对齐，合理。

### DEVIATED (功能做偏了)
- D1: design.md L30 §脊椎一第2件要求"断言 policy_refs ⊆ 已注入规则集"（完整子集回查）。实现（server/common/output_contracts.py L162-167）仅做非空检查（approved/rejected 须 ≥1 条 ref）。全仓无 issubset/注入规则集检查。checklist 标为 G1b-lite done / G1b-full deferred，延后理由"规则在 Claude 侧注入 Python 不知注入集"技术上成立，但与 design.md 原文把三件事合并为 G1 一步表述存在偏差。
- D2: design.md L31 §脊椎一第3件（G1c）要求"金额/限额/日期由 OCR 确定性给数，比较由 Python 重算"。当前 diff 无任何算术重算逻辑。checklist 标 G1c deferred，理由"需 OCR 确定性数+比较逻辑"技术上成立，但同样偏离 design.md 将 G1 三件事列在同一步骤的表述。

### 覆盖表

| Design 任务 | checklist 状态 | 实际状态 | 文件证据 |
|---|---|---|---|
| G0a 删死域路由/plumbing/编排 | done | 实质完成；轻微残留见 M1 | server/api.py 删 /contract 路由注册；server/cli.py 删 review-contract 命令；server/platform/paths.py 删 CONTRACTS_DATA_DIR；server/routes/{contract,contract_worker}.py 已删；.claude/agents/{hr,legal}/ 已删；.claude/contracts/legal/ 已删；tests/ 4文件已删 |
| G0b 泛型化 TaskPipeline | deferred | 已延后，理由如实 | server/stores/ 剩 audit_task_store.py(211行)+tender_task_store.py(185行) 2份副本 |
| G1a schema 形校验 jsonschema.validate | done | 实质完成 | server/common/contract.py L88-120 `_validate_against_json_schema` 在 enrich 前对原始输出跑校验；tests/test_contract_registry.py L55-96 5条闸验用例 |
| G1b-lite policy_refs 非空检查 | done | 实质完成 | server/common/output_contracts.py L162-167；tests/test_contract_registry.py `test_gate_rejects_approved_without_policy_refs` |
| G1b-full policy_refs ⊆ 注入规则集 | deferred | 已延后，技术理由成立，见 D1 | 全仓无此逻辑 |
| G1c 算术重算 | deferred | 已延后，技术理由成立，见 D2 | 全仓无金额/日期 Python 重算 |
| G2/G3/G4/G5 | todo | 未开始，符合 checklist | diff 无对应新文件 |

### 范围诚实性

checklist 对 G0b/G1b-full/G1c/G2/G3/G4/G5 均标 deferred/todo 而非 completed，延后理由有技术依据，未将延后包装成完成。G0a 和 G1a/G1b-lite 声称"done"的内容均有代码与测试佐证，名实相符。expense/tender/OCR 路由与 schema 均未出现在 diff 中，未被误删/误改。

### Spec Compliance 总评

- MISSING 数: 1（audit.md L10 措辞轻微残留，非路由代码层面）
- EXTRA 数: 2（均为合理 refactor，无 scope creep）
- DEVIATED 数: 2（D1/D2 均因 design.md 把 G1 三件事合并一步、实际拆 lite/deferred 导致；延后技术理由成立）
- **建议**: PASS（有条件）
  - G0a/G1a/G1b-lite 声称完成部分名实相符。
  - D1/D2 是设计粒度不足导致的表述偏差，非欺骗性虚报——checklist 已诚实记录延后及理由。
  - M1 建议后续顺手清理，不构成阻塞。
  - 若口径要求 G1 三件全部完成才算 done，则 G1 仍为 in_progress（与 checklist 一致），主 agent 应知晓本 sprint 仍有 backlog 未完成。
