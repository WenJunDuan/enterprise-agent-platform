# Design Snapshot

## 分层

- `.claude/`: agents、skills、hooks、commands、contracts，承载业务工作流与输出契约
- `knowledge/`: 结构化制度和规则资产
- `server/api.py`: HTTP serve 接口、租户鉴权、健康检查、业务 command JSON API、请求/会话/结果查询
- `server/core.py`: Claude Agent SDK 桥接、结构化输出约束、会话控制、事件记录
- `server/command_adapter.py`: Python 对 Claude slash command 的统一调用适配层
- `server/cli.py`: 本地 CLI 外壳，负责终端参数解析与终端输出
- `server/app_server.py`: Python 版后台进程管理、日志查看、doctor、maintain
- `server/platform/`: 路径、配置、诊断、维护、底层文件存储工具与源文件预处理
- `server/stores/`: request/session/result/runtime 仓储接口与本地 JSONL/JSON 实现
- `tests/`: 测试代码与后续测试用例数据承载位置
- `knowledge/external/`: 当前仓库中保存原始制度文件或外部参考材料的位置
- `logs/`: 唯一的本地运行时、请求、会话、结果、进程状态归档根目录

## 当前设计决策

- 业务规则只留在 `.claude/` 和 `knowledge/`；Python 只负责调用 Claude、执行 JSON 契约、记录审计链路和暴露运行入口。
- 结构化输出通过 Claude Agent SDK `output_format` + JSON Schema 强制约束，不再依赖 prompt 文本声明。
- 审核输出继续保留内部 `approved / rejected / manual_review` 三态，但对外统一映射为 `result/conclusion/explanation` 中文展示字段；其中 `manual_review` 固定显示为“待人工复核”，且必须说明无法自动放行的原因。
- `request_id` 是全链路审计主键；`conversation_id` 表示应用级会话；`claude_session_id` 对应 Claude SDK 的可恢复会话。
- Python 不拥有业务能力实现；`init-rules`、`audit` 等能力定义在 `.claude/commands` / `.claude/skills`，CLI 与 serve 只通过统一 adapter 调用这些 Claude 能力。
- 前台调试入口是 `python -m server.cli serve`；后台常驻入口是 `uv run app-server start`，两者本质上都启动同一个 Python 服务进程。
- 本地 JSONL/JSON 布局先对齐未来数据库字段，再在后续通过仓储层替换为 PostgreSQL。
- 顶层 `data/` 和 `raw_policies/` 不是当前仓库正式目录；测试数据应收敛到 `tests/`，真实制度源材料当前放在 `knowledge/external/`。
- 当前业务建设顺序调整为：`/init-rules` 优先，审后业务记忆沉淀次之，单条审核业务闭环随后；`batch-audit` 不进入当前主线。

## 本地存储布局

- `logs/service/requests/requests-YYYY-MM.jsonl`: serve 请求审计索引
- `logs/sessions/index/sessions-YYYY-MM.jsonl`: 会话索引
- `logs/sessions/events/YYYY/MM/DD/*.jsonl`: Claude 原始事件流
- `logs/results/index/results-YYYY-MM.jsonl`: 结构化结果索引
- `logs/results/by-request/YYYY/MM/DD/{request_id}.json`: 结构化结果归档
- `logs/runtime/app-server/`: PID、状态文件、stdout/stderr、维护对象

## 约束

- 结果、请求、会话三层都用 `request_id` 串联，保证可恢复、可追溯。
- 索引采用按月分片的 JSONL，避免单文件无限增长。
- 原始事件流和结构化结果分离存储：前者保留过程，后者保留最终归档。
- CLI 与 serve 共享同一套 Claude command 调用适配层；差异只体现在终端输出与 HTTP JSON/SSE 输出。
- 后续如果接 PostgreSQL，优先迁移 `request/session/result` 三类仓储实现，不改 Claude 业务侧内容。

## 记忆分层

- `logs/` 保存不可变的运行事实：请求审计、会话事件、最终结构化结果、进程状态。
- 审核完成后的“业务记忆沉淀”不应直接混入 Python 逻辑；应由 Claude 侧从已归档结果中提炼为结构化经验资产，再沉淀回 `knowledge/` 体系。
- 下一阶段建议增加独立的案例/经验记忆层，用于沉淀已审核结果中的 `verdict`、`policy_refs`、`evidence_chain`、风险模式和复核结论，并保留 `request_id` / `result_file` 回链。

## 当前清理状态

- 旧 `server/` 外层兼容 wrapper 已删除，当前以 `platform/` 和 `stores/` 为稳定内部边界。
- 旧 `server/logs` 路径已废弃；真实运行数据统一写入项目根 `logs/`。
- 仓储层不再读取 legacy 单文件日志，也不再保留 `output/results/` 兼容实现。
- 文档与命令中仍有少量 `data/claims`、`raw_policies/...` 的历史示例路径，需要在下一阶段统一到当前仓库目录模型。
