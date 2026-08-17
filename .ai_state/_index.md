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
  reviews_count: 81
  cleanup_count: 7
  compound:
    learning: 18
    trick: 4
    decision: 10
    explore: 3
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-08-15-tender-context-pipeline/design.md" # Fable R1 NEEDS_REVISION 已全响应+S0/S0-B 实测在档
  latest_review: "sprints/2026-08-15-tender-context-pipeline/reviews/impl-pass2.md" # PASS: 两 P0 四 P1 全闭合, 建议先部署验证
  latest_cleanup: "sprints/2026-08-12-prompt-architecture/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-08-17-decision-real-corpus-worktree-only-purge.md", "compound/2026-08-17-decision-bid-auditor-skill-absorption.md", "compound/2026-07-20-decision-ocr-as-standalone-service.md", "compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md", "compound/2026-07-16-decision-schema-split-tender.md"]
  latest_lessons: ["compound/2026-08-17-learning-schema-column-add-needs-caller-sweep.md", "compound/2026-08-17-learning-retrieval-quality-needs-the-chunk-body.md", "compound/2026-08-14-learning-prompt-budget-must-be-per-session.md", "compound/2026-08-13-learning-design-budget-must-account-own-mandates.md", "compound/2026-08-12-learning-review-chain-catches-fix-induced-p0.md"]
  latest_architecture_update: "2026-08-14T09:26:47.542Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "【2026-08-17 会话末复盘 · 下会话唯一入口 = sprints/2026-08-15-tender-context-pipeline/handoff-2026-08-17.md】sprint=2026-08-15-tender-context-pipeline path=Refactor stage=impl。

本日概况: S5 三缺陷修复已推送(4802fee, 全量 17F/1614P 与基线同名); S6 部分重合回退作 WIP 提交(证据层 138 测试绿+ruff 净, **全量回归未跑**——下会话第一件事补跑)。用户四次纠偏(样本只验证不当规格 / 项目数据不进仓库 / 判断放 .claude 侧 Python 只做物理层+有界原语 / 不推翻能跑的), 详见 handoff 第三节。

下会话按 handoff 第四节顺序执行: ①补全量回归 ②修招标抢位(投标层优先, 先造真红, evidence 第六轮有数据) ③开放决策·续接边界去排版化(小设计增量) ④开放决策·KD8 search-bid 有界工具(推翻 KD3b 须 critic 评审) ⑤athena-review 整体 review aa08c4e..HEAD(用户点名 Fable 5 执行并实跑) ⑥golden-case eval+度量脚本实跑, 部署机 E2E 计时(10 分钟目标未验) ⑦全部收口再部署。

遗留风险: 招标抢位未修(首块=招标规定而非投标应答, 影响评分依据); 续接边界对未知编号风格静默变薄; 10 分钟耗时未实测。

【部署】生产现役 agent-backend:0817b1 + agent-front:0815b3(仅第一波)。部署形态: 后端 docker build --build-arg WITH_OCR=1, 前端先本地 bun run build; env 改动须 docker rm -f 重建(restart 不重读 --env-file); SSH 用长连接 ControlMaster+ControlPersist=60m。

【用户口径】评标 10 分钟内出结论, 超 20 分钟=架构问题; 提示词只删重复不删规则; 本机缺 paddleocr/LibreOffice, 云 OCR 与 .doc 转换只能部署机验; 勿并发多个 pytest。"
last_subagent: "codex-exec" # tender-report-dimensions D0-D5 headless (codex 0.142.1, gpt-5.5)；必须 env -u HTTP_PROXY -u HTTPS_PROXY 否则 streaming API 挂起，见 compound/2026-06-25-trick-codex-proxy-hangs-streaming.md
last_subagent_at: "2026-06-25T00:00:00.000Z"
active_worktrees: [] # 2026-08-17 两个返工 worktree 已合并 369c53e 并清理
last_critic_round: 4 # demo-full-doc-ocr: R1-R3 修订，R4 PASS
design_changed_after_impl: true

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
