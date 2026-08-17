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
  latest_review: "sprints/2026-08-15-tender-context-pipeline/reviews/impl-pass2.md" # PASS: 两 P0 四 P1 全闭合, 建议先部署验证
  latest_cleanup: "sprints/2026-08-12-prompt-architecture/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-07-20-decision-ocr-as-standalone-service.md", "compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md", "compound/2026-07-16-decision-schema-split-tender.md", "compound/2026-07-15-decision-ocr-service-layer.md", "compound/2026-07-02-decision-ocr-routing-ladder.md"]
  latest_lessons: ["compound/2026-08-14-learning-prompt-budget-must-be-per-session.md", "compound/2026-08-13-learning-design-budget-must-account-own-mandates.md", "compound/2026-08-12-learning-review-chain-catches-fix-induced-p0.md", "compound/2026-07-30-learning-document-ingestion-deployment-evidence.md", "compound/2026-07-18-learning-prompt-gate-contradiction-literal-model.md"]
  latest_architecture_update: "2026-08-14T09:26:47.542Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "【2026-08-17 tender-context-pipeline · S5 三缺陷已修完并提交(4802fee), 下一步=部署验证真实模型耗时】sprint=2026-08-15-tender-context-pipeline path=Refactor stage=impl。

★ 前一轮阻塞项已证伪 ★ 第三轮「检索命中错误证据」的判断**不成立**——第四轮逐块打开原文核对: 命中页 315/317/345/349/310 的正文首行分别是 4.7.企业综合实力 / 4.8.类似业绩(含 3 行业绩表) / 4.9.拟派项目负责人 / 4.10.技术参数指标 / 4.6.5.2.维护队伍配备, **全部是正确证据**; 且 trigram phrase 等价子串匹配, 每条命中都字面含查询词, BM25 排序与 tag 过滤都不是问题。第三轮误判源于只看渲染出的出处行没打开正文。**不需要推翻 KD2 检索设计**。

【S5 三缺陷已修完 · 4802fee】用户拍板"三条一起修 + 等修完再部署"。修法与实测(design 增量 S5/KD6 + evidence 第四五轮 + tdd-evidence s5_kd6): ①**出处保真**: 切片按自身首行重推标签(局部十进制识别器, 刻意不动全局 chapter_heading——会同时改招标章节树/目录判定/structure-body 行数不变量), 相符率 0/4 → **27/27**。②**索引去重**: 切片后按正文去重 + 按 (page_start,原序) 稳定排序, 645 → **509 chunk 无重复**, 且 rowid 恒等于文档顺序(续接依赖, 由构造保证)。③**按小节取满**: 命中后沿文档顺序续接、按 per_item_tokens 收满(首块仍只受全局账目管)。技术参数指标 221 → **5,338 字**(含真参数行), 全项 3,480 → **23,594 字**(额度 39.6%), truncated 空。续接三条边界缺一不可(全部实测逼出): 命中块自身不是小节标题就不续接(否则无终点, 既有接线守卫抓出它吃进 8,500 字无关附件) / 止于同族同级下一小节且跨编号族不比较(否则「企业综合实力」吃进「类似业绩」39 块; 硬比层级会让偏离表在第一行被截断) / 空白扫描页跳过但继续往后走(p319-344 只剩页码)。十进制编号必须含小数点且以点收尾——宁可漏认「4.7 企业综合实力」也不能把「21.5 寸液晶显示屏」认成标题。evidence_index 越 300 行硬线故拆出 evidence_retrieval(83+270)。全量 **17 failed/1614 passed**, 与基线逐条同名(本机缺 PIL/paddleocr, 已 git stash 在干净树复跑确认), **新增失败 0**。AC 度量可复跑: `uv run python scripts/measure_tender_evidence.py <投标底稿.txt>`(六项全 PASS)。

【已完成并推送 main(57ce023)】①7731e16 省略标记不谎报+criteria 竞态等待 ②9fae313 第二波四项(法规/记忆改服务端注入删模型自取 Read; 底稿在场锁 Glob/Read 例外 ocr-page; 判0/manual 仲裁 5 处收敛单一决策表; 契约失败改 resume 修补不整单重跑) ③1a52e92 .doc 兜底档 BEL 还原 Word 表格 ④3701e91 章节定位三修(目录识别/粘连拆行/评审方法标签) ⑤f8b6966 目录跳过规则两处对齐(修我自己引入的回归: rag 与 docstructure 跳过规则不一致→招标层退化 10 粗 chunk) ⑥57ce023 .doc 改先转 PDF 拿真实页号。提示词净减 5,840B(SKILL.md -54%)。

【三轮实跑实测】招标抽取 0.07s/表格21单元格; 结构解析 0.004s/7章正文树/evaluation_method 一次命中无试错; 投标 43MB400页直读 3.0-3.2s/19-21万字/399页锚; 建索引 0.15s/招标105+投标645 chunk; 按项检索 9/9 命中 1ms(含2字词报价走子串旁路), 6/9 带真实页锚(其余3个来自招标.doc, 本机无 LibreOffice)。

【部署】生产现役 agent-backend:0817b1 + agent-front:0815b3(仅含第一波)。第二波及 S5 全部未部署——**这是下一步**。三条缺陷已修完, 用户原口径「等修完再部署」的前置条件已满足。**唯一未验的是真实模型耗时**: 注入从 3,480 字涨到 23,594 字(块数 8 → 41), 叠加脚手架 90K 后单次约 115K token, 10 分钟目标须在部署机实测复核(AC7); 若超时, design 已写明按满分权重分配 per-item 额度(大分值项多给), **不回退取量**。另: `直播间总体方案设计`(15 分)仍 unresolved——投标写的是「4.1.项目需求及总体设计方案」, 字面不匹配, 属 S0-B 已记录的召回上限, 按设计走 evidence_unresolved 不判 0。部署形态: 后端 docker build --build-arg WITH_OCR=1(漏了缺 pymupdf/paddleocr), 前端需先本地 bun run build; env 改动必须 docker rm -f 重建容器(restart 不重读 --env-file); SSH 必须建长连接 ControlMaster+ControlPersist=60m(反复短连接打满 sshd MaxStartups, 本会话踩过两次)。.env 已注释 TENDER_CONTEXT_MAX_BYTES(备份 .env.before-0817)。

【用户口径】评标须 10 分钟内出结论, 超 20 分钟即视为架构问题; 提示词只删重复表述不删规则; 本机缺 paddleocr/LibreOffice, PDF 云 OCR 与 .doc 转换只能在部署机验; 跑测试勿并发多个 pytest(会互抢资源假超时)。"
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
