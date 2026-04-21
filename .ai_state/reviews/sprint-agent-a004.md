# A-004 自审：单条审核业务闭环

## 结论

- VERDICT: PASS

## 本轮目标

- 用真实目录输入完成一次本地 `/audit`
- 让结果明确引用本地规则来源
- 让 `/distill-memory` 基于真实归档结果产出首条业务记忆
- 把 memory 查询能力接入 expense 审核主链

## 实际改动

- 新增真实 fixture：
  - `tests/fixtures/expense/travel-missing-preapproval/audit-request.json`
  - `tests/fixtures/expense/travel-missing-preapproval/invoice-summary.txt`
- 新增 `common-memory-query`：
  - `.claude/skills/common/memory-query/SKILL.md`
  - `.claude/skills/common/SKILL.md` 同步注册
- 更新 `expense-auditor` 与 `expense-audit`：
  - 审核主链现在明确要求在规则命中后查询 `knowledge/memory/expense/`
  - 记忆只能作为辅助证据，不能替代结构化规则
  - 若命中高价值记忆，应尽量在 `evidence_chain` 中以 `memory:` 来源体现
- 更新 `common-evidence-chain`
  - 支持 `memory:` 形式的证据来源写法
- 更新 `audit` command
  - 明确 `knowledge/memory/{domain}/` 中的记忆可作为辅助证据，但不能替代规则
- 生成首条真实 memory asset
  - `knowledge/memory/expense/expense.travel.pre-approval-mismatch.manual-review.v1.json`

## 真实闭环验证

### 审核

执行命令：

```bash
uv run python -m server.cli audit-json tests/fixtures/expense/travel-missing-preapproval
```

观察结果：

- Claude 实际读取了 fixture 目录、`audit-request.json`、`invoice-summary.txt`
- Claude 实际读取了：
  - `.claude/contracts/common/audit-result.schema.json`
  - `knowledge/expense/travel.rules.json`
  - `knowledge/expense/general.rules.json`
- 真实结果稳定命中了：
  - `expense.travel.015`
  - `expense.travel.016`
  - `expense.travel.018`
- 对 `EXP-TRAVEL-001` 给出了围绕“缺失事前申请/事后补提”的 `manual_review` / `rejected` 结论

### 记忆沉淀

执行命令：

```bash
uv run python -m server.cli ask "/distill-memory logs/results/by-request/2026/04/21/070a8b03-b0f7-4519-a07e-d7302048c1c3.json expense"
```

观察结果：

- Claude 实际读取了归档结果和 `knowledge/_schema/case-memory.schema.json`
- Claude 实际触发 `system-memory-distill`
- Claude 写出了第一条业务记忆
- 最终落地并修整为：
  - `knowledge/memory/expense/expense.travel.pre-approval-mismatch.manual-review.v1.json`
- 记忆资产保留了：
  - `source_trace.request_id`
  - `source_trace.result_file`
  - `source_trace.claim_id`
  - `source_trace.conversation_id`
  - `source_trace.claude_session_id`

## 验证

- 新增 `tests/test_audit_memory_integration.py`
- 新增 seed memory 校验到 `tests/test_memory_assets.py`
- `uv run pytest` 通过，当前共 41 项
- `uv run ruff check server tests` 通过
- 真实 `/audit` 路径实际跑通
- 真实 `/distill-memory` 路径实际跑通
- 首条 memory asset 已通过 `case-memory.schema.json` 校验

## 为什么这版更对

1. 这不是只靠文档的“设计闭环”，而是真实输入、真实规则、真实结果、真实记忆资产的本地闭环。
2. 规则来源和记忆来源都可追溯：
   - 规则通过 `policy_refs` + `knowledge/expense/*.rules.json`
   - 记忆通过 `knowledge/memory/...` + `source_trace.result_file`
3. Python 仍然没有越界：
   - Python 只负责 CLI/服务入口和结果归档
   - Claude 负责审核判断和记忆提炼

## 风险与遗留

- 当前真实审核结果已经稳定命中规则来源，但在 `audit-result` 的 `evidence_chain` 中仍未稳定写出 `memory:` 证据。也就是说，memory 已进入主链设计与提示约束，但在真实输出中还没有完全稳定体现为显式 memory source。
- `distill-memory` 当前通过 Claude 命令路径可用，但还未在 Python CLI/API 中暴露专门的结构化入口；这符合当前边界，但若后续要做管理面或批量沉淀，还需额外接口设计。
- 首条 memory asset 已存在于当前工作区，但 `knowledge/` 仍是默认忽略目录；若后续要做稳定版本化，需要再决定 memory 资产的入库策略。

## 下一步建议

- 进入 A-005：规则治理与追溯查询增强
- 优先做：
  - `knowledge/` 规则与 memory 资产校验
  - `claim_id / manual_review_reason / review_delta` 查询面
  - memory 来源说明在查询接口中的对外暴露
