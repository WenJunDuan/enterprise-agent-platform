# Sprint 2 Code Review

**Reviewer:** Codex (research mode) + CC 交叉核对
**Date:** 2026-04-24
**Path:** Feature
**Scope:** ui/src/** (React frontend) + server/api.py (CORSMiddleware)

---

## Codex 原始发现

Codex 在 review 时读取到的文件与实际磁盘文件存在出入（幻觉），导致 3 条 HIGH 中有 2 条误报：

| 严重度 | 发现 | 适用于实际代码 | 处置 |
|--------|------|---------------|------|
| HIGH | 无 React ErrorBoundary | ✅ 真实 | 已修复：App.tsx 加 ErrorBoundary + 重试按钮 |
| HIGH | GET /audit/tasks 响应 shape 不匹配 | ❌ 误报（实际返回数组，非 wrapper） | 忽略 |
| HIGH | task_id 路径穿越 | ❌ 误报（实际用 JSON store，非文件路径） | 忽略 |
| MED | StatusBadge 未知 status 崩溃 | ❌ 已有 `??` 兜底 | 忽略 |
| MED | 无 404 路由 | ✅ 真实 | 已修复：App.tsx 加 `<Route path="*">` |
| MED | navigate(-1) 直链问题 | ❌ 实际用 Link 而非 navigate | 忽略 |
| LOW | 无 fetch 取消 | ✅ 真实但低优 | 遗留 |

## 实际修复（App.tsx）

1. 加入 `ErrorBoundary` class component，捕获页面渲染错误，显示中文错误信息 + 重试按钮
2. 加入 `NotFound` 组件 + `<Route path="*">` catch-all 路由

## 已验证正确的部分

- `client.ts`：fetch 封装，Bearer token 来自 `VITE_API_KEY`，正确 ✓
- `types/index.ts`：request_id / TaskStatus / AuditResult 与后端 schema 对齐 ✓
- `StatusBadge.tsx`：`??` 兜底，不会崩溃 ✓
- `TaskDetail.tsx`：3s 轮询 + cleanup + 结果展示完整 ✓
- `SubmitExpense.tsx`：multipart 构建方式与后端 API 合约一致 ✓
- `server/api.py` CORS：origins 显式列出，未用通配符 ✓

## Verdict: PASS（含修复）

## Codex 复核追加（2026-04-24 17:22）

当前原 PASS 结论撤回，原因如下：

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` 在 collection 阶段失败：`tests/test_store_capacity.py` 仍导入已删除的 `JSONLResultStore`。
- `cd ui && npm run build` 失败：`ui/src/api/client.ts` 使用 `import.meta.env`，但缺少 Vite 类型声明。
- `.ai_state/project.json` 仍处于 `impl`，说明尚未完成真实 review/ship gate。

临时 Verdict: REWORK（回到 impl 修复）。

## Codex 修复复核（2026-04-24 17:29）

### 修复内容

- `tests/test_store_capacity.py` 删除对已裁剪 `JSONLResultStore` 的导入与用例，避免恢复旧 JSONL result index 主路径。
- `ui/src/vite-env.d.ts` 新增 Vite 类型声明，修复 `import.meta.env` TypeScript 类型错误。
- `tests/test_api.py`、`tests/test_audit_submit_attachments.py` 收口上传契约：上传模式必须至少包含 1 个 `files` 附件；`application/x-www-form-urlencoded` 继续返回 415。
- `tests/test_health_endpoints.py` 对齐当前 `/health` compact payload：`app_server` 只暴露 `ok/running`，不泄露内部 `record`。
- `README.md` 与 `.ai_state/docs/前端审核服务对接文档.md` 同步“上传至少 1 个附件”的前端契约。
- `tests/test_api.py`、`tests/test_audit_task_store.py`、`tests/test_result_store.py` 清理 ruff 未使用导入。

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`：96 passed
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`：All checks passed
- `cd ui && npm run build`：通过

## Verdict: PASS（local gate）

说明：本轮已完成主力自审与本地 gate。Feature+ 的独立 reviewer / 内置 review 记录仍建议在进入 ship 前补齐。

## Review Closure（2026-04-26）

### Scope Rechecked

- HTTP public surface is limited to `/health`, `/audit/submit`, `/audit/tasks`, `/audit/tasks/{request_id}`, and `/audit/tasks/{request_id}/result`.
- CLI retains query/governance surfaces; HTTP does not expose `/requests`, `/results`, `/memories`, `/review-deltas`, `/governance/assets`, `/chat`, `/audit`, or `/init-rules`.
- Frontend contract uses `VITE_API_BASE` and `VITE_API_KEY`, matching `ui/src/api/client.ts`.
- Upload mode requires at least one `files` part; docs, tests, and UI validation now agree.
- `.ai_state/init.sh` exists and reports project/stage/sprint/tasks without mutating source state.

### Review Method

- Mainline self-review inspected route inventory, docs, task state, UI env contract, ignored artifacts, and build outputs.
- Independent sub-agent review was not spawned because the current Codex tool policy only allows sub-agents when the user explicitly asks for delegation/sub-agents. This was treated as a review-protocol degradation, not a blocker.
- No ECC/System scan was run because Sprint 2 is Feature path, not System path.

### Final Gate Commands

- `bash .ai_state/init.sh`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`
- `UV_CACHE_DIR=/tmp/uv-cache uv build`
- `cd ui && npm run build`
- `git diff --check`

## Verdict: PASS（ready for ship）

Remaining non-code action: user-controlled commit / PR, because this agent must not commit unless explicitly requested.
