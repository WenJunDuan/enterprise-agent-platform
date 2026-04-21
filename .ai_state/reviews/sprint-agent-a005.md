# A-005 自审：规则治理与追溯查询增强

## 结论

- VERDICT: PASS

## 本轮目标

- 把 request 查询索引从纯文件扫描升级为 SQLite
- 为 memory 资产建立查询索引
- 补齐 `/requests`、`/results`、`/memories` 的治理与追溯查询面
- 补齐 `review_delta` 的持久化与查询
- 给 rules / memory 资产增加可执行校验面

## 实际改动

- 新增 `server/stores/memory_store.py`
  - 从 `knowledge/memory/**/*.json` 构建 SQLite 查询索引
  - 提供：
    - `list_memory_records()`
    - `get_memory_record_by_id()`
    - `list_memory_records_by_request_id()`
- `request_store`
  - 改为 `JSONL 日志 + SQLite 查询索引`
  - 保留 `logs/service/requests/*.jsonl` 作为请求日志
  - 新增 `logs/service/requests/index.sqlite3` 作为查询索引
- `result_store`
  - 补 `verdict` / `manual_review_reason` 查询维度
  - 对已有 SQLite 文件做轻量 schema migration
- `api.py`
  - `/requests` 新增 `route` / `status`
  - `/results` 新增 `verdict` / `manual_review_reason`
  - `/results/{request_id}` 新增 `linked_memories`
  - 新增：
    - `GET /memories`
    - `GET /memories/{memory_id}`
- `cli.py`
  - `requests` 命令新增 `route` / `status`
  - `results` 命令新增 `verdict` / `manual_review_reason`
  - `result-detail` 增加 `linked_memories`
  - 新增：
    - `memories`
    - `memory-detail`
- `diagnostics.py` / `maintenance.py`
  - 存储健康与 storage report 已对齐到当前 SQLite + 文件混合存储
- 新增 `server/stores/review_delta_store.py`
  - `logs/review-deltas/index.sqlite3`
  - `logs/review-deltas/by-request/YYYY/MM/DD/{request_id}.json`
- 新增 `server/platform/asset_validation.py`
  - 校验 `knowledge/*/*.rules.json`
  - 校验 `knowledge/memory/**/*.json`
- `api.py`
  - 新增：
    - `GET /review-deltas`
    - `GET /review-deltas/{request_id}`
    - `GET /governance/assets`
- `cli.py`
  - 新增：
    - `review-deltas`
    - `review-delta-detail`
    - `validate-assets`

## 实际状态验证

- 真实工作区已创建：
  - `logs/service/requests/index.sqlite3`
  - `logs/sessions/index.sqlite3`
  - `logs/results/index.sqlite3`
  - `logs/knowledge/memory-index.sqlite3`
- 当前可观察到：
  - `request` 查询索引
  - `session` 查询索引
  - `result` 查询索引
  - `memory` 查询索引

## 测试

- 新增 `tests/test_sqlite_stores.py`
  - 验证 request/session/result SQLite store
  - 验证 legacy JSONL backfill
  - 验证 memory index
- 新增 `tests/test_query_surfaces.py`
  - 验证 `/requests` route/status 过滤
  - 验证 `/results` manual_review_reason 过滤
  - 验证 `/results/{request_id}` 的 `linked_memories`
  - 验证 `/memories` 与 `/memories/{memory_id}`
- 新增 `tests/test_review_delta_store.py`
- 新增 `tests/test_asset_validation.py`
- `uv run pytest` 通过，当前共 64 项
- `uv run ruff check server tests` 通过

## 为什么这版更对

1. 你前面明确提出“日志保留文件，查询适合 SQLite”，现在数据层已经按这个思路真正落地。
2. `knowledge/memory` 仍保留 JSON 文件作为 source of truth，但查询不再需要全盘扫文件。
3. `request/session/result/memory` 四类查询索引现在是一致的，后续治理和追溯会顺很多。

## 风险与遗留

- `review_delta` 查询面和存储已经就绪，但主审核链路还没有自动生成 reviewer 产物并归档，这意味着目前数据层已准备好，生产 review_delta 数量仍取决于后续多域/复核编排接入。
- `memory_store` 当前采取“查询时 refresh 索引”的策略，数据量小时很稳，后续如果 memory 资产规模变大，可以再优化成增量刷新。
- asset validation 目前以 schema + 命名/路径一致性为主，后续还可以继续增加更细的业务规则一致性检查。

## 下一步建议

- 进入 A-006：
  - 多域协同触发条件
  - reviewer 自动接入主链
  - review_delta 真正进入运行时业务闭环
