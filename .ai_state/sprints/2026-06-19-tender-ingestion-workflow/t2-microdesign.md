# T2 Micro-Design · /tender/evaluate 路由 + worker

> 用户 2026-06-19 批准 **方案 A（新建 tender_task_store）**。本文为 T2 实施依据。
> 镜像源：`routes/audit.py` + `routes/audit_worker.py` + `stores/audit_task_store.py`。

## 核心决策：task store = 新建 `tender_task_store`（方案 A，已批准）

**关键发现**：`audit_tasks.mode` = `directory`/`upload`（提交模式），**不是**域标识；tender 提交模式也是
directory/upload。真正正交的轴是「域」。故 plan 里「`mode=tender` 区分」不准确（会和 worker/retry 依赖的
directory/upload 语义冲突）。

- **A 新建** `tender_tasks` 表，严格镜像 audit_task_store，**去掉 legacy backfill**（无 tender tasks.json）。✅
- B audit_tasks 加 `domain` 列复用 —— ❌ 动 item0 已加固的表、API 涟漪进 audit、违「新表 per domain」约定。
- C overload `mode=tender` —— ❌ 破坏 directory/upload 语义。

**理由**：对齐项目约定「统一库新表 per domain」（contract 也将如此）；域隔离干净；零触碰 audit 路径
（honors「不破坏既有接口」）。代价 ~150 行镜像重复 → **rule-of-three**：等 item2 contract-api 第 3 个
task store 出现时再抽公共基类（独立 refactor，现在抽会回 touch audit）。

## 结果归档：复用现成链路，零新表

worker 调 `run_command_json("evaluate-bid", case_path, schema_name=common/audit-result,
request_id=…, tenant=…, conversation_id=…)` → 内部 `run_agent_json` 已 `archive_result_payload(request_id,
tenant)`（json_bridge:199）。GET `/tender/tasks/{id}/result` 复用 `get_result_payload_by_request_id`。
`result_store` 域无关，不新建表。

## 文件清单（全部上层；不建 server/tender feature 模块）

| 文件 | 动作 | 镜像源 |
|---|---|---|
| `server/stores/tender_task_store.py` | 新建 tender_tasks 表 + upsert/get/list/delete + recover_stale_tender_tasks（删 backfill） | audit_task_store.py |
| `server/routes/tender.py` | POST /tender/evaluate(directory+multipart, verify_tenant) + GET /tender/tasks/{id} + /result，复用 upload_helpers | routes/audit.py |
| `server/routes/tender_worker.py` | 信号量+超时，调 run_command_json("evaluate-bid",…) | audit_worker.py |
| `server/api.py` | include_router(tender, prefix="/tender") + lifespan recover_stale_tender_tasks | 现有 audit 接线 |

## 分层

- tender route/worker → stores + common.command_adapter + platform：全下行，合法。
- tender 不 import ops → 不触发 ops/routes 层序冲突。T2.5（health.py→diagnostics 上向 import + 补守卫）
  与 T2 自身 import 独立，单独做。

## 独立调参（标书数据量大）

- `TENDER_TIMEOUT_SEC` 默认 600s（40MB+/~18 章节，S2 抽取慢）。
- `MAX_CONCURRENT_TENDER` 默认 1（单标已重）。

## 已知运行风险（非 T2 阻塞）

- structured 输出 qwen 后端可能不支持（离线仅跑通文本模式）。worker 默认 structured=True；e2e 失败则加
  `TENDER_STRUCTURED` toggle 走文本模式（T4 暴露）。

## 不做（本 T2，列 backlog）

- retry/delete/list 端点（plan 只要 POST evaluate + GET task + GET result 三个）。
- 多投标人 S5；T4 e2e。

## 验收（T2）

- `tests/test_tender_routes.py`（镜像 test_ocr_routes/test_routes_smoke）：提交→accepted、查任务、查结果、404。
- `test_routes_do_not_import_app_module` / `test_layering` 不退化。
- `uv run ruff check .` 全过。
