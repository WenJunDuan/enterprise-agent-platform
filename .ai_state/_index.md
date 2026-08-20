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
    learning: 20
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
  latest_lessons: ["compound/2026-08-19-learning-handoff-claims-need-artifact-proof.md", "compound/2026-06-23-learning-gate-rescues-not-creates.md", "compound/2026-08-18-learning-the-investment-was-dark-in-production.md", "compound/2026-08-17-learning-schema-column-add-needs-caller-sweep.md", "compound/2026-08-17-learning-retrieval-quality-needs-the-chunk-body.md"]
  latest_architecture_update: "2026-08-14T09:26:47.542Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "【2026-08-20 · v2.2 批次详细设计已落盘: sprints/2026-08-15-tender-context-pipeline/design-2026-08-20-v22-transplant.md (K0-K11, 待 critic 评审后开工)】⚠新发现: v2.2 移植令 tracked 且已推 origin/main(7753d22), 正文含真名+身份证号 → K0 历史抹净已扩围(--replace-text+两真名档路径, 一次重写)。执行序照设计任务表: T1 K0 抹净(最先)→T2 case-4→T3/T4 office native+混合页(先复现实验/校准)→T5-T9 Step5 前置件→T10 D2→Step 5 对照(不等 vision)→Step 6(40K 按字)。开工前义务: ①核 d82aca89 结论 ②critic 评设计增补档。另: 前端对接文档已重写为 tender 三接口+iframe 版(.ai_state/docs/)。vision 支线卡 qwen VL 端点】

入口链: sprints/2026-08-15-tender-context-pipeline/handoff-2026-08-18-night.md（含 08-19 订正）→ 纠偏令 v2（效力最高）→ plan-2026-08-18-v2-execution.md。

Step 2 已过闸(782e7d4): case-zj-live n=3 基线回填附录B——墙钟 299s ✅ / manual 6(目标≤2) / 召回 2/7(D1 三跑全中, v2 '按项检索必漏 D1' 预判被证伪) / 客观分 0/3 / 报价勾稽 0/3; 三跑逐条一致=漏检结构性, 靶子=D1 证书扫描页空 + D2 检索错位。

Step 3 已合并(merge 58bf547): case-2/3 金标准落 eval/golden/, 页锚双路互证(pdftotext 空页数与生产 _blank_page_count 逐数相符); 9 条待人工确认清单在 generator 报告(见 subagent-log); 素材两处证伪——5ccbb361 抢救件从未存在、53f94fd0 属另一项目(D2 实证改挂), 订正已落 handoff-night 三节 + compound/2026-08-19-learning-handoff-claims-need-artifact-proof.md。

08-19 全天合并推送九笔, 最新 08e6186。下午: 提交闸改收单等就绪(b7f66cf, 顺带根治 prewarm_oracle 挂死) + Phase A(5ef7d18, 结论义务四裁决入提示词)。晚间 v2.1 第一批四刀: 前端文案透传(1df7407) / agency 可见性打通+facts_precheck(de54b4b, 复制式汇集+跨投标人隔离五专测) / vision-page(ea1e5e7, 提示词净+3B) / 度量修正(d9286d8, 归因23条+同义词带出处+两新列)。全量 1,965P/17F 逐名不变。

下一步: ①双镜像部署 0818b4(Dockerfile 已加 qpdf)+前端——**vision 冒烟前必须配 VISION_PAGE_URL/MODEL(chat 端点, 现役 OCR_VL 是 job API 不能复用)** ②Step 5 前小刀: 服务端 tool_call 计数进任务记录(proposals P1) ③Step 4 D1/D2 ④Step 5 对照(列A验收: 召回≥4/7, 勾稽3/3, manual≤3) ⑤Step 6。待用户裁决: 40K 字 vs 字节口径(proposals)。禁令照旧; P0.6 worktree 勿 prune。"
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
