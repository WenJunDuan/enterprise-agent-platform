---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "System"                    # 活动 sprint=agent-capability-redesign(System,跨切面架构); contract-audit-platform 主体已达成
stage: "ship"                     # agent-capability-redesign G0-G5 全触达+两批交叉审查PASS+287passed+pushed(7eb656a)；backlog/用户TODO 见 pending-actions.md。新会话=干净起点
current_sprint_slug: "2026-06-20-agent-capability-redesign"
current_roadmap_slug: ""          # 跨切面 goal，非单一 roadmap item
skip_polish: false
skip_architecture_check: false

# === 平台与版本 ===
platforms_enabled: ["cc"]
cc_version: ""
cx_version: ""
ag_callable: false

# === 平台原生能力 (athena-init 探测) ===
platform_features:
  cc_subagent_task: true
  cc_ultrathink_supported: false
  cc_isolation_worktree: false
  cc_subagent_stop_hook: false
  cc_worktree_hooks: false
  cc_stop_prompt_hook: false
  cx_spawn_agent: false
  cx_plan_mode_reasoning_effort: false
  cx_spawn_agents_on_csv: false
  ag_parallel_subagents: false
  ag_headless_p: false

# === 工具可用性 (athena-init 探测) ===
tools_available:
  context7_cli: false
  context7_mcp_cx: false
  augment_mcp_cc: false
  augment_mcp_cx: false
  web_search_cc: true
  web_search_cx: false
  rg_available: true
  jq_available: true
  agentshield_cli: false

# === 进度计数 (index-updater hook 自动维护, 不手填) ===
counts:
  features_count: 2
  issues_count: 0
  refactors_count: 0
  systems_count: 2
  reviews_count: 33
  cleanup_count: 1
  compound:
    learning: 4
    trick: 0
    decision: 3
    explore: 0
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-06-19-contract-audit-api/design.md"
  latest_review: "sprints/2026-06-19-contract-audit-api/reviews/summary.md"
  latest_cleanup: "sprints/2026-06-19-contract-audit-feature/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-06-20-decision-verification-gate-and-scaffolding.md", "compound/2026-06-19-decision-ops-below-routes-layering.md", "compound/2026-06-19-decision-agent-front-cc-out-of-scope.md"]
  latest_lessons: ["compound/2026-06-18-learning-absence-is-not-zero.md", "compound/2026-06-17-learning-cross-review-and-soft-timeout.md", "compound/2026-06-17-learning-classify-fix-exposes-latent-bug.md", "compound/2026-06-02-learning-legacy-v962-migration.md"]
  latest_architecture_update: "2026-06-20T01:29:08.936Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "idle:agent-capability-redesign 完成。新会话起点→读 pending-actions.md(用户TODO:G3 信用key/G4 case-memory schema; 代码 backlog) 或用户新方向"
last_subagent: "generator"
last_subagent_at: "2026-06-02T09:25:27.661Z"
active_worktrees: []
last_critic_round: 0
design_changed_after_impl: false

# === 用户偏好 ===
plan_critique_max_rounds: 4
plan_critique_disabled: false
network_in_polish: true

# === 项目元信息 (迁移自旧 project.json) ===
project:
  tech_stack: "python>=3.12, claude-agent-sdk, fastapi, typer, uvicorn"
  test_cmd: "uv run pytest -q"
  build_cmd: "uv build"
  lint_cmd: "uv run ruff check ."
  dev_cmd: "uv run python -m server.cli serve"
  conventions: ["line-length=100", "target=py312", "ruff formatter", "packages=[server]"]
  gotchas:
    - "tests/ 已纳入版本控制，测试回归应与实现同步提交"
    - "knowledge/ 与 data/ 被 .gitignore 忽略，制度源材料不入库"
    - "业务结论必须引用本地 policy_refs + evidence_chain，禁止训练记忆替代"
    - "distill-memory 只保留为 Claude command / CLI 工作流，不暴露 HTTP API"
    - "Python 只运行服务、获取外部输入并提交给 Claude；审核判断和记忆提炼都在 Claude 侧完成"
    - ".claude/CLAUDE.md 是产品业务内容(会进生产 agent 系统提示)，勿往里写 CC 开发/工作约束"
    - "agent-front/ 保持 git 追踪但 CC 默认 out-of-scope(改后端不联动改前端)，详见 compound/2026-06-19-decision-agent-front-cc-out-of-scope.md"

# === Fingerprint (index-updater 用于 mtime 比对) ===
fingerprint: ""
---

# Athena Project State Index (v9.6.4)

> 本文件由 Athena 自动维护. 不要手工修改 frontmatter 字段以外的部分除非你知道你在做什么.

## 当前状态

2026-06-20（agent-capability-redesign goal **完成**）: 用户驱动的跨切面架构 sprint（依据
`sprints/2026-06-19-review-backend-refactor/reviews/round4-fullstack-review.md`）。五诉求收敛为
**两脊椎（验证闸 + 记忆轴）**，G0-G5 全部触达、两批交叉审查均 **PASS**、**287 passed**、已 push origin/main。
- **G0a** 删 legal/contract + HR 死域（round4 F8，15 文件 + 6 处 un-wire）；**G0b** 泛型化
  `server/stores/task_store.TaskStore` 收敛 audit/tender 重复（F7）。
- **G1 验证闸**（F1 BLOCKER）：`apply_schema_semantics` 加 jsonschema 形校验 + approved/rejected 须引
  ≥1 policy_ref + 引用真伪闸（env 门控 `RULE_REF_CHECK`，默认关）+ 评分 score≤max 一致性。
- **G2** `common/plan.schema.json` + `extracted_data.plan` 形校验（类型化计划，命令可选产出）。
- **G3** 外部企业信用工具脚手架：`server/ops/credit_api.py` + `CreditApiSettings`(env `CREDIT_API_URL/KEY`)
  + `contracts/tools/credit-check.schema.json` + cli `credit-check`；**未配置→manual_review，填 url+key 即用**。
- **G4** memory-query SKILL 三层记忆(制度>案例>工作)+规则版本复检+衰减；**G5** `server/stores/override_store.py`
  + cli `override-result` + distill 消费文档（人工否决→案例记忆 复利回路）。
- 决策见 `compound/2026-06-20-decision-verification-gate-and-scaffolding.md`。
- **backlog（诚实，有约束，见 pending-actions.md + 该 sprint checklist.yaml）**：evidence_chain source 解析 +
  算术重算（撞「Python 不判断」gotcha）、worker/route 泛型化、G3 评标内自动注入、G4/G5 全自动闭环。
- **用户侧 TODO**：① G3 拿到信用 API 后填 `enterprise-agent.env` 的 `CREDIT_API_URL/KEY`；
  ② G4 在部署侧改 gitignored 的 `knowledge/_schema/case-memory.schema.json`（domain enum→
  `["expense","tender","ocr"]`，加 valid_until/superseded_by/decided_under_rule_version）。
- 注：`contract-audit-platform` roadmap(item0-3)曾先完成，但其 **item2/item3 的合同域代码已在本 sprint G0a 删除**
  （用户确认只做 tender 评标，不做独立合同审查）。env 示例已去重，只留 `enterprise-agent.env.example`。

2026-06-19（重拍 Sprint 节点）: 梳理整合「进 item1 design」与「先做 tender 路由」两条流，用户拍板
**tender 路由先行**。roadmap `contract-audit-platform` 折入已就绪的 tender sprint，执行序重排为
**Phase 1 `tender-ingestion`（route+CLI+测试+层序决策）→ Phase 2a `contract-audit-feature` → Phase 2b
`contract-audit-api`**。关键整合：item0 延后的「ops/routes 层序决策 + 补守卫」从原计划的 contract-api 处
**前移到 tender sprint（T2.5）**——tender 路由是后重构第一个新路由，只做一次，contract-api 复用；T2 立的
「镜像 audit 的异步路由」模板供 contract-api 照抄；tender T4 端到端 materials-gated 横切（卡用户真标）。
active sprint 切到 `2026-06-19-tender-ingestion-workflow`（Feature, stage=impl, design/plan/checklist 就绪，
从 T1 CLI 起）。详见 `roadmap/contract-audit-platform/{roadmap.md,items.yaml}` + 该 sprint 的 plan.md/checklist.yaml。

2026-06-19: Roadmap `contract-audit-platform` **item0 `review-backend-refactor` 已收口（completed）**。
3 轮深度 review（R1/R2/R3 均 CONCERNS）+ 1 轮 codex 交叉（原判 REWORK：C1 迁移漏 JSONL / C2 litellm 暴露）。
用户 de-scope（demo 阶段 / 内网无风险 / key 自轮替 / litellm 不管）→ 丢弃 C1·F1-key·C2，聚合回落 CONCERNS。
落地 4 项纯代码质量修复（commit `3222e8d`/`def90fe`/`afe060a`/`e0e3c87`）：DRY `_env_int`、SRP 拆
`_cleanse_risk_dimensions`、memory 单坏文件异常隔离、session 测试 patch 正确单例。**241 passed / ruff clean**。
延后项已文档化于 `sprints/2026-06-19-review-backend-refactor/reviews/summary.md`（架构分层守卫需 ops/routes
层序决策转 Phase 1、API 脱敏、并发测试、migrate 可观测性、全部 polish）。运维遗留：litellm key 轮换（仅运维可做，
见 `pending-actions.md`）。**下一项 item1 `contract-audit-feature` 待 design 阶段启动（next_action 已指向）**；
主线方向（item1 合同审计 vs 并行 tender-ingestion sprint）待用户拍板，本次仅收尾 item0 状态。

2026-06-19: Sprint `2026-06-19-tender-ingestion-workflow`（Feature）**计划就绪，待开工**（PACE
current_sprint 仍指 review-backend-refactor，未抢占）。tender 评标 harness 最终定为 **AI 直读、无 OCR、
单 agent 内联五步**（早期 OCR 流水线方案作废）。已落地：`/evaluate-bid` 五步命令 + 域配置 + 契约 + skill +
statute 规则两部（evalmethod 13 / regulation 8）+ 项目样例 r2024007。待 Claude Code 执行：CLI 子命令、
HTTP 路由 `/tender/evaluate`+worker、测试、真标端到端。执行清单见
`sprints/2026-06-19-tender-ingestion-workflow/plan.md` + `checklist.yaml`，设计见同目录 `design.md`。

2026-06-18: Sprint `2026-06-18-tender-domain`（Feature, 对话驱动开发, 事后补档）已 ship。
新增第 5 个业务域 `tender`（招投标评标）：三 agent（extractor/evaluator/reviewer，reviewer 默认关）、
两契约（tender/extract-result + review-delta，audit-result 复用 common）、skill `tender-eval`、
两层规则（statute 通则待生成 + 项目级 `{招标编号}.rules.json`）、CLAUDE.md 路由 + rule-init 接入、
两处 domain enum 加 `tender`。核心：评分项命中 `requires_live_event/external_data/cross_bid_comparison`
一律 `manual_review`，**绝不判 0**（纠正 DeepSeek 把答辩/信用/价格判 0 的范畴错误）。
**零 `server/` 改动**（纯 `.claude/` + `knowledge/` 配置驱动）。验收：jsonschema 21/21 + 川姜花苑 dry-run。
设计见 `sprints/2026-06-18-tender-domain/design.md`，交付见同目录 `ship.md`，
教训见 `compound/2026-06-18-learning-absence-is-not-zero.md`。
注：`knowledge/tender/*` 落盘但被 `.gitignore`（制度源不入库约定）；样例规则 confidence:medium 待核；代码尚未 commit。

2026-06-17: Sprint `2026-06-17-ocr-http-api`（Feature, 对话驱动开发, 事后补档）已 ship。
补齐 OCR 对外 HTTP API（`POST /ocr/extract` 纯识别 + `POST /ocr/fill` 识别+回填）、
前端 OCR 页面（左右分割, 接入 /ocr/fill）、并修复 classify 文本层误判与 pipeline
`pages` 字段冲突。验收: 186 tests + ruff + 前端 build + 真实样例端到端。
设计见 `sprints/2026-06-17-ocr-http-api/design.md`，交付见同目录 `ship.md`，
教训见 `compound/2026-06-17-learning-classify-fix-exposes-latent-bug.md`。
待办: extract-result schema 对齐 / 配 key 验真识别 / 20K 截断。代码尚未 commit。

2026-06-02: 从旧扁平 `.ai_state/` 结构 (pre-v9.6.2) 迁移到 v9.6.4 骨架。
历史 sprint 0-4 的扁平状态文件、`design/` 蓝图与全部 `reviews/` 已归并到
`sprints/legacy-2026-06-02-v962-merge/`；带日期的 superpowers plans/specs 已按
slug 拆分为独立 sprint 目录；`lessons.md` 整体保留为
`compound/2026-06-02-learning-legacy-v962-migration.md`。当前无进行中 sprint。

## 目录结构 (v9.6.4)

- `sprints/{date}-{slug}/` — 每个 sprint 的 design.md / plan.md / checklist.yaml / reviews/passN.md
- `roadmap/{slug}/` — 大需求拆分 (items.yaml + roadmap.md)
- `architecture/` — 长效架构档案 (ARCHITECTURE.md + {type}-{slug}.md)
- `compound/{date}-{type}-{slug}.md` — 跨 sprint 经验沉淀 (learning/trick/decision/explore)
- `docs/` — 项目参考文档 (开发指南 / 前端对接 / audit-skills)，非状态机文件

## 历史 (由 pace-continuator hook 自动追加, 最多保留近 10 条)
- `2026-06-20 01:47:27`: stage=impl sprint=2026-06-20-agent-capability-redesign turn-end
- `2026-06-19 12:07:21`: stage=ship sprint=2026-06-19-contract-audit-api turn-end
- `2026-06-19 10:20:54`: stage=impl sprint=2026-06-19-contract-audit-feature turn-end
- `2026-06-19 08:33:33`: stage=impl sprint=2026-06-19-tender-ingestion-workflow turn-end
- `2026-06-19 08:18:16`: stage=ship sprint=2026-06-19-review-backend-refactor turn-end
- `2026-06-19 01:40:10`: stage=review sprint=2026-06-19-review-backend-refactor turn-end
- `2026-06-18 15:25:31`: stage=ship sprint=2026-06-18-tender-domain turn-end
- `2026-06-17 10:00:43`: stage=ship sprint=2026-06-17-ocr-http-api turn-end
- `2026-06-17 09:53:50`: stage=ship sprint=  turn-end
- `2026-06-17 09:51:55`: stage=ship sprint=  turn-end

- 2026-06-02 [migrate] v9.6.2(legacy flat) → v9.6.4. 备份见 `.ai_state.backup-*`。


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史


## 历史
