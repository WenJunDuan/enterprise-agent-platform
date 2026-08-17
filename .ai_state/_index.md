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
  features_count: 3
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
  latest_review: "sprints/2026-08-15-tender-context-pipeline/reviews/impl-pass2.md" # PASS: 两 P0 四 P1 全闭合, 建议先部署验证
  latest_cleanup: "sprints/2026-08-12-prompt-architecture/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-07-20-decision-ocr-as-standalone-service.md", "compound/2026-07-16-decision-schema-split-tender.md", "compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md", "compound/2026-07-15-decision-ocr-service-layer.md", "compound/2026-07-02-decision-ocr-routing-ladder.md"]
  latest_lessons: ["compound/2026-08-14-learning-prompt-budget-must-be-per-session.md", "compound/2026-08-13-learning-design-budget-must-account-own-mandates.md", "compound/2026-08-12-learning-review-chain-catches-fix-induced-p0.md", "compound/2026-07-30-learning-document-ingestion-deployment-evidence.md", "compound/2026-07-18-learning-prompt-gate-contradiction-literal-model.md"]
  latest_architecture_update: "2026-08-15T09:40:14.417Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "【2026-08-17 tender-context-pipeline 耗时治理进行中】sprint=2026-08-15-tender-context-pipeline path=Refactor stage=impl。已完成并推送到 main(f8b6966): ①第一波 7731e16(省略标记不谎报+criteria 竞态等待) ②第二波 9fae313(A 法规/记忆改服务端注入删模型自取 Read; B 底稿在场锁 Glob/Read 例外 ocr-page; C 判0/manual 仲裁 5 处收敛单一决策表; D 契约失败改 resume 修补不整单重跑) ③1a52e92 .doc 兜底档 BEL 还原 Word 表格 ④3701e91 章节定位三修(目录识别/粘连拆行/评审方法标签) ⑤f8b6966 目录跳过规则两处对齐。提示词净减 5,840B(SKILL.md -54%)。两轮实跑记录见 evidence/dry-run-2026-08-17.md。

【实跑实测数据】招标抽取 0.07s/表格21单元格; 结构解析 0.004s/7章正文树/evaluation_method 一次命中无试错; 投标 43MB400页直读 3.2s/19万字; 建索引 0.14s/招标105+投标223 chunk; 按项检索 9/9 命中 1ms(含2字词报价走子串旁路)。

【下一步·未做】⚠️缺陷②native 直读路径无页锚: draft_render.render_body 只对 OCR 引擎产物(pages)渲染【第N页】, native 直读(.doc/文本层PDF 的 blocks)零页锚 → 检索 page_anchor 全是页码未知 → 证据链给不出可回查页码, 回查闸失依据。实测招标底稿 39,056字/0页锚。用户已拍板【先改这个】, 改完再实跑验证+审核出结论。两条路: (推荐)pymupdf 按页取文本拿真实页号 / 或改提示词用章节路径代页码。

【部署】生产现役 agent-backend:0817b1 + agent-front:0815b3(仅含第一波)。第二波及之后全部未部署。部署形态: 后端 docker build --build-arg WITH_OCR=1(漏了缺 pymupdf/paddleocr), 前端需先本地 bun run build; env 改动必须 docker rm -f 重建容器(restart 不重读 --env-file); SSH 必须建长连接 ControlMaster+ControlPersist=60m(反复短连接会打满 sshd MaxStartups)。.env 已注释 TENDER_CONTEXT_MAX_BYTES(备份 .env.before-0817)。

【用户口径】评标须 10 分钟内出结论, 超 20 分钟即视为架构问题; 提示词只删重复表述不删规则; 本机缺 paddleocr/LibreOffice, PDF 云 OCR 与 .doc 转换只能在部署机验。"
last_subagent: "codex-exec" # tender-report-dimensions D0-D5 headless (codex 0.142.1, gpt-5.5)；必须 env -u HTTP_PROXY -u HTTPS_PROXY 否则 streaming API 挂起，见 compound/2026-06-25-trick-codex-proxy-hangs-streaming.md
last_subagent_at: "2026-06-25T00:00:00.000Z"
active_worktrees: [] # 2026-08-17 两个返工 worktree 已合并 369c53e 并清理
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
