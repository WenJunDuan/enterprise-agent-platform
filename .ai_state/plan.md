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

- [x] T-015: 固化审核结果中文展示契约；验收标准是内部继续保留 `approved/rejected/manual_review` 三态，对外统一输出 `result/conclusion/explanation`，其中 `manual_review` 固定显示为“待人工复核”且必须说明无法自动放行的原因
      文件: `.claude/contracts/common/audit-result.schema.json`、`.claude/skills/common/result-format/SKILL.md`、`.claude/hooks/check-before-write.py`、`tests/test_bootstrap.py`
      依赖: T-014

- [x] T-016: 提供 serve 异步审核提交能力；验收标准是 `POST /audit/submit` 支持目录模式和上传模式、`GET /audit/tasks/{request_id}` 可轮询状态、`GET /results/{request_id}` 可读取完整结果、目录和上传模式都能形成统一 case 路径并通过测试
      文件: `server/api.py`、`server/platform/paths.py`、`server/stores/audit_task_store.py`、`server/command_adapter.py`、`tests/test_bootstrap.py`、`.ai_state/superpowers/`
      依赖: T-014

- [x] T-017: 强化异步审核服务端；验收标准是任务状态包含时间线字段与进度信息、启动时可恢复超时任务、上传具备基础安全校验、轻量结果接口可用、租户隔离与目录白名单生效、submission 清理机制与 HTTP 集成测试通过
      文件: `server/api.py`、`server/platform/config.py`、`server/platform/maintenance.py`、`server/stores/audit_task_store.py`、`tests/test_bootstrap.py`、`.env.example`、`.ai_state/superpowers/`
      依赖: T-016

- [x] L-001: 生成 `data/case2` 到 `data/case21` 的混合压测样例，并输出 `data/scenario-index.json` 作为场景索引；验收标准是每个 case 至少包含 `audit-request.json`，同时覆盖合法、缺件、越界、异常和脏数据场景
      文件: `scripts/generate_stress_cases.py`、`data/`
      依赖: T-017

- [x] L-002: 将 `README.md` 重写为中文教程版，覆盖环境填写、项目启动、部署和测试四条主线，并对齐当前 CLI、HTTP 服务、Docker 与压测样例的实际入口
      文件: `README.md`
      依赖: T-017

- [x] L-003: 重写前端审核服务对接文档，按“接口数量 → token → 提交数据 → 查询状态 → 查询结果”的顺序整理，并对齐当前异步审核接口的实际行为
      文件: `.ai_state/docs/前端审核服务对接文档.md`
      依赖: T-017

- [x] L-004: 基于桌面真实 PDF 在 `data/real-case-001` 下生成可直接用于服务端目录审核的真实样例目录，并补充最小提交 payload
      文件: `data/real-case-001/`
      依赖: T-017

- [x] L-005: 调整 `docker-compose.yml` 以适配当前仓库目录结构，移除过时卷挂载，并同步 README 中的部署说明
      文件: `docker-compose.yml`、`README.md`
      依赖: T-017

- [x] L-006: 将 `.ai_state/docs/前端审核服务对接文档.md` 收口为前端接入手册，只保留请求头、上传格式、文件字段、示例数据、状态轮询和结果读取
      文件: `.ai_state/docs/前端审核服务对接文档.md`
      依赖: T-017

- [x] L-007: 让 Docker 与 Compose 的服务端口从 `.env` 读取，消除 `APP_SERVER_PORT` 与容器启动命令、端口映射之间的硬编码不一致
      文件: `Dockerfile`、`docker-compose.yml`、`README.md`
      依赖: T-017

- [x] L-008: 收口 `docker run` 文档示例，避免手工重复改端口，改为先从 `.env` 提取 `APP_SERVER_PORT` 再执行映射
      文件: `README.md`
      依赖: T-017

- [x] H-001: Python 平台清理 Tier 1+2（2026-04-20）；验收标准是 store `__init__` 类型注解齐全、默认租户密钥有启动告警、store 有容量保护、prompt 外置 + 启动校验、引入统一 logging + correlation id、租户隔离 `tenant` 字段必填、新增 session lifecycle / tenant isolation / prompt load / store capacity / tenant key defaults 测试
      文件: `server/stores/`、`server/platform/logging_setup.py`、`server/platform/config.py`、`server/platform/diagnostics.py`、`server/prompts/`、`server/command_adapter.py`、`server/api.py`、`server/core.py`、`tests/`
      依赖: T-014

- [x] H-002: audit 结果 schema 扩展（2026-04-20）；验收标准是 schema 新增 `manual_review_reason` 枚举（7 值）+ `risk_dimensions` 多维打分（5 维 0-10），`core.py` validator 同步校验（`manual_review` 必填合法 reason、score 严格 int 0-10），`prompts/audit.md` 告知 Claude 枚举要求，`README.md` 新字段说明，新增 `tests/test_audit_result_schema.py` 11 用例；保持向后兼容（新字段不入 required）
      文件: `.claude/contracts/common/audit-result.schema.json`、`server/core.py`、`server/prompts/audit.md`、`README.md`、`tests/test_audit_result_schema.py`
      依赖: T-014

- [~] H-003: audit P1 Python 业务编排尝试（2026-04-20 已撤销）；原设计是把 Python 拆成"数据搬运层 + Claude 判断层"，新增 `server/audit/` 目录（contracts / intake / extractor / rules_loader / amount_extract / approval_signatures / orchestrator）+ `POST /audit/fast` 单轮端点。判定为越界（Python 不得引入"发票 / 规则 / 金额 / 签字节点"等业务概念），全部删除。经验写入 `.ai_state/lessons.md`
      文件: （已删除）`server/audit/`、`server/prompts/audit_fast.md`、`tests/test_audit_*.py`；（已回退）`server/api.py`、`server/command_adapter.py`
      依赖: H-002（撤销不影响 H-002）

## Next Phase — Agent 架构与优化执行序列（2026-04-21）

- [x] A-001: 收口命令单一事实源（2026-04-21）；验收标准是 Python adapter 不再承载独立业务语义，`audit` / `init-rules` 的规则说明只有一份
      文件: `.claude/commands/`、`server/command_adapter.py`、`README.md`、`.ai_state/design/agent-next-phase-blueprint.md`；实施结果：删除 `server/prompts/audit.md` 与 `server/prompts/init-rules.md`，adapter 统一走 slash command，补充空格参数 quoting，`.claude/commands/audit.md` 历史路径示例已收口
      依赖: 无
      Review Gate: command 边界 review

- [x] A-002: 收口 agent / skill 关系并补中间契约（2026-04-21）；验收标准是 extractor 输出与 reviewer 差异都有明确 schema，agent 之间不再只靠自由文本衔接
      文件: `.claude/agents/expense/`、`.claude/skills/`、`.claude/contracts/`、`README.md`；实施结果：新增 `expense/extract-result.schema.json` 与 `expense/review-delta.schema.json`，同步 extractor / auditor / reviewer 的职责与输入输出边界，补 `tests/test_agent_contracts.py`
      依赖: A-001
      Review Gate: schema + 单域主链 review

- [x] A-003: 设计并落地审后业务记忆沉淀层（2026-04-21），形成 `logs/results -> knowledge/memory/` 的回链；验收标准是案例记忆具备独立 schema、保留 `request_id/result_file` 指针，且不混入 Python 业务逻辑
      文件: `.claude/`、`knowledge/`、`.ai_state/design/agent-next-phase-blueprint.md`；实施结果：新增 `knowledge/_schema/case-memory.schema.json`、`.claude/commands/distill-memory.md`、`.claude/skills/system/memory-distill/SKILL.md`、`knowledge/memory/{expense,hr,legal}/`
      依赖: A-002
      Review Gate: 记忆层边界 review

- [x] A-004: 打通单条审核闭环（2026-04-21），接入初始化后的规则与沉淀记忆；验收标准是能基于当前真实输入组织方式完成一次完整 `/audit`，并能解释规则来源与记忆来源
      文件: `.claude/CLAUDE.md`、`.claude/agents/expense/`、`.claude/hooks/`、`knowledge/expense/`、`knowledge/memory/`；实施结果：新增 `tests/fixtures/expense/travel-missing-preapproval/` 真实输入样例，完成 `/audit -> audit-result -> /distill-memory -> case-memory` 首条本地闭环，新增 `common-memory-query` 并接入 expense 主链，生成首条真实 memory 资产
      依赖: A-003
      Review Gate: 真实样例闭环 review

- [x] A-005: 建立规则治理与追溯查询增强（2026-04-21），补齐 `claim_id / review_delta / manual_review_reason` 查询；验收标准是规则资产可校验、结果可追溯、复核差异可检索
      文件: `knowledge/_schema/`、`knowledge/`、`server/api.py`、`server/cli.py`、`server/stores/`、`tests/`
      实施结果（第一阶段，2026-04-21）：`request_store` 双写 SQLite 查询索引、`memory_store` 建立 SQLite 索引、`/requests` 和 `/results` 补过滤参数、`/memories` 查询面上线、`/results/{request_id}` 回链 `linked_memories`
      实施结果（第二阶段，2026-04-21）：新增 `review_delta_store`、`/review-deltas`、`/governance/assets`、CLI `validate-assets`，并完成 rules/memory 资产校验与复核差异查询面
      依赖: A-004
      Review Gate: 治理 + 查询面 review

- [x] A-006: 以触发条件驱动的方式扩展多域协同和二次复核成本治理（2026-04-21）；验收标准是 HR/legal 只在明确条件下参与，post-write review 不再默认为全量高成本路径
      文件: `.claude/CLAUDE.md`、`.claude/agents/`、`.claude/hooks/`、`README.md`；实施结果：在 `CLAUDE.md` 与 `audit.md` 中固化 reviewer / HR / Legal 触发条件，并将 `review-output` hook 收紧为高风险 / 冲突场景触发
      依赖: A-005
      Review Gate: 多域协同 + 成本治理 review

- [x] A-007: 项目级整体架构 review + API 返回集优化 + 发布前整理（2026-04-21）；验收标准是查询列表统一返回 `meta`、HTTP 错误统一补结构化 `error` 且保留 `detail` 兼容、README/前端文档同步、全仓 `ruff check .` 与 `pytest` 均通过
      文件: `server/api.py`、`tests/test_query_surfaces.py`、`README.md`、`.ai_state/docs/前端审核服务对接文档.md`、`.ai_state/docs/audit-skills/audit_check.py`、`.ai_state/reviews/sprint-agent-a007.md`
      实施结果：为 `/sessions`、`/conversations`、`/requests`、`/results`、`/memories`、`/review-deltas`、`/sessions/{session_id}/messages` 增加 `meta(limit/offset/returned/filters)`；新增统一 HTTP 异常处理，返回 `detail + error{code,message,status_code,path,correlation_id}`；补查询面与错误返回回归测试；修复 `.ai_state/docs/audit-skills/audit_check.py` 的 lint 问题，发布前质量门恢复为全绿
      依赖: A-006
      Review Gate: API contract + release cleanup review
