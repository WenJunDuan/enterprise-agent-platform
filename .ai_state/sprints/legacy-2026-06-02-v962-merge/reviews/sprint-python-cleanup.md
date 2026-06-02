# Sprint Python Cleanup 自审

## 范围

本轮实现覆盖了 handoff 中 Tier 1 / Tier 2 的主要可执行项，并补齐了 Tier 3 设计文档。实际改动集中在 `server/`、`server/prompts/`、`tests/`、`docs/design/` 和 `.ai_state/` 记录文件，没有触碰 `.claude/`、`knowledge/`、`logs/`、`data/` 的现有内容。

## 本轮已完成

- `command_adapter` 已改成模板加载模式，`audit` 和 `init-rules` 都从 `server/prompts/` 读取模板，启动时做模板存在性与占位符校验。
- `TENANT_KEYS` 默认值会触发一次性 warning，`/ready` 的 runtime snapshot 新增 `tenant_keys_are_default` 字段。
- session/request/result 三类 shard store 增加软容量保护，超限时只打 warning，不阻断写入。
- 引入统一 `logging_setup`，默认输出 JSON；`DEV=true` 或 `LOG_FORMAT=kv` 时切到 key=value。
- FastAPI 中间件会回写 `X-Request-ID`；核心 Claude 调用链和后台 audit 任务会把 `request_id / correlation_id / tenant / session_id` 写进日志上下文。
- tenant isolation 已从“默认可漏传 tenant”改成“API 公开查询必须显式 tenant”，CLI/maintenance 改走显式 admin-only 读取路径。
- session 事件 JSONL 现在会强制写入 `request_id / tenant / session_id`，request/result/task 归档也补写了 `session_id` 字段。
- 新增测试覆盖 prompt 加载、默认租户密钥、store 容量保护、tenant 隔离、session lifecycle。

## 对原计划的校正

- handoff 把 `init-rules` 描述成“当前已硬编码 prompt”并不准确；仓库现状是 slash command 路径。这里没有强行改成新的业务 prompt，而是把 slash command 文本本身模板化，既满足外置，又避免改动 Claude 侧语义。
- “新增覆盖率 ≥ 80%” 本轮没有作为自动 gate，因为仓库里尚未接入 coverage 工具链；已通过新增回归测试提升关键路径覆盖，但没有输出 coverage 数值。
- 1.1 中“store 查询返回 dataclass 列表”没有强行全面推进。原因是 API/CLI 当前大量依赖 dict 访问，若一次性替换返回类型会扩大重构面，风险不再属于 Tier 1。当前先完成了构造器类型注解和 tenant/admin 边界收紧，后续如果要继续做静态类型收敛，建议单独起一个 refactor。

## 风险与遗留

- `continue_recent` 现在在 HTTP 模式下允许“带 `conversation_id` 的 scoped continue”，但仍禁止无 scope 的 continue。这个行为更贴近 handoff 目标，但仍依赖 Claude SDK 对 recent conversation 的具体解释。
- `SessionLogger` 在会话刚启动时仍可能先写入本地预测的 session id，随后在收到 Claude 返回的真实 session id 后更新；因此单个 JSONL 文件内的 `session_id` 字段虽然始终存在，但前后记录可能不完全相同。这不影响隔离和 grep，但若未来要做强一致 session tracing，建议在 Tier 3 SQLite 迁移时顺手统一。
- logging 现已区分业务 `request_id` 与 HTTP correlation id；如果后续希望让外部链路排障完全围绕同一个 id 展开，需要再决定是否要把 correlation id 写入更多归档记录。

## 验证

- `uv run pytest -q` 通过，当前共 14 个测试通过。
- `uv run ruff check server tests` 通过。

## 建议

- 下一轮如果继续推进“静态类型收紧”，建议单独拆成 store typing refactor，不要和 tenant/logging 变更耦合。
- Tier 3 如需立项，建议先做 SQLite 设计验证，再决定是否同步做 rate limiter；两者的落地复杂度明显高于本轮。
