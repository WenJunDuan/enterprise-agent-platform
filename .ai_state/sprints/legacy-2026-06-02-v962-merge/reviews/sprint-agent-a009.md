# A-009 自审：health/ready 返回面瘦身 + 其他接口冗长度巡检

## 结论

- VERDICT: PASS

## 本轮问题

1. `/health` 和 `/ready` 直接复用了完整 runtime diagnostics
   - 对外返回包含 `checks`、`storage_backend`、`runtime_config`、store 写权限、knowledge 资产检查等大量内部细节
   - 这些信息对 `inspect/doctor` 很有价值，但对公共探针接口偏重
2. 健康检查接口和运维诊断接口职责混在了一起
   - 外部调用方只需要知道“整体状态如何、有哪些失败检查、当前 app-server 记录是什么”
   - 不需要每次都看到底层 store/path/schema 的完整明细

## 实际改动

- 更新 `server/api.py`
  - 新增 `_public_runtime_status()`
  - `/health` 和 `/ready` 现在只返回：
    - `status`
    - `app_server`
    - `failing_checks`
    - `advisories`
  - 过滤掉仅对 process manager 有意义的 `"app-server process is not running."` 提示，避免公共探针误导
- 新增 `tests/test_health_endpoints.py`
  - 锁定健康检查返回精简摘要
  - 锁定 `/ready` 在降级时仍返回 `503`
- 更新 `tests/test_tenant_key_defaults.py`
  - 适配新的健康检查契约
- 更新 `README.md`
  - 补充说明 `/health` 和 `/ready` 返回的是精简摘要，完整诊断走 `app-server inspect/doctor`

## 对其他接口的巡检结论

- 当前“明显过度暴露内部实现细节”的主要就是 `/health` 和 `/ready`
- 其余较大的返回主要集中在 detail/admin 型接口：
  - `/requests/{request_id}`
  - `/results/{request_id}`
  - `/review-deltas/{request_id}`
  - `/governance/assets`
- 这些接口本身就是排障、追溯或治理面，返回更详细是合理的
- 主业务列表面和提交面当前整体是克制的，没有发现同级别问题

## 验证

- `uv run pytest -q` 通过，当前共 71 项
- `uv run ruff check .` 通过

## 风险与遗留

- `app_server.record.command`、`cwd`、日志路径等字段仍保留在 `app_server` 里，因为当前需求明确认为这一级信息“够用且可接受”
- 如果后续还想继续瘦身，下一步最合适的是再裁掉 `command/cwd/pid_file/stdout_log/stderr_log` 这类本地路径细节，但这次先不主动压过头

## 下一步建议

- 如果前端或网关只关心 200/503，可以进一步把 health check 消费面约束到只读 `status`
- 如果后续还要继续做 API 返回面减重，优先审视 `/governance/assets` 和 detail 型接口是否需要“summary/detail”双版本
