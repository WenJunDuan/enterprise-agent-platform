---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "Feature"                   # 最后一次活动: 2026-06-17 ocr-http-api (Feature)
stage: "ship"                     # 最后停留阶段: 2026-06-17 ocr-http-api ship
current_sprint_slug: "2026-06-17-ocr-http-api"
current_roadmap_slug: ""
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
  features_count: 0
  issues_count: 0
  refactors_count: 0
  systems_count: 0
  reviews_count: 22
  cleanup_count: 0
  compound:
    learning: 3
    trick: 0
    decision: 0
    explore: 0
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-06-17-ocr-http-api/design.md"
  latest_review: "sprints/legacy-2026-06-02-v962-merge/reviews/pass4.md"
  latest_cleanup: ""
  latest_brainstorm: ""
  latest_decisions: []
  latest_lessons: ["compound/2026-06-17-learning-cross-review-and-soft-timeout.md", "compound/2026-06-17-learning-classify-fix-exposes-latent-bug.md", "compound/2026-06-02-learning-legacy-v962-migration.md"]
  latest_architecture_update: ""

# === PACE 联动字段 (hook 自动维护) ===
next_action: ""
last_subagent: "unknown"
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

# === Fingerprint (index-updater 用于 mtime 比对) ===
fingerprint: ""
---

# Athena Project State Index (v9.6.4)

> 本文件由 Athena 自动维护. 不要手工修改 frontmatter 字段以外的部分除非你知道你在做什么.

## 当前状态

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
- `2026-06-17 10:00:43`: stage=ship sprint=2026-06-17-ocr-http-api turn-end
- `2026-06-17 09:53:50`: stage=ship sprint=  turn-end
- `2026-06-17 09:51:55`: stage=ship sprint=  turn-end
- `2026-06-17 09:48:22`: stage=ship sprint=  turn-end
- `2026-06-17 09:31:54`: stage=ship sprint=  turn-end
- `2026-06-17 09:13:44`: stage=ship sprint=  turn-end
- `2026-06-17 08:51:45`: stage=ship sprint=  turn-end
- `2026-06-17 08:40:42`: stage=ship sprint=  turn-end
- `2026-06-17 07:39:01`: stage=ship sprint=  turn-end
- `2026-06-17 07:17:47`: stage=ship sprint=  turn-end

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
