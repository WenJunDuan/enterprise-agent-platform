# Explore · server/ 使用面（reachability）审计——文件级零死代码，肥肉在函数级

- 日期: 2026-08-17
- 类型: explore
- 方法: 从全部真实入口（Dockerfile CMD `uvicorn server.api:app`、`server.cli` 24 子命令、
  `server.app_server`、OCR 子进程 `python -m server.ocr.page_render_worker`、`python -m server.ocr`、
  .claude 接触面、agent-front api.ts）做 import/调用链追踪，54 处 tender 内部 import 逐符号核实使用次数。

## 结论

| 指标 | 数量 |
|---|---|
| server/ 总 .py | 111 个 / 24,945 行 |
| HTTP 生产链可达 | 97 个（87%） |
| 仅 CLI/运维入口 | 9 个（cli、app_server、ocr/__main__、credit_api、maintenance、source_proxy、migrate、override_store、review_delta_store） |
| 仅测试+文档引用（**有意**的离线回归闸，勿删） | 2 个：`server/audit/eval.py`、`server/tender/eval.py` |
| **文件级零引用死代码** | **0** |

`server/tender/` 25 个文件全部在评标主链 `doc_pipeline → runner → {doc/evidence/budget/criteria/rules context}` 上，无僵尸 import。

## 函数级孤儿（全仓唯一出现点=定义处；待 review 收口后清理）

- `server/stores/request_store.py`：`append_request_audit` / `list_request_audits` / `get_request_audit_by_request_id`（非 `_admin` 孪生）
- `server/stores/review_delta_store.py`：`archive_review_delta_payload` / `list_review_delta_records` / `get_review_delta_record_by_request_id` / `get_review_delta_payload_by_request_id` / `describe_review_delta_store`
- `server/stores/result_store.py:425 list_result_records`、`memory_store.py:248 list_memory_records_by_request_id`、`tender_project_store.py:205 update_project_status`、`server/ocr/runner.py:456 run_doc_extract`
- `override_store` 的 `get_override`/`list_pending_overrides`/`mark_distilled` 仅测试引用——`/distill-memory` 文档说"由平台 mark_distilled 标记"但无代码调用，**复利回路只落了写端**（接线 or 删，待拍板）

## 其他待拍板

- 前端已不调用的 legacy 路由：`POST /tender/evaluate`、`GET /tender/tasks`（`routes/tender/tasks.py:206,216`；同文件其余 4 条在用，不能整删）
- `.claude/hooks/review-output.py` 未注册但是 CLAUDE.md 载明的**有意停用件**（重开复核先重注册），不是孤儿，不动

## .claude ↔ server 接触面（仅 5 点）

① `ocr-page/ocr.py` in-process import `server.ocr.pipeline`；② `agent_bridge.py` PreToolUse Bash 白名单闸（只放行 ocr-page 前缀）；③ `multi-ocr` skill → `python -m server.ocr`；④ SDK 调 slash command：`tender-evaluate`(runner:288)/`tender-extract-info`(doc_pipeline:270)/`tender-compare`(compare_worker:125)/`audit`+`init-rules`(仅 CLI)；⑤ `contract.py` 从 `.claude/contracts/` 加载全部 schema。`.claude` 资产零 HTTP 调用。
隐式耦合一处：`audit.md:10` 要求 Read `server/audit/runner.py` 取 `AUDIT_INSTRUCTIONS`——迁移该提示词进 .claude 时一并解除（已排队）。
