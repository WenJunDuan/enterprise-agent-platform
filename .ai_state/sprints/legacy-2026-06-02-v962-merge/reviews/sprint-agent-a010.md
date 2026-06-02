# A-010 自审：删除 `/ready` 与 `inspect`，统一到 `health + doctor`

## 结论

- VERDICT: PASS

## 本轮动机

用户明确反馈当前探针和诊断入口过多：

- `/health`
- `/ready`
- `app-server inspect`
- `app-server doctor`

其中 `/ready` 与 `inspect` 的职责已经可以被现有 `health` 与 `doctor` 覆盖，继续保留只会增加理解和维护成本。

## 实际改动

- 更新 `server/api.py`
  - 删除 `/ready`
  - `/health` 现在在 `status != ok` 时返回 `503`
  - `/health` 继续返回精简摘要：`status + app_server + failing_checks + advisories`
- 更新 `server/app_server.py`
  - 删除 `inspect`
  - `doctor` 去掉 `--require-ready`
  - `service_http` 只保留 `health` 探测
- 更新测试
  - `tests/test_health_endpoints.py` 现在锁定：
    - `/health` 在 ok 时返回 200
    - `/health` 在 degraded 时返回 503
    - `/ready` 不再暴露
  - `tests/test_cli_serve.py` 锁定：
    - `app-server --help` 不再出现 `inspect`
    - `app-server doctor --help` 不再出现 `--require-ready`
  - `tests/test_tenant_key_defaults.py` 改为通过 `/health` 验证新契约
- 更新 `README.md`
  - 移除 `/ready`
  - 移除 `inspect`
  - `doctor` 示例改为 `--require-running`

## 为什么这样更好

1. 公共探针只保留一个更直观。
2. 运维命令只保留一个重型诊断入口更容易记。
3. 删除重复 surface 比继续解释各自差异更省认知成本。

## 对业务接口精简的巡检结论

当前还能继续精简的，主要不是主链路，而是 detail/admin 型接口：

- `/requests/{request_id}`
  - 现在会直接返回完整 request audit，含 `request_payload`、`prompt_preview`、`session_log_file`、`result_file`
- `/results/{request_id}`
  - 现在会同时返回 `record + payload + linked_memories + review_delta`
- `/memories/{memory_id}`
  - 现在会同时返回扁平索引字段和完整 `payload`
- `/governance/assets`
  - 返回完整 rules/memory 校验结果，天然偏治理和排障

主业务高频接口整体还算克制：

- `POST /audit/submit`
- `GET /audit/tasks/{request_id}`
- `GET /audit/tasks/{request_id}/result`
- `GET /results`
- `GET /review-deltas`

这些暂时不建议直接删字段，否则更容易误伤现有前端或排障链路。

## 验证

- `uv run pytest -q` 通过，当前共 74 项
- `uv run ruff check .` 通过

## 下一步建议

如果继续做业务接口减重，优先级建议如下：

1. 给 `/results/{request_id}` 增加轻量模式，只返回 `payload`
2. 给 `/requests/{request_id}` 增加 summary/detail 分层，默认不回 raw `request_payload`
3. 给 `/memories/{memory_id}` 改成默认只回 `payload`，把索引字段留给列表接口
