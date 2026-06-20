# Codex 代码评审 — tender 数据模型 Phase1 实现

> Reviewer: Codex CLI v0.141.0 (gpt-5.5) · commit `429bf5d` · 2026-06-20 · 100K tokens
> 命令: `codex exec -s read-only "$(< logs/codex-review/impl-instructions.txt)"`

## VERDICT: **REWORK**（2 P1 真 bug + 2 P2 测试盲区；happy path / 隔离 / 迁移 confirmed OK）

## P1（须修）

1. **retry 丢 project_id → 覆盖招标结论**（`server/routes/tender.py:336` retry 路径）
   - `POST /tasks/{id}/retry` 重排程时**未传 project_id**（默认 None）；worker 归档 `archive_result_payload(project_id=None)`。
   - 因 result 归档是 `INSERT OR REPLACE BY request_id`（result_store.py:122），retry 会把**原本 project-scoped 的结论 project_id 覆盖成 NULL** → 从 `/projects/{id}/results` 消失。
   - **修复**：retry 传 `project_id=record.get("group_id")` + 回归测试。

2. **空 `tender_no=""` 违反部分唯一索引 → 500**（`tender_project_store.py:133`）
   - `if tender_no:` 对 `""` 跳过查找 + 跳过 IntegrityError 兜底；但部分索引 `WHERE tender_no IS NOT NULL` 把 `""` 算入（"" 非 NULL）→ 重复 `""` 插入被拒 → 未兜底 → 500。
   - **修复**：函数入口 `tender_no = (tender_no or "").strip() or None`（"" → None 匿名，不入索引）。

## P2（测试盲区）
3. 新测试缺 route→worker→archive 透传不变量（fixture mock schedule no-op；recall 测试直接调 archive）。建议 spy `schedule_tender_evaluation_task` + worker 断言 project_id 转发 + retry 保留 group_id。
4. 无跨租户 project 访问测试（隔离逻辑在但无回归）。

## Confirmed OK（codex 明确排除）
- create/evaluate happy path：accept 时写 group_id；project_id 显式经 run_command_json→run_agent_json→archive_result_payload 透传。
- worker upsert 不含 group_id → `_coerce_record` 保留 accept 行的 group_id（仅当未来显式传 `"group_id": None` 才会被覆盖）。
- 迁移 ALTER 幂等；动态 SQL 表名/列名白名单或参数化。

## 处置（本轮 REWORK 修复）
- P1.1 retry 传 project_id：**已修** + 回归测试。
- P1.2 空 tender_no 归一：**已修** + 回归测试。
- P2.3/P2.4：worker 透传测试 + 跨租户测试 **已补**（部分先于 codex 完成时已加）。
- 另：cc-impl-review 独立发现的 P1（删任务后 `/tasks/{id}/result` 404、详情取不到）→ 已加 `GET /projects/{id}/results/{request_id}` 直读 results 修复 + 测试。
- 见 reviews/pass2 收口（本文件末）。
