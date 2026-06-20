# Server API 完整性 — tender 任务三件套对齐 audit + worker 加固

> Sprint 2026-06-20 · Path: **System**（server 路由 + worker + store）· 用户 2026-06-20 要求"全面检查 server 层 API/数据存储，把接口全部实现，为下个 sprint 前后端对接做准备"。

## 背景：server 层现状检查结论

- **数据存储层两域共用、已完整**：结果 → `result_store` SQLite `results.payload`（按 tenant+request_id，H4 隔离）；任务 → 泛型 `TaskStore` 的 `{域}_tasks` 表。回看/查看（list + get result）能力底座齐备。
- **缺口在 tender 路由没补齐三件套**：audit 有 submit/list/get/result/retry/delete + 准入闸 + to_thread；tender 只有 evaluate/get/result，**缺 list / retry / delete**，且 worker 未吃 backend-hardening 的 F4(to_thread)/F5(引用集+准入闸)。
- **前端**：`features/audit/api.ts` 已用满 audit 全套；无 `features/tender/`（下 sprint 建）。故本 sprint 把 tender **服务端**补到与 audit 对等，前端留待下 sprint。

## 方案：镜像 audit，最小新增

泛型 `TaskStore` 已含 `try_transition` / `delete_if_idle` / `list`，**无需改 store 逻辑**，只在 tender 薄封装层绑定 + 路由调用。

### 影响范围
- `server/stores/tender_task_store.py` — 绑定 `try_transition_tender_task` / `delete_tender_task_if_idle`（方法已存在于泛型类）。
- `server/routes/tender_worker.py` — 加固对等 audit_worker：`_BACKGROUND_TASKS` 引用集 + `_track_task`（F5 防 GC）、`admission_available()`（F5 准入）、所有 `upsert_tender_task` 包 `to_thread`（F4）。
- `server/routes/tender.py` — 新增 `GET /tasks`（列表）、`POST /tasks/{id}/retry`、`DELETE /tasks/{id}`；`POST /evaluate` + retry 加准入闸（满回 503）；submit 的 upsert 包 to_thread。
- `tests/test_tender_routes.py` — 补 list/retry/delete + 准入闸用例（镜像 audit 测试）。

### 不做（明确边界）
- 不加 result-history 端点（result_store.list_records 按 verdict/claim_id）：audit 也没有，加了会两域不对称、且超出"接口对齐"范围。需要时另案。
- 不改 agent-front（下 sprint 前后端对接时建 tender 前端）。
- 不改数据存储 schema（已够用）。

## 验收
- tender 路由与 audit 对等：list/retry/delete 行为一致（含并发 retry 仅一个成功、running 删不动回 409、队列满回 503）。
- `uv run pytest -q` 全绿 + ruff clean。
- 数据回看链路：submit → list（见历史任务）→ get result（取结论 payload）两域一致可用。
