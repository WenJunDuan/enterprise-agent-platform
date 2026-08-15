---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "Refactor" # 2026-08-15 tender-context-pipeline: 规则层常驻+证据层按项检索(三次上下文事故根治)
stage: "impl"
current_sprint_slug: "2026-08-15-tender-context-pipeline"
current_roadmap_slug: "2026-07-doc-intelligence"
skip_polish: false
skip_architecture_check: false
skip_impl_subagent_check: false # (已随 program ship 释放; 当时理由: subagent-assignments.jsonl 握手台账 hook 未落(结构性问题见 proposals.md P14); events/log 台账在, 各 sprint tdd-evidence+三轮 review 链为实质证据, 不伪造派工记录
skip_runtime_verify: false # Feature 可选; 本 sprint 无真模型窗口，runtime-verify 不列入 Done Contract（AC 全是单测）

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
  features_count: 4
  issues_count: 0
  refactors_count: 2
  systems_count: 10
  reviews_count: 79
  cleanup_count: 7
  compound:
    learning: 16
    trick: 3
    decision: 8
    explore: 2
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-08-15-tender-context-pipeline/design.md" # Fable R1 NEEDS_REVISION 已全响应+S0/S0-B 实测在档
  latest_review: "sprints/2026-08-15-tender-context-pipeline/reviews/impl-pass1.md" # REWORK: F1 主承重墙未接线/F2 回落闸反松 2.3 倍
  latest_cleanup: "sprints/2026-08-12-prompt-architecture/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-07-20-decision-ocr-as-standalone-service.md", "compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md", "compound/2026-07-16-decision-schema-split-tender.md", "compound/2026-07-15-decision-ocr-service-layer.md", "compound/2026-07-02-decision-ocr-routing-ladder.md"]
  latest_lessons: ["compound/2026-08-14-learning-prompt-budget-must-be-per-session.md", "compound/2026-08-13-learning-design-budget-must-account-own-mandates.md", "compound/2026-08-12-learning-review-chain-catches-fix-induced-p0.md", "compound/2026-07-30-learning-document-ingestion-deployment-evidence.md", "compound/2026-07-18-learning-prompt-gate-contradiction-literal-model.md"]
  latest_architecture_update: "2026-08-14T09:26:47.542Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "【2026-08-15 tender-context-pipeline 返工中·用户外出暂停】sprint=2026-08-15-tender-context-pipeline path=Refactor stage=impl。恢复链: ①代码在 worktree `.claude/worktrees/agent-a40c8e9dd8b94062a`(分支 worktree-agent-a40c8e9dd8b94062a), 基线 main f55cdf34, 已 8 commits + 1 个 wip 快照 8e326d0(F1 接线中途, 勿合并) ②Fable 复查判 REWORK, findings 在 sprints/2026-08-15-tender-context-pipeline/reviews/impl-pass1.md(main bf2ce3e): 两个 P0 = F1 主承重墙未接线(load_evidence_context 零调用方/enforce_manual_review 只被自测调用, 已主 agent 独立复核)、F2 回落闸未扣脚手架反比收编前松 2.3 倍; P1 = F3 AC0b 应改判 blocked 且 KD2 多词拆OR未实现、F4 全零命中归宿应改 manual_review、F5 预算耗尽静默饿死、F6 except ValueError 归因面过宽 ③返工顺序: F1 接线+穿透测试 → F2 扣脚手架 → F4 归宿改判 → P1 三项 ④返工完再过一轮 Fable 复查, PASS 才部署 ⑤部署形态: 后端 docker build --build-arg WITH_OCR=1(漏了会缺 pymupdf/paddleocr), 前端 agent-front/deploy/Containerfile.agent-front 需先本地 bun run build; env 改动必须 docker rm -f 重建容器(restart 不重读 --env-file)。生产现役: agent-backend:0815b2 / agent-front:0815b2。用户口径: 评标须 10 分钟内出结论, 超 20 分钟即视为架构问题。"
last_subagent: "codex-exec" # tender-report-dimensions D0-D5 headless (codex 0.142.1, gpt-5.5)；必须 env -u HTTP_PROXY -u HTTPS_PROXY 否则 streaming API 挂起，见 compound/2026-06-25-trick-codex-proxy-hangs-streaming.md
last_subagent_at: "2026-06-25T00:00:00.000Z"
active_worktrees: ["agent-a40c8e9dd8b94062a"] # tender-context-pipeline 返工中, 含 wip 快照 8e326d0, 勿清理
last_critic_round: 4 # demo-full-doc-ocr: R1-R3 修订，R4 PASS
design_changed_after_impl: false # prompt-architecture 实施期 design 修订(beb1ce3)已由 pass2 增量重核覆盖(evaluator 授权范围), 2026-08-13 释放

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
  conventions:
    ["line-length=100", "target=py312", "ruff formatter", "packages=[server]"]
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

2026-07-20（**_index.md 瘦身整理**）: next_action 只保留当前轮+上一轮存档；本节原 2026-06-02 ~ 2026-06-23
的逐会话叙事条目整体裁剪——内容在 git 历史（8eb2a32 之前各版本 _index.md）与对应 sprint 目录 / compound/
中可完整回溯。当前盘面：doc-intelligence 路线图 D1/D2/D3/D6/D7/D8(代码)/D11 + E4 dependabot 已 DONE；
D10 in_progress（②vision 附件预嵌 backlog，卡 vision 模型）；D4/D5/D9 pending。本机产品侧盘面见底，
等部署机窗口（D8 runbook 四指标 / D4 前置 V4Pro 基线锁硬门 / D10② vision 模型）或用户拍板
（D8 复测通过标准量化 / D9 agent-front 红区授权 / 向量二期触发时机）。详见 frontmatter next_action。

## 目录结构 (v9.6.4)

- `sprints/{date}-{slug}/` — 每个 sprint 的 design.md / plan.md / checklist.yaml / reviews/passN.md
- `roadmap/{slug}/` — 大需求拆分 (items.yaml + roadmap.md)
- `architecture/` — 长效架构档案 (ARCHITECTURE.md + {type}-{slug}.md)
- `compound/{date}-{type}-{slug}.md` — 跨 sprint 经验沉淀 (learning/trick/decision/explore)
- `docs/` — 项目参考文档 (开发指南 / 前端对接 / audit-skills)，非状态机文件

## 历史 (由 pace-continuator hook 自动追加, 最多保留近 10 条)
- `2026-07-23 06:08:32`: stage=impl sprint=2026-07-23-tender-case-header turn-end
- `2026-07-20 11:08:44`: stage=polish sprint=2026-07-20-streaming-ocr turn-end
- `2026-07-20 05:11:59`: stage=review sprint=2026-07-20-streaming-ocr turn-end
- `2026-07-20 02:03:28`: stage=design sprint=2026-07-20-streaming-ocr turn-end
- `2026-07-19 04:01:19`: stage=plan sprint=2026-07-18-tender-discipline-residuals turn-end
- `2026-07-19 01:13:36`: stage=impl sprint=2026-07-18-tender-discipline-residuals turn-end
- `2026-07-19 00:32:32`: stage=plan sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-19 00:26:42`: stage=review sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-18 08:22:59`: stage=impl sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-18 06:57:42`: stage=plan sprint=2026-07-18-prompt-single-source turn-end


- 2026-06-02 [migrate] v9.6.2(legacy flat) → v9.6.4. 备份见 `.ai_state.backup-*`。
