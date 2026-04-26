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

- [x] A-008: README 重写与命令面收口（2026-04-22）；验收标准是 README 先给出快速开始、端口、CLI 两套命令和 HTTP API 总览，关键信息不再埋在长段落里，且文档中的服务命令与当前实现一致
      文件: `README.md`、`.ai_state/reviews/sprint-agent-a008.md`
      实施结果：将 README 从“长教程堆叠”重构为“快速开始 → 端口与地址 → 命令总览 → HTTP API → 审核流程 → 查询追溯 → 部署 → 测试排障”的结构，并用 `server.cli --help`、`app-server --help`、`app-server doctor --help` 校验关键命令示例
      依赖: A-007
      Review Gate: docs usability review

- [x] A-009: health/ready 返回面瘦身 + 其他接口冗长度巡检（2026-04-22）；验收标准是 `/health` 和 `/ready` 不再暴露完整内部 diagnostics 包，只保留紧凑摘要，且确认其他业务主接口没有同级别的过度暴露问题
      文件: `server/api.py`、`tests/test_health_endpoints.py`、`tests/test_tenant_key_defaults.py`、`README.md`、`.ai_state/reviews/sprint-agent-a009.md`
      实施结果：新增公共健康检查摘要层，`/health` 与 `/ready` 现在只返回 `status + app_server + failing_checks + advisories`；完整 diagnostics 保留给 `app-server inspect/doctor`；补健康检查精简回归测试并更新 README，同时审阅其他接口，确认当前冗长返回主要集中在 detail/admin 型接口而非主业务列表面
      依赖: A-008
      Review Gate: API surface trim review

- [x] A-010: 删除 `/ready` 与 `inspect`，统一到 `health + doctor`（2026-04-22）；验收标准是公共 HTTP 探针只保留 `/health`，本地运维诊断只保留 `doctor`，README/测试/CLI 帮助与实际实现一致
      文件: `server/api.py`、`server/app_server.py`、`tests/test_health_endpoints.py`、`tests/test_tenant_key_defaults.py`、`tests/test_cli_serve.py`、`README.md`、`.ai_state/reviews/sprint-agent-a010.md`
      实施结果：删除 `/ready` 路由，`/health` 改为同时承担状态探针并在 degraded 时返回 `503`；删除 `app-server inspect`，`doctor` 去掉 `--require-ready`；`service_http` 只保留 `health`；补 route/help 回归测试并同步 README
      依赖: A-009
      Review Gate: surface deletion review

- [x] A-011: 业务 API / CLI 边界收口 + 业务返回面整理（2026-04-22）；验收标准是 HTTP API 不再与 CLI 重复暴露查询/治理接口，异步审核返回只保留业务必需字段，README/前端对接文档同步说明
      文件: `server/api.py`、`server/app_server.py`、`tests/test_query_surfaces.py`、`tests/test_tenant_isolation.py`、`tests/test_audit_submit_attachments.py`、`tests/test_cli_serve.py`、`README.md`、`.ai_state/docs/前端审核服务对接文档.md`、`.ai_state/reviews/sprint-agent-a011.md`
      实施结果：移除 HTTP 上的 `/sessions`、`/conversations`、`/requests*`、`/results*`、`/memories*`、`/review-deltas*`、`/governance/assets`、`/sessions/{session_id}/messages`，将查询/治理统一收回 CLI；`/audit/submit` 删除 `result_url`，`/audit/tasks/{request_id}` 收口为 `request_id/status/mode/claim_id/error_detail/progress_message/submitted_at/started_at/finished_at/updated_at`；`app-server doctor` 的服务 URL 快照同步去掉已删除的查询面
      依赖: A-010
      Review Gate: business-vs-cli boundary review

- [x] A-012: 最小业务 HTTP 面落地（2026-04-22）；验收标准是 HTTP 只保留 `health + audit submit/status/result`，命令型能力全部收回 CLI，README 与前端文档同步更新
      文件: `server/api.py`、`server/app_server.py`、`tests/test_query_surfaces.py`、`tests/test_cli_serve.py`、`tests/test_audit_submit_attachments.py`、`README.md`、`.ai_state/docs/前端审核服务对接文档.md`、`.ai_state/reviews/sprint-agent-a012.md`
      实施结果：移除 HTTP 上的 `/chat`、`/chat/stream`、`/audit`、`/init-rules`，当前公开 HTTP 只剩 `/health`、`/audit/submit`、`/audit/tasks/{request_id}`、`/audit/tasks/{request_id}/result`；`app-server doctor` 的 URL 快照同步改为这组最小业务面；测试与文档已全部对齐
      依赖: A-011
      Review Gate: minimal-http-surface review

## Sprint 2 修复计划 — React Frontend Gate Recovery（2026-04-24）

- [x] S2-FIX-001: 修复过期的 store capacity 测试；验收标准是 `tests/test_store_capacity.py` 不再导入已删除的 `JSONLResultStore`，并与当前 SQLite result store 边界一致。
      文件: `tests/test_store_capacity.py`、必要时 `server/stores/result_store.py`
      风险: 不能为了让测试通过恢复已裁剪的 JSONL result index 主路径。
- [x] S2-FIX-002: 修复 Vite/TypeScript 环境类型；验收标准是 `cd ui && npm run build` 通过，且不提交 `ui/.env.local` 与 `ui/node_modules/`。
      文件: `ui/src/vite-env.d.ts` 或等效 Vite 类型声明
      风险: 只补类型声明，不改 API client 行为。
- [x] S2-FIX-003: 回归后端质量门；验收标准是 `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` 与 `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` 通过。
      文件: `tests/`、必要时 `.ai_state/reviews/sprint-2.md`
      风险: 若发现 unrelated 旧失败，只记录并隔离，不扩大修复面。
- [x] S2-FIX-004: 同步 `.ai_state` 真实状态；验收标准是 `tasks.md`、`progress.md`、`reviews/sprint-2.md` 反映实际验证结果，不再保留虚假 PASS。
      文件: `.ai_state/tasks.md`、`.ai_state/progress.md`、`.ai_state/reviews/sprint-2.md`
      风险: 文档必须以验证命令输出为准。

## Sprint 2 Review Closure Plan（2026-04-26）

- [x] S2-REV-001: 修正 `.ai_state/design.md` 中过期的 HTTP 查询面、后端变更与 SSE 描述。
- [x] S2-REV-002: 修正前端对接文档中的接口数量、`GET /audit/tasks`、`VITE_API_BASE` / `VITE_API_KEY`。
- [x] S2-REV-003: 新增 `.ai_state/init.sh`，让 review/impl 阶段 get-bearings 可执行。
- [x] S2-REV-004: 完成主线自审、质量门验证、lessons 追加，并将 Sprint 2 推进到 ship 阶段。

## Sprint 3 Plan — 真实报销填报与列表增强（2026-04-26）

### WHY

当前 `ui/` 只覆盖最小审核提交：案例编号、申请人、费用类型、附件。它能打通链路，但不像真实发票报销：缺少申请人/部门/成本中心、发票与金额拆分、行程/招待/借款/审批信息、异常场景选择、附件分类与列表筛选。Sprint 3 目标是把 UI 提升为“真实复杂报销单模拟器”，但不把业务判断下沉到 Python。

### Contract Boundary

- 后端 `POST /audit/submit` 不校验业务字段；只校验传输外壳、安全落盘和可解析性。
- 前端可以把任意公司/业务线字段放入 `form_json`，也可以用普通 multipart 文本字段；字段语义由 Claude 审核链路读取。
- `files` 附件为可选的 0 个或多个，Python 不按业务扩展名白名单拦截，只保留文件名安全、非空文件和大小限制。
- 不新增 HTTP 业务路由；继续使用 `/audit/submit`、`/audit/tasks`、`/audit/tasks/{request_id}`、`/audit/tasks/{request_id}/result`。
- 不在 Python 中新增发票/金额/规则/审批判断逻辑。

### Scope

- 表单页改为多区块真实报销填报：基础信息、费用明细、发票信息、行程/招待信息、审批与借款、异常场景、附件上传与提交预览。
- 列表页增强业务信息密度：统计卡片、状态过滤、关键词搜索、风险/异常标签、本地提交摘要回显。
- 使用浏览器 `localStorage` 保存最近提交的表单摘要，用于弥补后端任务列表目前只返回 `claim_id`/状态时间线、不返回完整表单 payload 的限制。
- 维持现有 Tailwind + React Router 结构，不引入 UI 框架或后端依赖。

### Non-Scope

- 不改 Claude 审核 prompt/规则。
- 不新增数据库字段或任务状态 schema。
- 不上传附件内容做前端解析；只展示文件名、类型、大小、附件分类。
- 不做真实 OCR、发票查验或预算校验；这些只作为模拟字段和异常勾选项进入 `form_json`。

### Proposed UI Model

表单字段按真实报销场景组织：

- 基础信息：报销单号、申请人、部门、成本中心、项目/客户、申请日期、币种、紧急程度、费用类型。
- 金额信息：总金额、税额、未税金额、支付方式、是否公司卡、是否预付/借款、借款单号、预算科目。
- 发票信息：发票类型、发票号码、发票代码、开票日期、销售方、纳税人识别号、发票验真状态、是否抬头不符。
- 差旅信息：出发/到达城市、开始/结束日期、交通方式、住宿晚数、同行人数、是否事前申请。
- 招待信息：招待对象、客户公司、参与人数、人均金额、招待时段、业务目的。
- 审批与异常：审批单号、审批人、事前审批状态、预算超额、重复发票、附件缺失、金额不一致、跨期报销、超标准住宿/招待。
- 附件：发票、行程单、付款凭证、审批单、合同/订单、其他；每个附件可选分类，提交前展示清单。

### Acceptance Criteria

- `SubmitExpense` 至少覆盖 30 个真实报销字段，并能根据费用类型展示差旅/招待等场景字段。
- 提交 payload 不依赖后端业务必填字段；复杂字段进入 `form_json` 并由 Claude 解释。
- 附件上传支持 0 个或多个文件、附件分类、大小展示、删除单个文件。
- 提交前展示 JSON/摘要预览，便于验证模拟场景。
- `TaskList` 展示状态统计、关键词搜索、费用类型/异常标签、本地摘要；无本地摘要时保持后端任务列表可用。
- `TaskDetail` 若能命中本地摘要，展示提交时的业务表单摘要和附件摘要。
- `cd ui && npm run build` 通过；后端 `pytest`/`ruff` 不因类型或契约漂移失败。

### Implementation Tasks

- [x] S3-T0: 调整 `/audit/submit` 为无业务字段约束的通用 multipart intake，测试覆盖无固定字段、附件可选、任意扩展名归档。
- [x] S3-T1: 扩展 `SubmitFormData` 类型为真实报销模板 payload，但不把模板字段作为后端必填边界。
- [x] S3-T2: 新增前端本地提交摘要存储工具，用 `request_id` 关联 form summary / attachment summary / scenario flags。
- [x] S3-T3: 重构 `SubmitExpense` 为多区块复杂表单，含场景字段、异常勾选、附件分类与预览。
- [x] S3-T4: 增强 `TaskList`，增加统计卡、关键词搜索、摘要列、异常标签和更真实的空状态。
- [x] S3-T5: 增强 `TaskDetail`，展示本地提交摘要、附件摘要、异常场景与原始结果。
- [x] S3-T6: 同步 `.ai_state/design.md`、前端对接文档与 README 的 UI 使用说明。
- [x] S3-T7: 运行 `cd ui && npm run build`、`UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`、`UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`。

### Risks

- 后端任务列表不返回完整 form payload，因此列表业务摘要只能依赖 `localStorage`；跨浏览器/清缓存后会降级为只展示后端字段。
- 字段很多会让单页变重，需要用分区、默认值和场景预设降低填报成本。
- 前端模板字段只是示例 UI 模型，不能再被文档或测试描述成 Python 必填契约。
