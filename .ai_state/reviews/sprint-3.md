# Sprint 3 Review — 通用表单 Intake 与复杂报销 UI

**Reviewer:** Codex mainline self-review  
**Date:** 2026-04-26  
**Path:** Feature  
**Scope:** `/audit/submit` upload contract, React reimbursement UI, docs/state sync

## Verdict

PASS（local gate）

## Contract Decision

Python serve 层不再拥有报销字段 schema。上传模式只负责：

- 鉴权与 `mode=upload` 传输外壳
- `form_json` 可选解析；传入时必须是 JSON object
- 普通 multipart 文本字段归档到 `fields`
- 0 个或多个附件落盘；只做安全文件名、非空文件、大小限制
- 将 `audit-request.json` 目录交给 Claude `/audit` command

不再校验 `case_id`、`applicant_name`、`expense_type`，也不再按业务扩展名白名单拒绝附件。

## Review Findings

| Area | Finding | Result |
|---|---|---|
| Backend contract | `server/api.py` 已删除业务必填字段 gate，新增通用字段归档和可选附件处理 | PASS |
| Regression tests | `tests/test_api.py` 与 `tests/test_audit_submit_attachments.py` 覆盖无 `form_json`、无附件、无固定字段、任意扩展名附件 | PASS |
| UI submit | `ui/src/api/client.ts` 改为 `unknown` payload + 可选 `File[]`，表单页不再阻断 0 附件提交 | PASS |
| UI richness | `SubmitExpense` 覆盖基础、金额、发票、差旅、招待、审批、异常、附件分类和 payload 预览 | PASS |
| List/detail | `TaskList` / `TaskDetail` 通过 `localStorage` 回显提交摘要，后端无摘要时仍降级可用 | PASS |
| Docs/state | README、design、plan、tasks、前端对接文档均同步为“Python 不校验业务字段” | PASS |

## Validation

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_api.py tests/test_audit_submit_attachments.py -q` → 15 passed
- `cd ui && npm run build` → passed
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → 97 passed
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` → All checks passed

## Known Limitations

- 任务列表/详情的业务摘要来自浏览器 `localStorage`；换浏览器或清缓存后只能显示后端紧凑任务字段。
- 当前 UI 是复杂报销模板，不是所有公司表单 schema 的统一标准；真正的字段语义仍由接入方表单和 Claude 侧审核能力决定。
- 独立 reviewer/sub-agent 未执行：当前工具策略只允许用户显式要求 sub-agent 后再 spawn。此处以主线自审 + 自动质量门作为本轮可执行 review。

