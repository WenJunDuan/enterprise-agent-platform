---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "System" # 文档智能 program 2026-07-doc-intelligence 立项：四波次 D1-D11（地基/质量/结构/体验），旧 tender-program 已收口(S7/S9 结转,S8 用户推迟)
stage: "polish" # 2026-07-20: D9 review PASS(pass1 独立 reviewer 发现 P0 F1+spec PASS→修 merge 176e91c→pass2 主 agent 复审 F1 解决/无新阻塞,955 passed)。进 polish(清 P2-a docstring 过时/P2-b read_pdf_text on_page 旁路+doc/security 扫描)→runtime-verify(需起服务)→ship。pass2.md 存档。pass2 独立子 agent 因断网中断不可恢复,由主 agent 复审(透明记录)
current_sprint_slug: "2026-07-20-streaming-ocr" # D9 页级流式 OCR(立项 2026-07-20; 前 D11 已 done+归档)
current_roadmap_slug: "2026-07-doc-intelligence"
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
  systems_count: 6
  reviews_count: 60
  cleanup_count: 2
  compound:
    learning: 12
    trick: 2
    decision: 8
    explore: 1
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-07-18-tender-discipline-residuals/design.md" # D11 定稿(critic 九条应答, 2026-07-19 全交付);roadmap 见 roadmap/2026-07-doc-intelligence/
  latest_review: "sprints/2026-07-20-streaming-ocr/reviews/pass2.md" # D9 pass2=PASS(F1 修复复审,主 agent;pass1 独立 reviewer 发现 P0+spec PASS);2 P2 留 polish
  latest_cleanup: "sprints/2026-06-19-contract-audit-feature/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-07-20-decision-ocr-as-standalone-service.md", "compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md", "compound/2026-07-16-decision-schema-split-tender.md", "compound/2026-07-15-decision-ocr-service-layer.md", "compound/2026-07-02-decision-ocr-routing-ladder.md"]
  latest_lessons: ["compound/2026-07-18-learning-prompt-gate-contradiction-literal-model.md", "compound/2026-07-18-learning-lazy-import-behavioral-seam.md", "compound/2026-07-15-learning-slots-dataclass-hollow-getattr.md", "compound/2026-07-01-learning-flash-tender-eval-inconsistency.md", "compound/2026-07-01-learning-adversarial-empirical-review-catches-text-leaks.md"]
  latest_architecture_update: "2026-07-20T07:13:21.930Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "【2026-07-20 · _index 瘦身 ship + D9 立项 design 定稿(两轮 critic),待用户 GO impl】① .ai_state 整理 ship(1da3cb5 push):_index 62.7KB→12KB(next_action 只留两轮存档+叙事区裁剪+pointers 刷新指 D11),6 月快照/.DS_Store 清。② 部署机窗口交 codex(用户拍板):D8 runbook=sprints/2026-07-18-d8-transcript-slimming / D4 前置=D1 golden manifest+runbook / D10② vision=items.yaml 注记。③ **D9 页级流式 OCR 立项**(sprint 2026-07-20-streaming-ocr,stage=design 定稿):route-note=Feature 路径,depends_on D4 判软依赖解除(代码核验正交,用户拍 D9 先行),前提修正=**平台无 SSE**(grep 零命中,真实先例=TaskStore submit→poll)。design=方案 A(OCR 任务化 POST /ocr/jobs + 部分结果轮询,SSE 否决留流式二期;粒度自适应 native/VLM 页级、cloud 文件级)。critic round1=NEEDS_REVISION(F1 P0 TaskStore 无增量落点/F2 FITZ_LOCK 临界区/F3 缓存命中绕过+3P2)→Round2 应答=**units.jsonl 边车**(job case_dir 内 per-job lock append,TaskStore(ocr_jobs) 独立表+progress_message 存 {done,total} JSON 计数,不改共享 schema)+buffer-then-fire 锁外回调契约+缓存命中补 from_cache 事件+0单元即 completed/未知 404/recover_stale 保留 partial→critic round2=**APPROVE-WITH-CHANGES**(F1-F6 全 RESOLVED 代码实证;G1 P1=units.jsonl 会被 _iter_files 重扫当文档识别→定案加入 _OCR_EXCLUDED_FILENAMES+重扫不计入断言;G2=progress_message 格式钉死+路径一律服务端派生禁客户端传入,均已并入 design 收尾修订)。plan.md T1-T5 就绪:T1 接缝/T2 端点/T3 worker=黄区后端 subagent,T4 前端渐进渲染=agent-front 红区 worktree(已授权),T5 全量回归 920 基线;执行序 T1→T2/T3 并行→T4。**下一步=用户 GO 即进 impl(GO 前勿写代码)**;其余在册:部署机三项随 codex 窗口 / D8 复测标准量化与向量二期仍待拍 / D10② vision backlog。 ▽上轮存档▽ 【2026-07-20 · Athena harness 9.9.3 ship-契约结构性 bug 根治 + 双仓 push,会话收口】本会话为 harness 维护会话(未碰产品代码,测试基线仍 920 passed/2 skip/ruff 净不变)。收口旧 next_action 挂账 item ③(9.9.3 ship 契约: current_roadmap 非空即要求全 item completed=中程必挂),两修复+一文档全落地: **P1** validateRoadmap 只校验 current sprint 对应 item(slug 尾段匹配)为 done/completed,兄弟 pending 不再挡、错 roadmap 仍 FAIL(Rlues 40b0637); **P2③** ship 契约按变更面分级=轻门禁: 净 diff(对 upstream)≤60 行且仅触及文档/配置/依赖/.ai_state/测试(排除 hooks/settings/源码逻辑)→ 只校验 roadmap 一致性,跳过 review-manifest/tdd-evidence/三件套;源码/harness/超预算走完整契约 fail-closed;.ai_state 计入文件面不计入行预算(规避 token-usage 抖动误判)(Rlues f8c214c); **docs** stages.md ship 节载明 push 门禁合法放行(Rlues 60103b1)。四文件均落 cc+cx 装态(~/.claude+~/.codex)与源仓(Rlues/vibeCoding/{claude,codex}/9.9.3),源==装 diff 逐字节一致。验证: CC 真 hook 调用(stage=ship + .ai_state-only diff→空输出/exit0 轻门通过);CX py_compile + 分类端口 10/10 PASS。EAP .ai_state 记账 f4dac09(proposals P2→FIXED + 本 _index)。**push 正道(关键·替代'切 ship→推→回 plan'绕行)= `ATHENA_ALLOW_PUSH=1 git push`**——pre-bash-guard(CC 认内联 env / CX 认子串)直接放行,零状态篡改零伪造;github push 需加 `-c http.proxy=http://127.0.0.1:6152`(git 子进程不继承代理,报 SSL_ERROR_SYSCALL 即此,curl 能通即证网络 OK);见 memory athena-push-guard-allow-flag。**两仓(Rlues + EAP)origin 均同步无 ahead/behind**。**产品盘面(自 D11/E4 起未变,全卡外部)**: doc-intelligence D1/D2/D3/D6/D7/D8(代码)/D11 DONE + E4 dependabot DONE;D10 in_progress(①直连 ③耗时指标 ④runbook DONE,②vision 附件预嵌=backlog 卡 vision 模型);D4/D5/D9 pending。**下一步全卡部署机/用户方向,本机产品侧盘面见底**: ①部署机窗口=D8 runbook(TENDER_SLIM_CONTEXT=1 真标书跑 S7 harness 成本/时延/一致性跨度/policy_refs 四指标,达标再改默认值)+ D4 前置(V4Pro 基线锁一致性硬门)+ D10② vision 模型;②待用户拍=D8 复测通过标准量化 / D9(agent-front 红区授权,R7 已 done)/ 向量二期触发时机;③harness 侧已无残留。 ▽更早存档已裁剪(2026-07-20 整理)▽ 2026-07-19 及更早的会话收口存档见 git 历史(1da3cb5/8eb2a32 之前各版 _index.md)与对应 sprint 档案(sprints/*/design.md·route-note.md·acceptance.md)。"
last_subagent: "codex-exec" # tender-report-dimensions D0-D5 headless (codex 0.142.1, gpt-5.5)；必须 env -u HTTP_PROXY -u HTTPS_PROXY 否则 streaming API 挂起，见 compound/2026-06-25-trick-codex-proxy-hangs-streaming.md
last_subagent_at: "2026-06-25T00:00:00.000Z"
active_worktrees: [] # git worktree list 仅 main；无其他分支/worktree(2026-06-23 复核确认)
last_critic_round: 2 # D9 design: round1 NEEDS_REVISION(F1 P0 存储无落点/F2 锁临界区/F3 缓存绕过+3P2)→Round2 应答(JSONL 边车+buffer-then-fire+缓存补事件)→round2 APPROVE-WITH-CHANGES(F1-F6 全 RESOLVED;G1 边车文件防重扫入排除名单+G2 格式/路径派生,已并入 design 收尾修订,定稿)
design_changed_after_impl: false # judgment-discipline 核心 R1-R3 已 ship,R4-R7 明确 backlog(非 in-flight)

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
- `2026-07-20 05:11:59`: stage=review sprint=2026-07-20-streaming-ocr turn-end
- `2026-07-20 02:03:28`: stage=design sprint=2026-07-20-streaming-ocr turn-end
- `2026-07-19 04:01:19`: stage=plan sprint=2026-07-18-tender-discipline-residuals turn-end
- `2026-07-19 01:13:36`: stage=impl sprint=2026-07-18-tender-discipline-residuals turn-end
- `2026-07-19 00:32:32`: stage=plan sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-19 00:26:42`: stage=review sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-18 08:22:59`: stage=impl sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-18 06:57:42`: stage=plan sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-18 06:28:29`: stage=ship sprint=2026-07-18-prompt-single-source turn-end
- `2026-07-16 03:27:43`: stage=design sprint=2026-07-16-tender-feature-package turn-end


- 2026-06-02 [migrate] v9.6.2(legacy flat) → v9.6.4. 备份见 `.ai_state.backup-*`。
