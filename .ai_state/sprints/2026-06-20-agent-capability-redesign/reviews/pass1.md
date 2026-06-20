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

---

## Spec Compliance — 第二批 G3/G0b/G1b-full/G1c/G2/G4/G5 (spec-compliance, 2026-06-20T10:30:00Z)

对照范围：`git diff c9e09da..HEAD`（10 commits，22 files，+1022/-407 行）

### MISSING (功能做少了)

- M1: design.md §脊椎一·第2件 L30 要求"evidence_chain 每条 source 须解析到真实输入文件/字段，解不出 → 降级 manual_review"。`server/common/output_contracts.py` 的 `_validate_audit_result` 完全未校验 evidence_chain.source 是否指向真实输入文件——只有 jsonschema 层的结构校验（source 为非空字符串即过）。checklist G1b-full 描述仅涵盖 `_load_known_rule_ids + policy_refs ⊆ 真实 rule_id`，未记录 evidence_chain source 解析为 backlog，属漏记而非诚实延后。
- M2: design.md L49 G4 明确要求"先修 `case-memory.schema.json` 缺 tender 枚举"为 G4 首要子任务。`knowledge/_schema/case-memory.schema.json` 的 domain 枚举仍为 `["expense","hr","legal"]`（缺 tender），无 `valid_until`/`superseded_by`/`decided_under_rule_version` 字段。`knowledge/` 整目录 gitignored（`.gitignore` L15），git diff 中零证据。checklist 将此列为 `user_todo_gitignored`，但 design.md Build Order L49 将其列为 G4 本身任务，G4 accept 条件"tender 记忆可存可校验"因此无法从 git 层面验证达成。

### EXTRA (功能做多了)

- E1 [合理 refactor]: `server/stores/task_store.py` 新建泛型 TaskStore，audit/tender store 退化为薄包装，调用方零改。design.md 未规定实现路径，worker/route 层留 backlog 的决策如实标注，合理。
- E2 [合理 refactor]: `.env.example` 新建，含 CREDIT_API_URL/CREDIT_API_KEY 占位说明。design.md 未明确要求，符合 security-checklist.md 的 .env.example 要求，顺手落地，不影响 spec。

### DEVIATED (功能做偏了)

- D1: design.md L30 §脊椎一·第2件要求 evidence_chain source 解析到真实输入文件/字段，与 policy_refs 子集校验并列为同一件事。实现仅完成 policy_refs 侧（env 门控），evidence_chain source 解析逻辑完全缺失且未进入 checklist backlog。偏离 design 文本，非诚实延后。
- D2: G0b checklist 声称 worker/route 层"80%/72% 雷同"。实测：audit_worker vs tender_worker SequenceMatcher ratio 78%（基本符合）；audit.py vs tender.py ratio 64%（声称 72% 存在偏差）。小幅高报，不影响"留 backlog"判断合理性，但数字不准确。
- D3: design.md L46 G1 三件合并为一步，G1c 算术重算（OCR 确定性数→Python 比较）仍 deferred，且 design.md 未预告此件会拆成独立 backlog。与第一批 pass1.md D2 一致，本批次未解决。

### 覆盖表

| Design G | checklist 状态 | git 证据 | 名实符合度 |
|---|---|---|---|
| G0b store 层泛型化 | done | `task_store.py` +220行；audit/tender 薄包装；15 store 测试 | 符合（worker/route backlog 如实标注） |
| G1b-full policy_refs⊆真实rule_id（env门控） | done | `_load_known_rule_ids` + `RULE_REF_CHECK`；4 测试 | 符合（门控理由成立） |
| G1b-full evidence_chain source 解析 | 未记 backlog | 全仓无此逻辑 | **漏记** — design.md L30 明确要求，见 M1/D1 |
| G1c 评分一致性 score≤max | done | `_verify_scoring_consistency`；3 测试 | 符合（验证非判断，未门控） |
| G1c 算术重算（OCR数→Python比较） | deferred | 全仓无此逻辑 | 理由技术成立，但 design 未预告拆分 |
| G2 plan schema + 校验 | done | `plan.schema.json` + `_verify_plan_shape`；3 测试；tender-evaluate S1 文档活化 | 符合（可选产出，产出则校验） |
| G3 工具契约化（代码+env门控） | done | `credit_api.py` + `credit-check.schema.json` + `CreditApiSettings` + CLI credit-check；5 测试 | 符合（未配置→None→manual_review） |
| G3 自动注入评标流程 | backlog | `tender-evaluate.md` 无 credit 调用 | 理由如实（鸡生蛋问题，技术成立） |
| G4 SKILL 三层+衰减+版本复检 | done（tracked） | `memory-query/SKILL.md` +15行，行为规范完整 | 符合（Claude 侧行为规范可追溯） |
| G4 case-memory.schema.json 修 tender 枚举+3字段 | user_todo_gitignored | knowledge/ 全 gitignored，零 git 证据 | **不可验证** — design.md L49 列为 G4 前置，见 M2 |
| G5 override_store + CLI + distill 文档 | done | `override_store.py` + CLI override-result + distill-memory.md G5段；4 测试 | 符合 |
| G5 全自动闭环 distill | backlog | distill-memory.md 说明手动导出流程 | 理由如实（跨 Python/Claude 边界） |

### 范围诚实性

- expense/tender/ocr 路径无误伤：`git diff --name-only` 无 server/routes/audit.py、server/routes/ocr.py、server/audit/、server/ocr/ 改动，真实业务流程未受影响。
- G1b-full RULE_REF_CHECK 门控和 G3 未配置跳过的理由技术上成立，均未将"关闭状态的功能"包装成"完整 done"——checklist 有明确启用条件说明，名实相符。
- G4 schema 修改归入 user_todo_gitignored：`knowledge/` gitignored（.gitignore L15）是客观约束，非虚报；但 design.md L49 将此列为 G4 自身任务而非用户待办，责任边界不清晰，accept 条件无法从 git 层面验证。
- G0b worker/route 相似度声称值与实测有偏差（route 层 64% vs 声称 72%），小幅高报，不改变留 backlog 的合理判断。

### Spec Compliance 总评（第二批）

- MISSING 数: 2（M1 evidence_chain source 解析完全缺失且未进入 backlog；M2 case-memory schema 修改 git 不可追溯）
- EXTRA 数: 2（均合理 refactor，无 scope creep）
- DEVIATED 数: 3（D1 evidence_chain 偏离；D2 route 相似度小幅高报；D3 G1c 算术重算延后但 design 未预告，延续第一批 D2）
- **建议**: REWORK（条件降级）
  - M1/D1 是实质问题：evidence_chain source 解析在 design.md L30 明确要求，代码完全缺失且 checklist 未记为 backlog。建议补入 checklist backlog 并给出明确延后理由，或补实现。
  - M2 是可追溯性问题：G4 accept 条件依赖 gitignored 文件的用户手工修改，建议在 checklist 中明确"G4 schema 部分验收方式 = 用户在部署侧操作并提供截图/确认"，而非以 git diff 作为唯一验收证据。
  - D2/D3 轻微，不阻塞，可在下次 polish 顺手修正。
