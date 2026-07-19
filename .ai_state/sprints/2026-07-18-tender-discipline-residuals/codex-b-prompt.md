你在一个隔离 git worktree（分支 `d11-batch-b`，从 main HEAD 拉出）里工作。任务：实现 D11「tender 判分纪律残留收口包」的 **Batch B（服务端确定性）**，严格 TDD。**只在本 worktree 改动，绝不 push，绝不碰 main 分支。**

## 先读上下文
- 设计全文：`.ai_state/sprints/2026-07-18-tender-discipline-residuals/design.md`，重点读「## 批次 B」节 + 文末 Round1 critic 应答表（F3/F4/F5/F7/F8 与 Batch B 相关）。
- 代码规范：DRY/SRP，函数 ≤40 行，禁 magic number，公开 API 加 type hints + docstring；异常只在信任边界处理，禁吞异常/空 catch。
- 测试：`uv run pytest -q <目标测试文件>`（**用目标文件，别跑全量套件**——OCR 测试缺 fitz 会失败，是环境既有，与本任务无关）。lint：`uv run ruff check .`。若首次 `uv run` 报缺依赖，跑 `uv sync --extra ocr`（**不要**跑纯 `uv sync`，会卸 pypdf/openpyxl/docx）。
- **只允许改**：`server/tender/output.py`、`server/platform/config.py`、`.claude/contracts/common/audit-result.schema.json`、`tests/` 下相关文件。**不改** `server/tender/evidence.py` 逻辑（只复用其 `_hit_moves_score`），**不改**共享 `_DEFAULT_REVIEWED_BY`。

## 三任务（每个 TDD red→green，单独 commit，conventional commits `feat(tender):`/`fix(tender):`，不 push）

### TB1 / F04 · evidence_chain 顶层派生 — `server/tender/output.py:enrich_tender_result`（约 :570）
- **RED 先写测试**：顶层 `evidence_chain` 空 + `scoring[]` 含带非零分 `award_hits`/`deduction_hits` → 断言派生 `{source, finding, conclusion}` 条目，**保留【第N页】页锚**。
- **空链精确定义**：`None` / 缺字段 / `[]` / 或经 `_normalize_evidence_chain` 拍平后所有条目 `source+finding+conclusion` 全空串。
- **GREEN**：`enrich_tender_result` 加派生逻辑，复用 `server/tender/evidence.py:_hit_moves_score`（判「带非零分命中优先」）。
- **关键正确性**：派生在 resolve 闸**之前**（顺序 normalize→schema→validate→enrich→resolve）；派生条目会被同次 resolve 标 `resolution` 字段，但降级只挂 `scoring[]`（`_check_hits`/`_downgrade_scoring_item`），所以派生条目即便被标 unresolved **不得改 verdict/scoring**——必须有断言。
- **5 断言**：①空链派生（含全空串假非空）②非空链不覆盖 ③无 scoring 安全跳过 ④页锚保真 ⑤unresolved 派生条目不改 verdict/scoring。

### TB2 / R5 · schema 与语义对齐
- **TB2a**：`output.py:normalize_tender_result`（约 :534）在调用共享 normalize 后覆盖 `reviewed_by="tender-evaluator"`；**不改**共享默认值。断言：tender 盖章正确 + expense 相关现有测试全绿（回归）。
- **TB2b**：编辑 `.claude/contracts/common/audit-result.schema.json` 的 `manual_review_reason` enum（当前 missing_approval/rule_gap/data_conflict/insufficient_evidence/budget_exceeded/invoice_invalid）。加法式扩展，值**以 `.claude/CLAUDE.md` tender 节实际用到的枚举为准**（先 `grep manual_review_reason .claude/CLAUDE.md` 看用到哪些值，缺哪个补哪个，如 `pre_approval_mismatch`——**别臆造**）。补 tender 场景断言该 reason 过 schema 校验。
- **TB2c**：`policy_refs_detail` 已于历史 commit `d26d90d` 实现于共享 `enrich_audit_decision`——只需补 1 个 tender 回归测试确认对 tender 结果也生效（近零工作量）。

### TB3 / R6 · config 收口 — `server/platform/config.py`
- **INFRA-01**：定位 `TENDER_TIMEOUT` 与 OCR 云等待超时的实际读取点，在配置加载时校验「OCR 等待 ≤ 0.5 × TENDER 超时」，否则 `logging.warning`（**只警告不硬拒**）。单测断言警告在越界触发、边界内不触发。
- **INFRA-02**：cache v2 首跑重跑 OCR 的部署提示——README/runbook 注记一句 + 启动日志一行。

## 验收 + 产出
- 每 TB：目标测试全绿 + `uv run ruff check .` 净 + 单独 commit。
- 完成后跑相关测试模块汇总（用实际存在的文件，如 `tests/test_tender_output.py`、`tests/test_contract*.py`、`tests/test_tender_eval.py`），报告绿/红。
- 最终结论写明：做了什么、每 commit 的 SHA + message、测试结果、任何 blocked 项及原因。
- **遇到设计与代码不符、或某项无法诚实完成：停下如实报告，不编造测试、不跳过断言。**
