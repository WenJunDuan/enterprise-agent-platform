# Contract 审查 HTTP API Design（Phase 2b / item3）

> Sprint 2026-06-19 · roadmap item3 · **Path: Feature**（纯加法，暴露 contract-feature 子系统）。
> 镜像 tender T2 异步路由模板（`routes/tender.py` + `tender_worker.py` + `tender_task_store.py`）。

## Goal

把 item2 的合同审查能力（`/review-contract` 内联命令）经 HTTP 异步任务对外：提交→轮询→取结果，
并在审查成功后复用 `persist_contract_from_result` 落库合同结构。既有路由零改。

## 方案（镜像 tender，复用 contract-feature）

| 组件 | 文件 | 镜像源 / 复用 |
|---|---|---|
| 审查任务状态 store | `server/stores/contract_task_store.py`（新建 `contract_review_tasks` 表） | 严格镜像 `tender_task_store.py`（域隔离，不复用 tender/audit 表） |
| HTTP 路由 | `server/routes/contract.py`：POST `/contract/review` + GET `/contract/tasks/{id}` + `/contract/tasks/{id}/result` | 镜像 `routes/tender.py` |
| 后台 worker | `server/routes/contract_worker.py`：信号量+超时，调 `run_command_json("review-contract",…)`，成功后 `persist_contract_from_result` | 镜像 `tender_worker.py` + 复用 contract_store 持久化 |
| 接线 | `server/api.py`：`include_router(contract, prefix="/contract")` + lifespan `recover_stale_contract_tasks` | 现有 tender/audit 接线 |
| 测试 | `tests/test_contract_routes.py`（提交→accepted/查任务/查结果/auth/404/415）+ 路由基线 | 镜像 `tests/test_tender_routes.py` |

## 关键点

- **任务状态 vs 合同库分离**：`contract_review_tasks`(本 sprint，任务状态机) ≠ `contracts`(item2，合同数据)。
  worker 成功后既更新任务表(completed + result_file)，又调 `persist_contract_from_result` 落合同库。
- **结果归档**：worker 调 `run_command_json` 透传 request_id/tenant → run_agent_json 自动归档 result_store；
  GET result 复用 `get_result_payload_by_request_id` + `enrich_audit_decision`。
- **分层**：route/worker 调 common.command_adapter + stores + platform；不建 server/contract feature 模块。
- **独立调参**：`CONTRACT_TIMEOUT_SEC`（默认 300s）、`MAX_CONCURRENT_CONTRACT`（默认 2）。

## 影响范围

- 新增：contract_task_store / routes/contract.py / contract_worker.py / test_contract_routes.py。
- 改：api.py（接线）、tests/test_routes_smoke.py（路由基线纳入 3 个 contract 路由）。
- 零改：routes/audit|ocr|tender；common/expense/tender/ocr/legal schema 不动。

## 验收（DoD）

- [ ] `tests/test_contract_routes.py` 绿（提交→accepted、查任务、查结果、auth/404/415、worker 转发+落库）。
- [ ] `uv run pytest -q` 全绿 + `ruff` 全过 + `test_layering` 6 守卫不退化 + 路由基线纳入 contract。
- [ ] 既有路由零改；不复活 meta.json/by-request 树。
