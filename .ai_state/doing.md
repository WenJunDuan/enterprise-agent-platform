# Doing

- 已完成职责收口：`.claude/` 与 `knowledge/` 仅承载业务内容，Python 只负责 Claude 调用、HTTP/CLI、持久化、诊断和进程管理。
- 已完成结构化输出约束：`server/core.py` 通过 Claude Agent SDK `output_format` 加载 `.claude/contracts/common/audit-result.schema.json`，不再依赖提示词声明 JSON。
- 已完成服务层重构：`server/` 现在稳定分为入口层（`api/core/cli/chat/app_server`）、基础设施层（`platform/`）和仓储层（`stores/`）。
- 已完成本地可追溯存储：请求审计、会话索引、原始事件流、结构化结果、运行时状态统一落在项目根 `logs/`。
- 已完成会话恢复基础能力：支持 `conversation_id`、`resume_session_id`、`fork_from_session_id`，并可通过 Claude SDK 读取 transcript。
- 已完成兼容清理：旧 wrapper、旧 `server/logs` 残留路径、legacy fallback 读取逻辑以及缓存目录已清理。
- 当前主线已明确：先统一路径模型并移除 `batch-audit` 出主线，再把 `/init-rules` 作为 Claude 第一优先业务能力，随后设计“已审核结果 → 结构化业务记忆”的沉淀链路，最后再进入单条审核业务闭环。
