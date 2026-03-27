# Lessons

- `.claude/` 只保留业务内容；开发过程、运行方式、服务契约和演进记录统一放在 `.ai_state`。
- 结构化 JSON 约束要落在 Claude Agent SDK `output_format` 和 schema 上，而不是依赖提示词 wording。
- 对服务层的目录迁移和兼容裁剪要一次性做完：删目录、删引用、删 fallback、删缓存最好在同一轮完成。
- `server/logs` 是历史残留；真实运行目录应统一使用项目根 `logs/`，避免后续存储边界混乱。
- 一旦决定不再兼容旧路径，就应同步移除 `LEGACY_*` 常量和旧单文件读取逻辑，避免为未来 PostgreSQL 迁移制造噪音。
- 本地持久化要先把 `request_id / conversation_id / claude_session_id` 这条链路设计完整，再考虑替换底层为数据库。
- 如果业务域继续扩展，`.claude/skills` 继续按“业务域 / 通用能力 / 系统能力”分组，比一级平铺更容易维护。
- 顶层 `data/` 与 `raw_policies/` 如果不再保留，就要同步修正文档、CLI 默认参数、slash command 用法和验收示例；否则计划会被历史目录误导。
- 当前仓库的真实素材组织应以 `tests/` 承载测试数据、`knowledge/` 承载结构化规则、`knowledge/external/` 承载制度源材料为准。
- `batch-audit` 已不再是当前阶段主线能力，规划和文档不应继续围绕它展开。
- “规则初始化”和“审后记忆沉淀”都属于 Claude 侧业务建设，不应回流成 Python 业务判断；Python 继续只做调用、归档和查询。
