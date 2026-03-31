# Doing

- 已完成职责收口：`.claude/` 与 `knowledge/` 仅承载业务内容，Python 只负责 Claude 调用、HTTP/CLI、持久化、诊断和进程管理。
- 已完成结构化输出约束：`server/core.py` 通过 Claude Agent SDK `output_format` 加载 `.claude/contracts/common/audit-result.schema.json`，不再依赖提示词声明 JSON。
- 已完成服务层重构：`server/` 现在稳定分为入口层（`api/core/cli/chat/app_server`）、基础设施层（`platform/`）和仓储层（`stores/`）。
- 已完成本地可追溯存储：请求审计、会话索引、原始事件流、结构化结果、运行时状态统一落在项目根 `logs/`。
- 已完成会话恢复基础能力：支持 `conversation_id`、`resume_session_id`、`fork_from_session_id`，并可通过 Claude SDK 读取 transcript。
- 已完成兼容清理：旧 wrapper、旧 `server/logs` 残留路径、legacy fallback 读取逻辑以及缓存目录已清理。
- 当前主线已明确：先统一路径模型并移除 `batch-audit` 出主线，再把 `/init-rules` 作为 Claude 第一优先业务能力，随后设计“已审核结果 → 结构化业务记忆”的沉淀链路，最后再进入单条审核业务闭环。
- 已完成当前 skill 整理：以 `.ai_state/docs/audit-skills/` 为基准，重写 `.claude/skills/expense-audit` 与相关 `common/system` skills，并将 `knowledge/expense/*.json` 回链到 `knowledge/external/数睿员工手册.pdf` 第六章制度来源。
- 当前进行中：先收口 CLI 的 `.env -> Claude SDK` 运行面，不进入 HTTP serve；重点是 runtime 映射、缺失校验和 `server.cli ask` 的前置可见性。
- 当前阻塞：本机 Python 环境缺少 `fastapi`、`typer`、`python-dotenv`、`claude_agent_sdk`、`anthropic`，因此只能完成静态校验，无法在本轮直接执行 `server.cli ask` 做真实模型调用验证。
- 已完成 CLI 基础链路验证：`server.cli runtime` 与 `server.cli ask` 已可实际进入 Claude 调用链并产生日志。
- 已完成 `init-rules expense` 稳定化：空 `initialized` 结果会被拒绝；PDF 会先转文本代理；expense 域按 `general/invoice/loan/entertainment/travel/transport` 拆分执行并聚合；最终结果已归档为 `manual_review`，保留成功写入文件与需人工确认项。
- 已移除 `chat` 模式：`server.cli` 不再暴露交互式 chat 子命令，`server/chat.py` 已删除，CLI 与未来服务边界更清晰。
- 已开始把 Python 越界的业务编排回收到 Claude 侧：`server/cli.py` 不再维护 expense/init-rules 的分类 orchestration，相关大文档拆分策略已迁回 `.claude/commands/init-rules.md` 与 `system/rule-init` skill。
- 已建立统一 Claude command 调用适配层：`init-rules` 与 `audit` 现在通过同一套 Python adapter 从 CLI 与 HTTP 两端进入同一个 Claude command，而不是在 Python 两侧重复实现业务能力。
- 已完成 Python 适配层第二轮收口：`api.py` 和 `cli.py` 的重复输出/错误处理模板已被压缩，Python 更接近“统一 Claude 调用适配层 + 两个输出外壳”的结构。
- 已完成 serve 运行面收口：`app_server.py` 已支持本地 HTTP `/health`、`/ready` 探测并暴露 `service_http` 状态；`api.py` 的 `/chat`、`/audit`、`/init-rules` 共享统一 JSON endpoint 模板；README 已补齐服务调用示例。
- 当前进行中：收口审核结果中文展示契约，要求内部保留三态，对外新增 `result/conclusion/explanation`，并将 `manual_review` 固定为“待人工复核”且必须说明无法自动放行的原因。
