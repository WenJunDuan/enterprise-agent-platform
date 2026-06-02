# Audit 业务重构 — TODO Checklist（⚠️ 已作废）

**2026-04-20 撤销**：本清单 P1 / P2 / P3 全部作废。Python 不做任何业务 — 包括"数据搬运"都越线。审核流程走现有 `/audit` / `/audit/submit` agentic 路径即可，Claude 一手负责全部业务。

**仍有效的部分**（已 P0 落地）：
- `.claude/contracts/common/audit-result.schema.json` 新增 `manual_review_reason` + `risk_dimensions`
- `server/core.py:validate_structured_output_semantics` 对应守卫
- `server/prompts/audit.md` 规则 #7 补充
- `README.md` 新字段说明
- `tests/test_audit_result_schema.py` 契约守卫测试

其余 P1 条目（rules_loader / extractor / amount_extract / approval_signatures / orchestrator / `/audit/fast`）均已撤销，不再是 TODO。

以下内容仅作历史记录：

---

---

## P0 — 基础就绪（缺失会阻断后续所有工作）

### P0.1 规则库初始化
- [ ] 确认 `knowledge/external/数睿员工手册.pdf` 存在，缺则请用户提供
- [ ] 跑 `POST /init-rules` 或 CLI 等价命令，生成：
  - [ ] `knowledge/expense/general.rules.json`（§ 6.3 通用规则）
  - [ ] `knowledge/expense/invoice.rules.json`（§ 6.3.3/6.3.4 票据）
  - [ ] `knowledge/expense/loan.rules.json`（§ 6.4 借款）
  - [ ] `knowledge/expense/entertainment.rules.json`（§ 6.5 招待）
  - [ ] `knowledge/expense/travel.rules.json`（§ 6.6 差旅）
  - [ ] `knowledge/expense/transport.rules.json`（§ 6.7 交通）
- [ ] 人工抽查每个文件：`extracted_rule_count > 0`、`policy_refs` 可回溯到 PDF 章节
- [ ] 补 `knowledge/expense/thresholds.json`（派生，从上面 6 个文件聚合阈值类规则）
- **判据**：6 个 rules.json 全非空，`/init-rules` 返回 `status: initialized`，`extracted_rule_count` 合计 ≥ 30

### P0.2 AuditContext 契约落地
- [ ] 新建 `server/audit/__init__.py`
- [ ] 新建 `server/audit/contracts.py`，按设计文档第 3.1 节实现所有 dataclass：
  - `ExpenseCategory` (Enum)
  - `ApplicantInfo / ExpenseClaim / ParsedInvoice / FileMeta / Rule`
  - `AmountPreCheck / ApprovalChain / PreCheckResult / HistorySummary`
  - `AuditContext`
- [ ] 全部 `@dataclass(frozen=True, slots=True)`，类型注解完整
- [ ] 新增 `tests/test_audit_contracts.py`：构造每个 dataclass 的正常 + 缺字段场景
- **判据**：`mypy server/audit/contracts.py` 无错；dataclass 可 JSON 序列化（便于日志/传输）

### P0.3 受理预检（Step 1）
- [ ] 新建 `server/audit/intake.py`，实现 `run_intake(form: dict, attachments: list) -> PreCheckResult`：
  - 检查 `REQUIRED_FORM_FIELDS`（case_id / applicant_name / expense_type / amount）缺失
  - 检查附件 MIME 类型白名单（pdf/jpg/png/webp）
  - 调 `rules_loader.is_ready()` 检查规则库（若 P1.2 未完成，先 mock 为 `True`）
  - 返回 `PreCheckResult`，`can_proceed_to_claude = (form_complete and attachments_valid and rule_library_ready)`
- [ ] 新增 `tests/test_audit_intake.py`：缺字段 → `can_proceed=False`；缺附件 → 同；规则库空 → 同
- **判据**：表单缺字段时 intake 返回 `can_proceed_to_claude=False` 且 `missing_form_fields` 非空

### P0.4 Schema 扩展（审核结果）
- [ ] 修改 `.claude/contracts/common/audit-result.schema.json`：新增 `manual_review_reason` (enum) 和 `risk_dimensions` (array)，保持向后兼容（不放进 `required`）
- [ ] 修改 `server/core.py:validate_structured_output_semantics`：
  - 若 `verdict == "manual_review"` 且无 `manual_review_reason` → 抛 `JSONContractError`
  - 若 `risk_dimensions` 存在，校验 name 枚举和 0-10 范围
- [ ] 修改 `tests/test_audit_submit_attachments.py` 或新建 `tests/test_audit_result_schema.py`：覆盖新字段
- **判据**：老客户端（不传新字段）仍能通过；verdict=manual_review 无原因 → 报错

---

## P1 — 核心重构（真正降速 5→1）

### P1.1 资料数字化（Step 2）
- [ ] 在 `pyproject.toml` 加依赖：`pdfplumber>=0.11` 或等价，`Pillow` 已有
- [ ] 新建 `server/audit/extractor.py`：
  - `extract_pdf_text(path) -> tuple[str, list[TableData]]`（pdfplumber）
  - `extract_invoice_from_pdf(text) -> ParsedInvoice`（正则抓 invoice_no / amount / date / 抬头）
  - `extract_invoice_from_image(path) -> ParsedInvoice`（先预留接口，实现用 mock 或对接 OCR）
  - `classify_attachment(path, filename) -> FileMeta.kind`（基于文件名 + 内容关键字）
  - `build_parsed_invoices(attachments) -> list[ParsedInvoice]`
- [ ] 新增 `tests/test_audit_extractor.py`：准备几个 fixture PDF（可自制最小样本），断言抽取结果
- **判据**：一个标准发票 PDF 能抽出 invoice_no / amount / date 三个字段

### P1.2 规则预加载（Step 3）
- [ ] 新建 `server/audit/rules_loader.py`：
  - 模块级变量 `_RULES_INDEX: dict[ExpenseCategory, list[Rule]]`
  - `load_all_rules(knowledge_dir: Path) -> None`（启动调一次）
  - `get_applicable_rules(category, applicant_role, city_tier, amount) -> list[Rule]`（内存筛选）
  - `is_ready() -> bool`（规则库是否加载成功）
  - 支持热重载（`reload_rules()`），用于 `/init-rules` 后刷新
- [ ] 在 `server/api.py` 的 FastAPI startup event 调 `load_all_rules()`
- [ ] 修改 `/ready` 端点，返回 `rule_library_ready: bool` + `rule_categories_loaded: list[str]`
- [ ] 新增 `tests/test_rules_loader.py`：空目录、正常规则、损坏 JSON 三种场景
- **判据**：启动日志能看到"loaded N rules across M categories"；`/ready` 反映状态

### P1.0 P0 契约命名校准（P1 首个任务）
> 边界原则确立后（Python = bridge，Claude = auditor），P0 已 commit 的 `AmountPreCheck / ApprovalChain` 名字和字段反映的是判断型职责，需要重命名+字段裁剪。详见 `docs/design/audit-refactor.md` 第 6 节。

- [ ] `server/audit/contracts.py`：
  - `AmountPreCheck` → `AmountExtraction`，删除 `variance_pct` / `exceeds_pre_approval` 字段
  - `ApprovalChain` → `ApprovalSignatures`，删除 `required_nodes` / `missing_nodes` 字段，保留并重命名 `actual_nodes` → `actual_signed`
  - `PreCheckResult.amount_check` → `amount_extraction`，类型同步
  - `PreCheckResult.approval_chain` → `approval_signatures`，类型同步
- [ ] `tests/test_audit_contracts.py` 同步重命名，不再覆盖被删字段的场景
- **判据**：所有调用点（目前只有 `intake.py` 构造 stub None）编译通过；pytest 绿

### P1.3 金额提取（Step 4，Python 只提取数值）
> **边界**：Python 只从发票/表单/附件中提取原始数值；**是否偏差过大、是否超额** 由 Claude 判断。
- [ ] 新建 `server/audit/amount_extract.py`：
  - `extract_amounts(claim_form: dict, invoices: list[ParsedInvoice], attachments: list[FileMeta]) -> AmountExtraction`
  - 输出字段严格限于：`invoices_total`（发票金额合计，求和）、`claim_total`（从 form 读）、`pre_approval_total`（从事前审批附件读，缺则 None）
  - **不**输出 variance_pct / exceeds_pre_approval 等判断型字段
- [ ] 新增 `tests/test_amount_extract.py`：3 张发票求和正确、事前审批额缺失时为 None
- **判据**：纯数值，无业务判断；测试覆盖 extract 正确性

### P1.4 签字提取（Step 5，Python 只列已签节点）
> **边界**：Python 只从附件/表单里识别"谁签了字"；**应签谁、缺哪个节点** 由 Claude 对照规则判断。
- [ ] 新建 `server/audit/approval_signatures.py`：
  - `extract_signatures(form: dict, attachments: list[FileMeta]) -> ApprovalSignatures`
  - 输出：`actual_signed: tuple[str, ...]`（如 `("lead", "finance")`），识别规则基于附件文件名 + 表单签字字段
  - **不**推导 required_nodes 或 missing_nodes
- [ ] 节点命名沿用：`lead` / `division` / `finance` / `cashier`
- [ ] 新增 `tests/test_approval_signatures.py`：只签 lead、签齐全、空签字三种
- **判据**：输出仅事实性清单；不含"该签谁"

### P1.5 主编排 + Fast 端点
- [ ] 新建 `server/audit/prompt_builder.py`：
  - `build_fast_audit_prompt(ctx: AuditContext) -> str` — 把 AuditContext 序列化为紧凑 JSON + 中文指令
  - **prompt 明确告诉 Claude**：金额偏差、审批合规、风险评分都需要 Claude 自己判断和填写，Python 不会代算
  - 新建 `server/prompts/audit_fast.md` 模板
- [ ] 新建 `server/audit/orchestrator.py`：
  - `async def run_fast_audit(form: dict, attachments_dir: Path, tenant: str) -> dict`
  - 串起：intake → extractor → rules_loader.get_applicable_rules → amount_extract → approval_signatures → build ctx → Claude 单轮调用（`allowed_tools=[]`, `max_turns=1`）→ 归档
  - **不**调用任何加权算分函数（risk_score 由 Claude 填进 response）
  - 若 `pre_checks.can_proceed_to_claude == False`：直接返回 `manual_review` + `manual_review_reason`，不调 Claude
- [ ] 修改 `server/api.py`，新增 `POST /audit/fast`（同步）：入参同 `/audit/submit`，响应直接返回审核结果
- [ ] 新增 `tests/test_audit_fast_e2e.py`：mock Claude 响应，验证一次请求完成
- **判据**：调 `/audit/fast` 一次审核 Claude API 调用次数 = 1；Python 代码里没有"判断金额是否超标 / 哪个节点缺失 / 算 risk_score"的逻辑

### ~~P1.6 风险加权~~（删除）
> 原计划"Python 加权算 risk_score"违反边界原则，已删。`risk_score` 字段由 **Claude 直接在 response 里填写**，`risk_weights.yaml` 仅作为参考权重写入 prompt 给 Claude 参考。

---

## P2 — 质量与可观测

### P2.1 manual_review_reason 分类落地
> **边界**：Python 只在"不发 Claude"这一条路径上推导 reason（守门判断，不是业务判断）。一旦请求发给 Claude，reason 由 Claude 填。
- [ ] `server/audit/orchestrator.py`：在 `pre_checks.can_proceed_to_claude == False` 时推导 `manual_review_reason`（仅覆盖守门场景）：
  - `missing_form_fields` 非空 → `insufficient_evidence`
  - `rule_library_ready == False` → `rule_gap`
  - `attachments_valid == False` → `insufficient_evidence`
  - 其他 can_proceed=False 的组合 → `insufficient_evidence`（兜底）
  - **注意**：不再依赖 `approval_signatures.actual_signed` 或 `amount_extraction.pre_approval_total` 做判断推导——这些是业务判断，一旦通过守门就交给 Claude
- [ ] Claude 侧：在 `prompts/audit_fast.md` 中列出 7 个 enum，要求 manual_review 时必选
- [ ] 新增 `tests/test_manual_review_reason.py`：守门不通过的三种场景
- **判据**：`can_proceed=False` 时 Python 给出 reason；`can_proceed=True` 时 reason 完全由 Claude 决定

### P2.2 历史摘要（Step 8）
- [ ] 新建 `server/audit/history.py`：
  - `summarize_history(applicant_id: str, tenant: str, lookback_days: int = 90) -> HistorySummary`
  - 查 `result_store` 同申请人近 N 天结果
  - 计算 `frequency_z_score`（相对该租户全量均值）
- [ ] orchestrator 调用时传入 ctx
- [ ] Claude prompt 里新增"历史对照"段
- **判据**：同人 30 天内 5 次招待报销 → `frequency_z_score > 2`；Claude 能据此标 anomaly

### P2.3 可观测指标
- [ ] `server/platform/metrics.py`（新增，简单实现）：
  - `audit_requests_total{tenant, verdict}`
  - `audit_duration_seconds{tenant, path=fast|agentic}`
  - `audit_manual_review_reason_total{reason}`
  - `claude_api_calls_per_audit{path}`
- [ ] orchestrator 的各步骤完成打点
- [ ] 暴露 `GET /metrics`（Prometheus 格式，可选）
- **判据**：能从指标看到 `/audit/fast` 的 claude_api_calls_per_audit ≈ 1

---

## P3 — 架构收尾（可选）

### P3.1 Skill 合并
- [ ] 合并 `.claude/skills/common/evidence-chain` 和 `result-format` 为一个 skill
- [ ] 更新 `expense-auditor` agent 的依赖列表
- **判据**：老 `/audit` 回退路径仍通过

### P3.2 跨域钩子（按需）
- [ ] orchestrator 在差旅审核时可选触发 `attendance-checker`（通过 `ENABLE_CROSS_DOMAIN_HR=true` 开关）
- [ ] 高额合同相关费用可选触发 `contract-reviewer`
- **判据**：开关关闭时完全不触发；开启时 AuditContext 多一个 `cross_domain_evidence` 字段

### P3.3 老 `/audit` 下线决策
- [ ] `/audit/fast` 生产运行满 2 周，对比成功率
- [ ] 失败率 ≤ `/audit` 时，`/audit` 改为内部调用 `/audit/fast`（平滑迁移）
- [ ] 再过 2 周，`/audit` 标记 `deprecated`（响应头）
- **判据**：老客户端无感知迁移完成

---

## 最终验收

- [ ] P0 完成，`/ready` 显示 `rule_library_ready: true`
- [ ] P1 完成，`POST /audit/fast` 端到端通过，Claude API 调用 = 1 次
- [ ] P2 完成，可按 `manual_review_reason` 出报表
- [ ] 所有测试通过（`pytest`）
- [ ] `ruff check server/ tests/` 无新增告警
- [ ] `.ai_state/reviews/sprint-audit-refactor.md` 自审报告
- [ ] 新老 `/audit` 双轨跑 2 周，性能/成功率对比进 review

---

## 执行约束

1. **不改老 `/audit` 端点行为**（回退路径保留）
2. **不改 JSONL 日志目录结构**（只能扩展字段）
3. **TDD**：P1 / P2 每项先写测试再写实现
4. **每 P 子项独立 commit**：前缀 `[audit-p0.1]` / `[audit-p1.3]` 等
5. **不动** `.claude/agents/` 和 `.claude/skills/` 除非 P3 明确要求
6. **不 `git push`**
