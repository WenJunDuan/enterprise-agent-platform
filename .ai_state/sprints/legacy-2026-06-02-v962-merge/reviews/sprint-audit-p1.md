# Sprint Audit P1 自审 — ⚠️ 已撤销 / REVOKED

**撤销日期**：2026-04-20
**撤销原因**：P1 整体违反"Python 只做通信/鉴权/服务，业务全归 Claude"的脚手架原则。Python 不该知道"发票 / 规则 / 金额 / 签字节点"等业务概念，即使形式上是"数据搬运"也算越线。

**已删除的交付物**（由用户手动 rm 执行）：
- `server/audit/` 全目录（9 个 Python 文件）
- `server/prompts/audit_fast.md`
- `tests/test_audit_contracts.py` / `test_audit_intake.py` / `test_audit_extractor.py` / `test_rules_loader.py` / `test_amount_extract.py` / `test_approval_signatures.py` / `test_audit_fast_e2e.py`（7 个测试文件）

**已撤销的代码改动**：
- `server/api.py`：删除 `/audit/fast` 端点、`AuditFastRequest` 模型、`app_lifespan` 里的 `rules_loader.load_all_rules()` 钩子
- `server/command_adapter.py`：从 `PROMPT_VARIABLES` 删除 `audit_fast` 条目

**教训**：见 `.ai_state/lessons.md` "Python 越线 audit 业务" 条目。

**本文档内容仅作历史记录保留**，原始草稿如下：

---

# Sprint Audit P1 自审（已作废）

## 范围

实施 `.ai_state/todo-audit-refactor.md` 中的 P1.0 → P1.5。P1.6 按边界原则删除（风险分归 Claude 填）。

本轮由 Claude Code 直接手写，未在本环境跑 pytest / ruff / 启动服务。需用户本地验证。

## 本轮已完成

### P1.0 契约命名校准
- `AmountPreCheck` → `AmountExtraction`，删除 `variance_pct` / `exceeds_pre_approval`
- `ApprovalChain` → `ApprovalSignatures`，删除 `required_nodes` / `missing_nodes`，保留 `actual_signed`
- `PreCheckResult.amount_check` → `.amount_extraction`，`.approval_chain` → `.approval_signatures`
- `intake.py` 同步重命名；`REQUIRED_FORM_FIELDS` 对齐 `api.py`（删除 `amount`，改成 `case_id / applicant_name / expense_type`）
- `tests/test_audit_contracts.py` + `test_audit_intake.py` 同步更新

### P1.1 Extractor（骨架）
- 新增 `server/audit/extractor.py`：
  - `classify_attachment(path, filename) -> AttachmentKind` — 按文件名关键字（中/英文）粗分类
  - `build_file_meta(path) -> FileMeta` — 用 `mimetypes` 推断 MIME，`stat` 拿大小
  - `list_attachments(directory) -> tuple[FileMeta, ...]` — 目录扫描
  - `extract_invoices(attachments) -> tuple[ParsedInvoice, ...]` — **本轮是 stub**，返回 `()`
- 真实 PDF 解析（`pdfplumber`）留到后续迭代，依赖需用户先 `uv add pdfplumber`
- 新增 `tests/test_audit_extractor.py`（13 用例）

### P1.2 Rules Loader
- 新增 `server/audit/rules_loader.py`：
  - 启动时扫 `knowledge/expense/*.rules.json`，按 `category` 建内存索引
  - `is_ready() / loaded_categories() / total_rule_count()` 状态查询
  - `get_applicable_rules(category, applicant_role=..., city_tier=..., amount=...)` — 仅按 role 做**轻量**预筛（有条件且不匹配才排除；role 未知时保留所有规则，让 Claude 自行判断）
  - `reload_rules()` 热重载
  - 同时加载 `thresholds.json`（派生数值聚合）
  - 坏 JSON / 未知 category 不抛错，log 后跳过
- 在 `server/api.py` 的 `app_lifespan` 里加启动钩子 `rules_loader.load_all_rules(PROJECT_ROOT / "knowledge")`，失败记日志不阻塞启动
- 新增 `tests/test_rules_loader.py`（10 用例）

### P1.3 金额提取（Python 只读数）
- 新增 `server/audit/amount_extract.py`：
  - `extract_amounts(form, invoices) -> AmountExtraction`
  - 输出**只含** `invoices_total`（发票合计求和）/ `claim_total`（form 读）/ `pre_approval_total`（form 读，缺则 None）
  - **不**输出 variance / exceeds 等判断型字段
- 新增 `tests/test_amount_extract.py`（8 用例，含"契约字段数守卫"）

### P1.4 签字提取（Python 只列已签节点）
- 新增 `server/audit/approval_signatures.py`：
  - `extract_signatures(form, attachments) -> ApprovalSignatures`
  - 三种识别源：
    - 表单字段别名（`signed_by_lead` / `lead_approval` 等）
    - 嵌套 `approvals: [{"node": "finance", "signed": true}, ...]`
    - 附件文件名关键字（`领导签字` / `finance_sign` 等）
  - 输出**只含** `actual_signed: tuple[str, ...]`，按 `lead → division → finance → cashier` 规范顺序
  - **不**推导 required_nodes / missing_nodes（Claude 的活）
- 新增 `tests/test_approval_signatures.py`（11 用例）

### P1.5 主编排 + Fast 端点
- 新增 `server/prompts/audit_fast.md` — 明确告诉 Claude：金额偏差/审批合规/风险评分全部由 Claude 判断
- 新增 `server/audit/prompt_builder.py` — dataclass → JSON 序列化工具 + `build_fast_audit_prompt(ctx)`
- 新增 `server/audit/orchestrator.py`：
  - `run_fast_audit(case_path, tenant, request_id)` 串起 intake → 附件扫描 → 规则预筛 → 金额/签字提取 → build AuditContext → 单轮 Claude 调用 → 返回
  - `allowed_tools=[]`, `max_turns=1` 强制 Claude 单轮出结果
  - **守门短路**：当 `can_proceed_to_claude == False`，Python 直接返回 `manual_review` + `manual_review_reason`（仅枚举：`rule_gap` / `insufficient_evidence`），不调 Claude
  - `case_path` 必须在 `PROJECT_ROOT/data/` 下（防路径逃逸）
- `server/api.py` 新增 `POST /audit/fast`：
  - 入参 `{"case_path": "data/caseN"}`
  - 出参直接是审核结果 JSON + `X-Request-ID` header
  - 写入 `request_audit` 审计
- `server/command_adapter.py:PROMPT_VARIABLES` 增加 `"audit_fast": {"context_json"}`，启动时自动校验
- 新增 `tests/test_audit_fast_e2e.py`（5 用例）：
  - mock `run_agent_json`，断言 Claude 只被调 1 次、`allowed_tools=[]`、`max_turns=1`
  - X-Request-ID 响应头回写
  - 规则库空时直接 manual_review + `rule_gap`，不调 Claude
  - 非 `data/` 路径拒绝 400
  - 不存在目录拒绝 400

## 已知限制 / 遗留

1. **PDF 解析是 stub**：`extract_invoices()` 返回空 tuple，没真正读 PDF 文本。这意味着 Claude 在 fast 路径下看不到发票金额/号码等字段，只看到附件文件名和 form 里的 `amount`。真实场景下准确度受限，Claude 更可能输出 `manual_review`。要提升准确度需：
   - `uv add pdfplumber`
   - 实现 `extract_invoices()` 真正解析
2. **`get_applicable_rules` 只按 role 粗筛**：`city_tier` / `amount` 不做预过滤（不越界到判断层），所有候选规则都会塞进 prompt 交 Claude 判断。如果规则多（travel 有 26 条），token 消耗会较大。可在 P2 加语义筛选。
3. **Orchestrator 目前只接受 `case_path`**：不直接处理 multipart 上传。上传场景应先走 `/audit/submit` 落盘到 `data/submissions/{request_id}/`，再用那个路径调 `/audit/fast`。P2 可加一个包装端点。
4. **守门 reason 只用了 `rule_gap` / `insufficient_evidence`**：未覆盖全部 7 个枚举，其他类型（data_conflict / budget_exceeded 等）由 Claude 负责。
5. **TestClient 与 lifespan**：测试里 `TestClient(api_module.app)` 未显式 `__enter__`，lifespan 通常不触发；如果某次 CI 环境 Starlette 版本差异导致 lifespan 触发，会读真实 `knowledge/` 覆盖测试的 fake rules。若发现此类 flaky，需在 fixture 里 monkeypatch `api_module.app_lifespan`。

## 验收步骤（用户本地执行）

```bash
cd /Users/mi_manchi/workspace/enterprise-agent-platform

# 1. 跑所有新/改测试
uv run pytest tests/test_audit_contracts.py tests/test_audit_intake.py \
              tests/test_audit_result_schema.py tests/test_audit_extractor.py \
              tests/test_rules_loader.py tests/test_amount_extract.py \
              tests/test_approval_signatures.py tests/test_audit_fast_e2e.py -v

# 2. 全量回归
uv run pytest

# 3. ruff
uv run ruff check server/ tests/

# 4. 启动服务
uv run python -m server.cli serve

# 5. 冒烟测试 fast 端点
curl -X POST http://127.0.0.1:8000/audit/fast \
  -H "Authorization: Bearer <你的 TENANT_KEYS value>" \
  -H "Content-Type: application/json" \
  -d '{"case_path":"data/case1"}'
```

冒烟测试观察点：
- 响应头 `X-Request-ID`
- 响应体有 `verdict / conclusion / explanation`（Claude 真返的）
- 若 `verdict == "manual_review"`，应有 `manual_review_reason`
- 日志里 `audit_fast_completed` 或 `audit_fast_blocked_by_intake`

## Commit 建议

按 P 子项分 6 个 commit 或 1 个综合 commit，自选。综合版：

```bash
git add server/audit/ server/prompts/audit_fast.md server/command_adapter.py \
       server/api.py tests/test_audit_contracts.py tests/test_audit_intake.py \
       tests/test_audit_extractor.py tests/test_rules_loader.py \
       tests/test_amount_extract.py tests/test_approval_signatures.py \
       tests/test_audit_fast_e2e.py \
       .ai_state/design/audit-refactor.md .ai_state/todo-audit-refactor.md \
       .ai_state/reviews/sprint-audit-p1.md
git commit -m "[audit-p1] add fast-path orchestrator, rules loader, amount/signature extraction, /audit/fast endpoint"
```

## 交付清单

新增 10 个文件：
- `server/audit/extractor.py`
- `server/audit/rules_loader.py`
- `server/audit/amount_extract.py`
- `server/audit/approval_signatures.py`
- `server/audit/prompt_builder.py`
- `server/audit/orchestrator.py`
- `server/prompts/audit_fast.md`
- `tests/test_audit_extractor.py`（13）
- `tests/test_rules_loader.py`（10）
- `tests/test_amount_extract.py`（8）
- `tests/test_approval_signatures.py`（11）
- `tests/test_audit_fast_e2e.py`（5）

修改 5 个文件：
- `server/audit/contracts.py`（重命名 2 个 dataclass + 字段裁剪）
- `server/audit/intake.py`（字段重命名 + REQUIRED_FORM_FIELDS 调整）
- `server/api.py`（新增 `/audit/fast` + startup 钩子加载规则）
- `server/command_adapter.py`（`PROMPT_VARIABLES` 增加 `audit_fast`）
- `tests/test_audit_contracts.py` + `tests/test_audit_intake.py`（配合重命名）

新增测试合计 47 个（比 P0 的 34 个多一倍）。
