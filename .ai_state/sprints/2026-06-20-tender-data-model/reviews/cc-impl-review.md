# CC (Claude) 代码评审 — tender 数据模型 Phase1 实现

> Reviewer: Claude(主实现方自审，独立维度) · commit `429bf5d` · 2026-06-20 · 配套 codex-impl-review.md

## VERDICT: **CONCERNS（1 个 P1 须修 + 2 个测试盲区，核心正确）**

325 passed/ruff。数据模型/隔离/迁移/幂等核心正确；下列 1 个 P1 半残了 P1.1 回看价值，建议进 Phase2 前修掉。

## 一、正确性核对（通过）

- **名册合并**（`_project_bid_roster`）：results(completed,durable) 先入 seen，tasks 后入且跳过 `rid in seen | status==completed` → 去重正确；删任务后已完成投标人仍从 results 显示（P1.1 已回归测试）。✓
- **project_id 透传链**：route→schedule→execute→_execute_inner→_run_evaluation→run_command_json→run_agent_json→archive_result_payload，全程显式参数（非 `**opts`，不会进 build_options）。✓
- **group_id 保留**：route accept 时设 `group_id=project_id`；worker/retry 的 upsert 不含 group_id key → `_coerce_record` 合并保留，不会被 None 覆盖。✓
- **幂等建 project**：`immediate=True` 写锁内 check-then-insert + IntegrityError 兜底；并发序列化，第二方读到现有。✓
- **租户隔离**：5 端点全部 `get_project(id, tenant)` / `list_*(tenant, ...)` 作用域；跨租户取 project → get_project 返回 None → 404。✓
- **迁移幂等**：task_store/result_store 均 PRAGMA 检查 + ADD COLUMN if missing；audit_tasks 多一空 group_id 列无害。✓

## 二、🔴 P1（须修：半残 P1.1 回看）

**`GET /tender/tasks/{id}/result` 删任务后 404，导致回看详情取不到。**
- `tender_task_result`（routes/tender.py）先 `get_tender_task(id, tenant)`，None → 404；再查 `tender_tasks.status==completed`。
- 但 P1.1 的核心是"删任务后结论仍在 results"。删任务后：`GET /projects/{id}/results` 列表显示摘要 ✓，**但点进去取完整结论(criteria/scoring/evidence) → 404**（任务没了），回看在详情层断链。
- **修复建议**：加 `GET /tender/projects/{project_id}/results/{request_id}`，直接读 `results.payload`（tenant+project 双作用域，`enrich_audit_decision` 归一），**不依赖 tender_tasks 存在性**。这样删任务后完整结论仍可取。
- 严重度 P1：不阻断主流程，但 P1.1（回看独立于删除）只做了一半——列表独立了，详情没独立。

## 三、P2（测试盲区，建议补）

1. **worker project_id 透传未端到端测**：测试里 `schedule_tender_evaluation_task` 被 mock no-op，`test_results_recall` 直接调 `archive_result_payload(project_id=pid)`——透传链(worker→run_command_json→archive)若断，测试抓不到。建议：扩 `test_worker_forwards_to_evaluate_bid_and_persists`，传 project_id 并断言转发到 run_command_json 的 opts 含 project_id。
2. **跨租户访问 project 未测**：租户 B 不能见/评/查租户 A 的 project（应 404）——隔离逻辑在但无回归。建议补一例。

## 四、明确排除
- 无硬编码密钥；表名/列名经白名单（`_SAFE_TABLE` / `_FIELDS`），无注入。
- legacy NULL project_id 的旧结论不会混入 `list_results_by_project`（按具体 project_id 过滤）。
- DRY：`_submit_bid_evaluation` 抽出 /evaluate 与 /projects/{id}/evaluate 共用，无重复。
