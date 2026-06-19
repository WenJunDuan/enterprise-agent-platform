# Contract 审查 + 合同库 Design（Phase 2a）

> Sprint 2026-06-19 · roadmap `contract-audit-platform` item2 · **Path: System** · 仅设计，待确认后 impl。
> 用户拍板（2026-06-19）：范围 = **审查 + 合同库**；驱动 = **内联命令 `/review-contract`**（对齐 expense/tender）。

## 背景

合同审计后端目前是 **greenfield**：只有 `contract-reviewer`(legal) agent 的 2 行 prompt，**无 legal 契约
schema、无 contract store、无路由**。`design-data-storage.md` 只有 `data/contracts/<id>/（未来合同库，C 设计）`
一行占位。本 sprint 把它做成：内联审查产 `common/audit-result` + 新建合同库持久化条款/付款节点，结论回链
`contract_id`，为后续「合同是否支持这笔付款」跨域引用打底（跨域回链本身留 v2，本 sprint 只建库不改 expense）。

## 方案（选定 + 备选对比）

**选定**：内联 `/review-contract`（AI 直读合同 → 事实底稿 → 匹配 legal 规则 → 风险/合规 → audit-result），
Python 侧把抽取出的合同结构持久化到 sqlite 新表 `contracts`，原件留 `data/contracts/<id>/source/`。

- 备选①「只审查不建库」：最快但无法支撑跨域引用——**未采纳**（用户要合同库）。
- 备选②「走 contract-reviewer agent 编排」：延迟高、与 expense/tender 内联演进不一致——**未采纳**。
- 备选③「合同结构由 Claude 侧用 Skill 直写库」：违背「Python 管持久化、Claude 管判断」分工——**未采纳**，
  改由 Python 在 run 后从 `audit-result.extracted_data.contract` 落库（与 result_store 归档同源）。

## 组件（改动面）

### 1. Legal 契约 schema（新建 `.claude/contracts/legal/`）
- `extract-result.schema.json` —— 合同事实底稿（镜像 expense/tender）：`contract_id` / `source_path` /
  `parties[]` / `contract_meta`(title, sign_date, amount, currency, term) / `clauses[]`(clause_id, type, text, page) /
  `payment_nodes[]`(node_id, name, amount, ratio, due_condition, due_date, page) / `attachments[]` /
  `ambiguities[]` / `reviewed_by` / `timestamp`。**内部底稿语义**，不作 structured output（同 tender 做法）。
- `review-delta.schema.json` —— contract-reviewer（默认关）的第二意见，镜像 expense/tender。
- **最终结论复用 `common/audit-result`**，不新建结论 schema（硬约束：schema 只动新建 legal/*）。

### 2. contract_store（新建 `server/stores/contract_store.py`）
- sqlite `contracts` 表入统一库 `platform.sqlite3`（store 机制镜像 `tender_task_store`）：
  `contract_id`(PK) / `tenant` / `title` / `parties`(JSON) / `sign_date` / `amount` / `currency` / `term` /
  `source_path` / `clauses`(JSON TEXT) / `payment_nodes`(JSON TEXT) / `meta`(JSON) / `created_at` / `updated_at`。
- 原件大 blob **留文件** `data/contracts/<contract_id>/source/`（遵 B1：结构化进表、blob 留文件）。
- 函数：`upsert_contract` / `get_contract` / `list_contracts` / `get_contract_admin`。
- **分层**：store 只 import platform（受 T2.5 新增 `test_stores_only_import_platform` 守卫约束）。

### 3. `/review-contract` 内联命令（新建 `.claude/commands/review-contract.md`）
- 五步对齐 tender：S0 清点 → S1 规则计划(legal 规则) → S2 抽取(extract-result 语义，含 clauses/payment_nodes) →
  S3 风险/合规评判 → S4 汇总 `audit-result`，把合同结构写进 `extracted_data.contract`，evidence_chain 引
  `contract_id` + clause/page。规则缺失 → `manual_review(rule_gap)`，不编造。

### 4. Python 持久化 + CLI（`server/cli.py` + 一个 thin 持久化函数）
- CLI `review-contract`(+`-json`) 镜像 audit/evaluate-bid：`run_command_json("review-contract", path,
  schema_name="common/audit-result")`（结论经 run_agent_json 自动归档 result_store）。
- run 后 thin 步骤：从 `audit-result.extracted_data.contract` 取结构 → `upsert_contract(contract_id, …)` +
  把原件 copy 到 `data/contracts/<id>/source/`。**Python 只搬运结构化产物，不做判断**（守 gotcha）。

### 5. 编排 / 文档
- `CLAUDE.md` legal 段：默认走 `/review-contract` 内联；`contract-reviewer` 保留特殊场景/第二意见。
- `contract-reviewer` agent：轻量加 legal schema 引用（不强制）。

## 影响范围

- **新增**：`.claude/contracts/legal/{extract-result,review-delta}.schema.json`、`.claude/commands/review-contract.md`、
  `server/stores/contract_store.py`、`platform/paths.py` 加 `CONTRACTS_DATA_DIR`、`server/cli.py` 加命令、
  `tests/test_contract_store.py` + `tests/test_cli_review_contract.py` + `tests/test_legal_contracts.py`。
- **改**：`.claude/CLAUDE.md` legal 段、`contract-reviewer.md`(轻)。
- **零改**：`routes/audit.py`/`routes/ocr.py`/`routes/tender.py`、common/expense/tender/ocr schema（硬约束）。
- 2b（item3 contract-audit-api）= HTTP `/contract/review` 路由，复用 tender 立的异步路由模板，**本 sprint 不做**。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 合同结构落库依赖 Claude 输出 `extracted_data.contract` 完整 | schema 校验 + 缺字段降级 manual_review；持久化容缺（部分字段 null） |
| common/audit-result.evidence_chain 是否容 contract_id 引用 | **待核**：impl 前确认 evidence_chain 形态够灵活（字符串引用），否则只在 extracted_data 回链 |
| System path 改动面大 | 分步 TDD + 即时 commit：schema → store → 命令 → CLI 持久化 → 文档；每步全量绿 + 分层守卫不退化 |
| OCR 已有合同付款节点抽取，重复 | 复用/对齐 OCR 的 payment_node 字段语义，不重造；本 sprint 以 review 为主、抽取走 review 命令 |

## 验收标准（DoD）

- [ ] legal 两契约存在可载 + manual_review_reason/verdict 枚举一致（镜像 T3 结构测试）。
- [ ] contract_store CRUD 测试绿；入统一库 `contracts` 表；store 只依赖 platform（分层守卫过）。
- [ ] `review-contract --help` 可见；`review-contract-json` 产 audit-result；持久化把 extracted_data.contract 落库 + 原件留文件（单测 mock 命令验证持久化路径）。
- [ ] `uv run pytest -q` 全绿 + `ruff` 全过 + `test_layering` 6 守卫不退化。
- [ ] System path：polish + 新建 `architecture/system-contract-audit.md`（ship 前）。

## 开放项 → 已决议（2026-06-19 核 schema 后定）

1. **evidence_chain 回链形态**：已核 `common/audit-result` evidence_chain item = `{source, finding,
   conclusion}` 且 `additionalProperties:false` → **不能加 contract_id 字段**（且硬约束禁改 common schema）。
   **决议**：contract_id 编进 `evidence_chain[].source` 字符串（如 `contract:<id>#clause-3 p.4`）+ 规范 id 放
   `extracted_data.contract.contract_id`（`extracted_data` 为 `additionalProperties:true`，自由）。零改 common。
2. **contract_id 生成**：**决议** = UUID（合同编号不可靠），每次审查生成；同合同去重留 v2。
3. **reviewed_by**：legal/extract-result 用 const `"contract-extractor"`（镜像 expense/tender 底稿命名约定）。
