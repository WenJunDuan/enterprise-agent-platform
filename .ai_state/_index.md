---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "Quick"                     # 最后一次活动: Sprint 4 (Quick)
stage: "ship"                     # 迁移前最后停留阶段
current_sprint_slug: ""
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
    learning: 1
    trick: 0
    decision: 0
    explore: 0
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-04-01-serve-lifespan-and-task-store/plan.md"
  latest_review: "sprints/legacy-2026-06-02-v962-merge/reviews/pass4.md"
  latest_cleanup: ""
  latest_brainstorm: ""
  latest_decisions: []
  latest_lessons: ["compound/2026-06-02-learning-legacy-v962-migration.md"]
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
  test_cmd: "uv run ruff check ."
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

- 2026-06-02 [migrate] v9.6.2(legacy flat) → v9.6.4. 备份见 `.ai_state.backup-*`。


## 历史
- `2026-06-02 07:13:33`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 07:17:29`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 07:24:14`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 07:46:19`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 07:48:36`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 08:04:03`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 08:09:35`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 08:11:11`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 08:20:40`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 08:31:07`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 08:34:21`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 08:53:20`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 09:06:14`: stage=ship sprint=? turn-end


## 历史
- `2026-06-02 09:21:58`: stage=ship sprint=? turn-end
- `2026-06-09 10:12:18`: stage=ship sprint=2026-06-09-audit-agent-docker-repack image=audit-agent artifact=audit-agent.tar run-build-host=true
- `2026-06-09 14:38:00`: stage=ship sprint=2026-06-09-litellm-no-db-repack image=docker.litellm.ai/berriai/litellm:main-stable artifact=litellm-main-stable.tar no-db=true
- `2026-06-09 15:13:00`: stage=ship sprint=2026-06-09-litellm-no-db-repack litellm-config=yaml-only active-env=false proxy-auth-removed=true
- `2026-06-09 19:31:00`: stage=ship sprint=2026-06-09-audit-agent-docker-repack image=audit-agent:latest image_id=57675756e0e5 artifact=/opt/application/audit-agent/audit-agent.tar sha256=5fc2a7a6fc140f5c0ab0a0911881dedf6072c4aa88a773a6a3a210374218f551 build_mode=local-runtime-repack remote=100.107.62.19
- `2026-06-09 20:43:00`: stage=ship sprint=2026-06-09-offline-date-tag-repack audit_image=audit-agent:0609 audit_artifact=/opt/application/audit-agent/audit-agent-0609.tar audit_sha256=526d441ef1c09c536d331cca8ed29dfa06938050a97333f51cd4a387869a3d5b litellm_image=docker.litellm.ai/berriai/litellm:0609 litellm_artifact=/opt/application/litellm/litellm-0609.tar litellm_sha256=3e55d273e9168c0226c785cc5b499b2957b0e68c8507481309f4a8659f00db3d remote=100.107.62.19
- `2026-06-09 20:47:00`: stage=ship sprint=2026-06-09-offline-date-tag-repack cleanup=true removed_images=[audit-agent:latest,docker.litellm.ai/berriai/litellm:main-stable] kept_images=[audit-agent:0609,docker.litellm.ai/berriai/litellm:0609] removed_old_artifacts=[audit-agent.tar,audit-agent.tar.sha256,litellm-main-stable.tar] docker_image_prune_reclaimed=76.26MB remote=100.107.62.19
- `2026-06-10 12:41:00`: stage=ship sprint=2026-06-10-audit-agent-repack audit_image=audit-agent:0610 image_id=90ef0e7b397f artifact=/opt/application/audit-agent/audit-agent-0610.tar sha256=576ca98b8f67548e763d0c8e4ccb9628aebd4f680c3f8f386c4265b2b4fb9470 synced_files=[server/core.py,server/platform/config.py,README.md,docker-compose.yml,.dockerignore] removed_old_audit_artifacts=[audit-agent-0609.tar,audit-agent-0609.tar.sha256] litellm_untouched=true remote=100.107.62.19
- `2026-06-10 14:29:00`: stage=ship sprint=2026-06-10-audit-agent-repack-b2 audit_image=audit-agent:0610b2 image_id=13f9fc10d701 artifact=/opt/application/audit-agent/audit-agent-0610b2.tar sha256=3c4690d09b7a4a11486e1a36a16bd3e20ea39bc9f6de92cce6eaaf608f187d7f synced_files=[server/audit_runner.py,server/core.py,README.md,docker-compose.yml] removed_old_audit_artifacts=[audit-agent-0610.tar,audit-agent-0610.tar.sha256] litellm_untouched=true remote=100.107.62.19
- `2026-06-10 16:47:00`: stage=ship sprint=2026-06-10-audit-agent-repack-b3 audit_image=audit-agent:0610b3 image_id=f96df1d5a343 artifact=/opt/application/audit-agent/audit-agent-0610b3.tar sha256=b913cbfa7c2fdf3deb0aef3033335289e76090674464127c6d0e02f2c9056618 synced_files=[server/core.py,docker-compose.yml] removed_old_audit_artifacts=[audit-agent-0610b2.tar,audit-agent-0610b2.tar.sha256] litellm_untouched=true remote=100.107.62.19
- `2026-06-10 16:58:00`: stage=ship sprint=2026-06-10-audit-agent-repack-b4 audit_image=audit-agent:0610b4 image_id=9488e9173489 artifact=/opt/application/audit-agent/audit-agent-0610b4.tar sha256=8eada129609b12103bc0389e9c2f37c95da8dde681e3b9e4753466e68eaff443 synced_files=[server/core.py,docker-compose.yml] removed_old_audit_artifacts=[audit-agent-0610b3.tar,audit-agent-0610b3.tar.sha256] litellm_untouched=true remote=100.107.62.19
