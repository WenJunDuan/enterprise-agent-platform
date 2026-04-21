# Sprint Audit P0 自审

## 范围

实施 `.ai_state/todo-audit-refactor.md` 中的 P0.2 / P0.3 / P0.4 三项。P0.1（规则库初始化）由用户手动完成（`knowledge/expense/*.rules.json` 已就绪，69 条规则跨 6 个类别，质量已核对）。

本轮**由 Claude Code 直接手写完成**，不走 codex 后台派发（前一次派发 rescue agent 未实际执行 shell）。因 Claude Code 无 Bash 工具，**测试未在本环境运行**；用户需本地跑 `pytest` 验证。

## 本轮已完成

### P0.2 AuditContext 契约
- 新增 `server/audit/__init__.py`（模块文档）
- 新增 `server/audit/contracts.py`：11 个 `frozen=True, slots=True` dataclass
  - `ExpenseCategory` Enum（invoice/travel/entertainment/loan/transport/general）
  - `FileMeta / Rule / ApplicantInfo / ExpenseClaim / ParsedInvoice`
  - `AmountPreCheck / ApprovalChain / HistorySummary / PreCheckResult`
  - `AuditContext` 聚合根
- `Rule` 字段**对齐 knowledge/_schema/rule.schema.json 实际定义**：
  - action enum 为 `approve / reject / escalate`（原设计里错写成 require/forbid/threshold 已更正）
  - 补齐 `description / confidence / notes / source_title / source_excerpt`
  - `category` 从文件顶层下沉到每条 rule
- 集合类字段统一用 `tuple[..., ...]`（而非 `list`）以保证 frozen dataclass 的真实不可变
- 新增 `tests/test_audit_contracts.py`（15 个用例，覆盖构造、不可变、缺字段异常）

### P0.3 受理预检
- 新增 `server/audit/intake.py`：
  - `REQUIRED_FORM_FIELDS = ("case_id", "applicant_name", "expense_type", "amount")`
  - `ALLOWED_MIME_TYPES = {pdf, jpeg, png, webp}`
  - `_rule_library_ready()` 本轮占位返回 `True`，含 TODO 注释等待 P1.2 替换
  - `amount_check` / `approval_chain` 本轮返回 `None`（P1.3 / P1.4 实现）
  - `run_intake(form, attachments) -> PreCheckResult`
- 新增 `tests/test_audit_intake.py`（8 个用例）：
  - 完整表单 + 合法附件 → `can_proceed_to_claude=True`
  - 缺 `amount` / 空串 `case_id` / `None` `applicant_name` 都算缺失
  - `image/gif` 附件触发 `attachments_valid=False` 并记录路径
  - 无附件时仍允许放行（附件非强制）
  - stub 字段（`amount_check` / `approval_chain`）确实为 None

### P0.4 Schema 扩展
- 修改 `.claude/contracts/common/audit-result.schema.json`：
  - `properties` 新增 `manual_review_reason`（enum 7 值）
  - `properties` 新增 `risk_dimensions`（array of `{name enum, score 0-10}`）
  - 两字段**不加入 `required`**，老 payload 完全兼容
- 修改 `server/core.py:validate_structured_output_semantics`：
  - `verdict == "manual_review"` 时必须含合法 `manual_review_reason`，否则抛 `JSONContractError`
  - `risk_dimensions` 存在时校验：
    - 必须是 list
    - 每项必须是 object
    - `name` 必须在 5 个枚举内
    - `score` 必须是 int（显式排除 bool，bool 在 Python 里是 int 子类）且 0 ≤ score ≤ 10
- 新增 `tests/test_audit_result_schema.py`（11 个用例）：
  - 老 payload（无新字段）通过
  - manual_review 合法 reason 通过
  - manual_review 缺 reason / 非法 reason 抛错
  - risk_dimensions 非 list / 非 object item / score 11 / -1 / 5.5 / 非法 name 抛错
  - approved payload 含 manual_review_reason 字段（误给）仍通过

## 对原计划的校正

1. **Dataclass 集合字段用 tuple 而非 list**：为了真正不可变（frozen=True 不阻止 list 内部 mutate）。调用方拿到的 `ctx.attachments` 可直接索引/迭代，只是不能 `.append()`，这是设计意图。
2. **intake.py 接受 `Sequence[FileMeta]`**（包含 list 和 tuple）：避免强制调用方转 tuple。`run_intake` 内部只做 iteration，不 mutate。
3. **Rule action enum 更正**：设计文档里 `require/forbid/threshold/require_approval` 是我之前想当然的归类，**实际 rule.schema.json 定义的是 `approve/reject/escalate`**。已更正设计文档和实现。
4. **risk_dimension score 严格整数**：JSON Schema 定义 `type: integer`，但 JSON 解析后在 Python 里可能出现 `bool`（`True is 1`）。validator 显式 `isinstance(score, bool)` 排除，避免 `True` 被当 1 通过。
5. **测试数**：实际 34 个（15+8+11），原 todo 未给数值要求，仅要求覆盖列出场景，已全覆盖。

## 风险与遗留

1. **未运行 pytest**：Claude Code 本地无 Bash 工具。用户需：
   ```bash
   cd /Users/mi_manchi/workspace/enterprise-agent-platform
   uv run pytest tests/test_audit_contracts.py tests/test_audit_intake.py tests/test_audit_result_schema.py -v
   uv run ruff check server/ tests/
   ```
   若失败需反馈错误。
2. **未执行 git commit**：按 handoff 要求应每个 P 独立 commit 前缀 `[audit-p0.X]`，本轮仅完成代码编写，commit 由用户手动或后续批量执行。
3. **intake 的空 form / 空 attachments 边界**：当前测试覆盖缺字段/非法 MIME；**未测试** form 为 `{}` 或 `None` 的极端情形。`run_intake(None, [])` 会在迭代时 AttributeError；保守做法是调用方保证非 None，但可在 P1 主编排里加入口守卫。
4. **P1 依赖**：`intake._rule_library_ready()` 占位 True；当 P1.2 `rules_loader` 落地后需替换，并在此时新增一个测试覆盖"规则库未就绪 → can_proceed=False"。

## Review 发现并修复的问题（commit 前）

1. **Prompt 与新 schema 不对齐（关键）**：`server/prompts/audit.md` 原本不提 `manual_review_reason` 字段，但新 validator 要求 verdict=manual_review 时必须带合法 reason。老 `/audit` 端点会被直接拒掉。
   - **已修**：在 audit.md 规则 #7 后追加 `manual_review_reason` 枚举说明，7 个原因全部列出，让 Claude 知道要填。
   - 未新增 prompt 模板变量占位符，`validate_prompts()` 的 `PROMPT_VARIABLES["audit"] = {"path"}` 依然匹配。
2. **city_tier 类型收紧**：设计文档写的是 `Literal[1, 2, 3] | None`，实现里丢成 `int | None`。
   - **已修**：新增 `CityTier = Literal[1, 2, 3]` 类型别名，`ExpenseClaim.city_tier: CityTier | None`。测试用 `city_tier=1` 和 `None` 两种已覆盖。

## 已知遗留（不 block commit）

1. `Rule.conditions: dict[str, Any]` 保持松散 — P1.2 rules_loader 实施时再决定是否抽 `Conditions` 子 dataclass。
2. Validator 里 `valid_reasons` / `valid_dim_names` 与 schema 硬编码重复 — 有漂移风险，P2 可抽常量。
3. `intake.run_intake` 未接 `logger` — P2.3 可观测性指标落地时一起补。
4. `PreCheckResult` 没有 `suggested_manual_review_reason` 字段 — P2.1 orchestrator 里做 reason 推导时按需扩展。

## 用户决策

**Commit 粒度**：用户选择**一个综合 commit**（而不是按 P 拆 3-4 个）。

## 2026-04-20 补记 — P0 的 server/audit/ 部分随 P1 一起撤销

P1 被认定违反脚手架原则（Python 不得碰业务），连带 P0 的 `server/audit/contracts.py` + `intake.py` 也一并撤销（它们引入了"发票 / 规则 / 签字节点"等业务概念）。只保留真正属于 IPC 契约的改动：schema 扩展 + validator 守卫 + prompt 指令 + README 文档。

**最终保留的 P0 交付物**：
- `.claude/contracts/common/audit-result.schema.json`（新增 `manual_review_reason` / `risk_dimensions`）
- `server/core.py:validate_structured_output_semantics`（两段新校验）
- `server/prompts/audit.md`（规则 #7 补充 enum 指令）
- `README.md`（新字段说明）
- `tests/test_audit_result_schema.py`（验证上述契约，11 用例）

## 验证（待用户执行）

```bash
# 1. 运行契约测试
uv run pytest tests/test_audit_result_schema.py -v

# 2. ruff 检查
uv run ruff check server/ tests/

# 3. 完整回归（确认没破坏已有测试）
uv run pytest

# 4. 一个综合 commit（P1 撤销后的最终形态）
git add .claude/contracts/common/audit-result.schema.json server/core.py server/prompts/audit.md \
        README.md tests/test_audit_result_schema.py \
        server/api.py server/command_adapter.py \
        .ai_state/design/audit-refactor.md .ai_state/todo-audit-refactor.md \
        .ai_state/reviews/sprint-audit-p0.md .ai_state/reviews/sprint-audit-p1.md \
        .ai_state/lessons.md
git commit -m "[audit-p0] extend audit-result schema with manual_review_reason / risk_dimensions; hold Python at bridge-only"
```

## 交付清单（P1 撤销后最终）

**新增 1 个文件**：
- `tests/test_audit_result_schema.py`（契约守卫测试，11 用例）

**修改 4 个文件**：
- `.claude/contracts/common/audit-result.schema.json`（+`manual_review_reason` + `risk_dimensions`，不入 required）
- `server/core.py`（validator 增加两段校验）
- `server/prompts/audit.md`（规则 #7 末尾补 7 个 `manual_review_reason` 枚举）
- `README.md`（返回字段新增说明）

**曾新增但已撤销（详见 lessons）**：
- `server/audit/__init__.py` / `contracts.py` / `intake.py` — 业务越线
- `tests/test_audit_contracts.py` / `test_audit_intake.py` — 随之撤销

**设计文档同步 2 个**（均已标注 P1 撤销）：
- `.ai_state/design/audit-refactor.md`
- `.ai_state/todo-audit-refactor.md`
