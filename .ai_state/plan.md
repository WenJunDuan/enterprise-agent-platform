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

- [x] T-009: 重写 `.claude/skills/expense-audit` 与相关 `common/system` skills，并为 `knowledge/expense/*.json` 补齐真实制度来源元数据；验收标准是 skill 文本引用真实本地路径、expense 规则带 `source`、`thresholds.json` 带来源映射且所有 JSON 可解析
      文件: `.claude/skills/expense-audit/`、`.claude/skills/common/`、`.claude/skills/system/`、`knowledge/expense/`、`.ai_state/superpowers/`
      依赖: T-002

- [x] T-010: 收口 CLI 的 `.env -> Claude SDK` 运行面，确保 `server.cli ask` 在进入模型调用前完成 runtime 映射、缺失校验和脱敏诊断输出；验收标准是 CLI 有 `runtime` 入口、`ask` 失败前置可读、README 和 `.env.example` 对齐
      文件: `server/platform/config.py`、`server/core.py`、`server/cli.py`、`server/platform/diagnostics.py`、`.env.example`、`README.md`
      依赖: B-001, B-002

- [x] T-011: 稳定 `server.cli init-rules` 的 expense 路径，避免空成功、PDF 读权限失败和单次 prompt 过长；验收标准是 expense 域按类别拆分执行、结果聚合归档、错误写偏文件被清理、最终返回有意义的 `initialized/manual_review`
      文件: `server/cli.py`、`server/core.py`、`.claude/commands/init-rules.md`、`.claude/skills/system/rule-init/SKILL.md`、`tests/test_bootstrap.py`、`knowledge/expense/`
      依赖: T-010

- [x] T-012: 移除 `chat` 模式，收紧 CLI 与服务边界；验收标准是 `server.cli` 不再暴露 `chat` 子命令，`server/chat.py` 删除，README 同步说明 CLI 仅保留本地终端直连用途
      文件: `server/cli.py`、`server/chat.py`、`README.md`、`tests/test_bootstrap.py`
      依赖: T-010

- [x] T-013: 建立统一 Claude command 调用适配层，让 CLI 与 serve 共用 `init-rules` / `audit` 的 Claude 能力入口，而不是在 Python 两侧重复实现；验收标准是新增共享 adapter、CLI 改为走 adapter、HTTP `/init-rules` 与 `/audit` 可用、测试通过
      文件: `server/command_adapter.py`、`server/cli.py`、`server/api.py`、`tests/test_bootstrap.py`、`README.md`
      依赖: T-010, T-011

- [x] T-014: 收口 serve 运行面与 Python 适配层模板重复；验收标准是 `app_server` 提供 HTTP 探测信息、`api.py` 的 JSON endpoint 共享统一执行模板、README 对齐服务调用方式、静态检查和测试通过
      文件: `server/app_server.py`、`server/api.py`、`server/cli.py`、`README.md`、`tests/test_bootstrap.py`
      依赖: T-013

- [ ] T-015: 固化审核结果中文展示契约；验收标准是内部继续保留 `approved/rejected/manual_review` 三态，对外统一输出 `result/conclusion/explanation`，其中 `manual_review` 固定显示为“待人工复核”且必须说明无法自动放行的原因
      文件: `.claude/contracts/common/audit-result.schema.json`、`.claude/skills/common/result-format/SKILL.md`、`.claude/hooks/check-before-write.py`、`tests/test_bootstrap.py`
      依赖: T-014

- [x] T-016: 提供 serve 异步审核提交能力；验收标准是 `POST /audit/submit` 支持目录模式和上传模式、`GET /audit/tasks/{request_id}` 可轮询状态、`GET /results/{request_id}` 可读取完整结果、目录和上传模式都能形成统一 case 路径并通过测试
      文件: `server/api.py`、`server/platform/paths.py`、`server/stores/audit_task_store.py`、`server/command_adapter.py`、`tests/test_bootstrap.py`、`.ai_state/superpowers/`
      依赖: T-014

- [x] T-017: 强化异步审核服务端；验收标准是任务状态包含时间线字段与进度信息、启动时可恢复超时任务、上传具备基础安全校验、轻量结果接口可用、租户隔离与目录白名单生效、submission 清理机制与 HTTP 集成测试通过
      文件: `server/api.py`、`server/platform/config.py`、`server/platform/maintenance.py`、`server/stores/audit_task_store.py`、`tests/test_bootstrap.py`、`.env.example`、`.ai_state/superpowers/`
      依赖: T-016
