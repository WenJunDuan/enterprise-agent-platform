# Plan

- [x] B-001: 完成 Claude Agent SDK serve 层基线重构 + 统一 JSON 契约 + 本地 request/session/result/runtime 存储
      文件: `server/`、`.claude/contracts/`、`logs/`
      依赖: 无

- [x] B-002: 完成 app-server 运维入口与旧兼容路径清理 + 将运行目录统一到项目根 `logs/`
      文件: `server/app_server.py`、`server/platform/`、`server/stores/`
      依赖: B-001

- [ ] T-001: 统一当前仓库路径模型 + 清理 `data/claims`、`raw_policies/...`、`batch-audit` 这类过时示例或主线入口 + 验收标准是 CLI、slash commands、README、`.ai_state` 都与“测试数据在 `tests/`、制度源材料在 `knowledge/`、当前不做 batch”保持一致
      文件: `server/cli.py`、`.claude/commands/`、`README.md`、`.ai_state/design.md`
      依赖: B-001, B-002

- [ ] T-002: 先把 `/init-rules` 做成 Claude 第一优先业务能力 + 让制度源材料从 `knowledge/external/` 进入 `knowledge/{domain}/` 结构化规则体系 + 验收标准是 rule-init skill、system 域路由、slash command 和输出规则格式形成完整闭环
      文件: `.claude/CLAUDE.md`、`.claude/commands/init-rules.md`、`.claude/skills/system/`、`knowledge/_schema/`、`knowledge/external/`
      依赖: T-001

- [ ] T-003: 设计并落地“已审核结果 → 结构化业务记忆”沉淀链路 + 区分运行日志与业务记忆资产 + 验收标准是已归档审核结果可以被提炼为可复用的案例/经验记忆，并保留回溯指针
      文件: `.claude/`、`knowledge/`、`server/stores/`、`.ai_state/design.md`
      依赖: T-002

- [ ] T-004: 打通单条审核业务闭环 + 验证 Claude 调度 `extractor → auditor → reviewer`、结果写入、Pre/Post hook 拦截链路，并接入初始化后的规则与沉淀记忆 + 验收标准是能基于当前仓库真实输入组织方式完成一次真实 `/audit`
      文件: `.claude/CLAUDE.md`、`.claude/agents/expense/`、`.claude/skills/`、`.claude/hooks/`、`knowledge/expense/`
      依赖: T-003

- [ ] T-005: 建立 knowledge 规则治理闭环 + 校验规则 JSON 与 schema、一致性命名、业务域分类映射，并纳入 init 产物与记忆产物 + 验收标准是现有规则集与新增沉淀资产都可校验并明确缺口
      文件: `knowledge/_schema/`、`knowledge/expense/`、`knowledge/hr/`、`knowledge/legal/`、`tests/`
      依赖: T-002, T-003

- [ ] T-006: 补强复核与追溯查询面 + 统一按 `request_id / conversation_id / claude_session_id / claim_id` 检索历史记录和恢复会话，并补充对业务记忆来源的说明 + 验收标准是 CLI/API/文档都能完成复查路径说明
      文件: `server/api.py`、`server/cli.py`、`server/stores/`、`README.md`
      依赖: T-004, T-005

- [ ] T-007: 扩展测试与端到端验证 + 覆盖 hooks、SSE、异常路径、app-server 生命周期、init-rules、审后记忆沉淀和单条审核闭环 + 验收标准是测试不只验证 bootstrap，还验证核心业务与运维路径
      文件: `tests/`、`server/api.py`、`server/app_server.py`、`.claude/hooks/`
      依赖: T-004, T-005, T-006

- [ ] T-008: 整理部署与运行约束说明 + 对齐单 worker、非 serverless、长运行实例、Docker 挂载与 app-server 启动方式 + 验收标准是 README 与 `.ai_state` 能直接指导部署
      文件: `README.md`、`Dockerfile`、`docker-compose.yml`、`.ai_state/quality.md`
      依赖: T-007
