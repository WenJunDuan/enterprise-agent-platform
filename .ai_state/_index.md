---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "System" # 评标 durable 硬化(证据可验证性+报价规模+准确度) — Sprint 已 ship,下一推进点待拍板
stage: "ship" # Sprint(evidence-accuracy-hardening) R1-R6 全完成:681绿+ruff,12 commits,main与origin同步(见 goal.md §九)
current_sprint_slug: "2026-06-22-tender-evidence-accuracy-hardening"
current_roadmap_slug: "" # 跨切面 goal，非单一 roadmap item
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
  reviews_count: 52
  cleanup_count: 1
  compound:
    learning: 5
    trick: 0
    decision: 3
    explore: 0
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-06-22-tender-evidence-accuracy-hardening/round-1-evidence-resolution-pipeline/design.md"
  latest_review: "sprints/2026-06-22-tender-evidence-accuracy-hardening/goal.md" # 本 sprint review 为内联 subagent，无 reviews/ 文件；完成状态见 goal.md §九
  latest_cleanup: "sprints/2026-06-19-contract-audit-feature/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-06-20-decision-verification-gate-and-scaffolding.md", "compound/2026-06-19-decision-ops-below-routes-layering.md", "compound/2026-06-19-decision-agent-front-cc-out-of-scope.md"]
  latest_lessons: ["compound/2026-06-22-learning-jsonschema-too-brittle-for-llm-output.md", "compound/2026-06-18-learning-absence-is-not-zero.md", "compound/2026-06-17-learning-cross-review-and-soft-timeout.md", "compound/2026-06-17-learning-classify-fix-exposes-latent-bug.md", "compound/2026-06-02-learning-legacy-v962-migration.md"]
  latest_architecture_update: "2026-06-23T06:38:15.291Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "**进行中 2026-06-23-tender-ui-scoring-fixes**（ZJXH单家 dogfood 驱动，用户 8 条实测问题；分工:前端→codex，后端+.claude→CC）。**CC 已交付**（commit d26d90d+e4ff16b，**已 push origin 同步**，684 绿+ruff）:#8b 上传 10MiB→256MiB；#3 底稿截断 OCR_MAX_FILE_BLOCK_CHARS 200k→600k（实测 evidence 回查 71%→92%、unresolved 8→1）；#6 enrich policy_refs→policy_refs_detail[{rule_id,name,source_text}]（+3测试）；④ tender-evaluate.md 禁 additive 整项 punt + 证据页码取底稿【第N页】锚点（治 deepseek/glm 技术参数 punt + page_mismatch）；#8a OCR-as-skill 能力件 .claude/skills/ocr-page（已自测，wiring 待做）。**前端 #1/#5/#7/#4 已交 sprints/2026-06-23-tender-ui-scoring-fixes/codex-handoff.md**（关键纠偏:#1/#2 是前端没渲染 scoring[]，后端实打 64/70、三模型客观项一致）。**3模型 fixed 重测已完成**(qwen 5/4·deepseek 7/2·glm 8/1;#6 e2e✅ 法定原文显示;④✅ 模型诚实 manual 不瞎打分;价格分全 manual 正确;bid_price 三模型一致 1,316,033.66)。**关键发现:真瓶颈=OCR 扫描证书页盲区**——投标 400 页中 **59 页(资质/业绩/职称/社保/检测报告全是扫描件)native 路由没走云 OCR→底稿空→技术参数/企业实力/负责人评分缺据→manual**(qwen/deepseek 严谨标 manual,glm 宽松给分)。**CC 已完成混合 PDF OCR**(commit 896bfaa Layer1+419ce48 Layer2+a5a4d78 review-fix,**未 push**,703 绿+ruff+format,交叉审查 reviewer/spec 已修 F1/F2/F3/M1):classify `mixed_pdf` 标记 + **计数为主触发**(count≥10 OR ratio>0.5,gate mixed_pdf,env 灰度;纠正原计划纯比例阈值在ZJ 0.147 是 no-op) + **Layer2 subset-into-one-job**(只抽扫描页成临时 PDF 走单 job recognize→回填 native blocks 真实页位,数字页保原生保真;本地抽页失败/云失败/页数不匹配三重回退整份云 OCR) + engine.extract_pdf_subset + _parse_cloud_jsonl 注入连续 page_number + cache v1→v2 + OCR_VL_CLOUD_MAX_WAIT 600→1200。**前端 #1/#5/#7/#4 已由 codex 实现(commit 9a382b8,lint/build/19测绿)**:ScoringDetailTable 复用组件+分项渲染+评标项目明细聚合+compare 分项;#4 报告500 codex 沙箱无法监听端口未复现,代码侧确认无报告API(纯 setScreen)+加固 null 路径,待用户环境复验。**全部已 push origin/main(dc50aa2)**。**CC 剩余**:①#8a wiring 用户拍板**降级不 wire**(子集 OCR 已在确定性流水线自动补回扫描页,on-demand ocr-page skill 价值大降;skill 文件保留可手动用,不接 agent)②真标验收(唯一待办,需起服务跑ZJXH重评:59 扫描页进底稿→技术/业绩/负责人出真分,evidence【第N页】定位准;OCR 云凭证已配,CC 可代跑若用户给 bid 文件路径或起服务)。**codex 侧**:前端 #1/#5/#7/#4(已交 handoff)。详见 sprints/2026-06-23-tender-ui-scoring-fixes/{findings,codex-handoff,per-page-ocr-plan}.md。**①招标人侧合规 MVP 用户已明确永久不做，永久剔除 backlog**。上一 Sprint 2026-06-22-evidence-accuracy 已 ship(R1-R6,见其 goal.md §九)。模型切换:logs/tmp/pick_model.py + env -u ANTHROPIC_* MODEL_*=...(详见 findings)。"
last_subagent: "reviewer"
last_subagent_at: "2026-06-22T06:56:41.825Z"
active_worktrees: [] # git worktree list 仅 main；agent-a13c533445cf2f1e5 已不存在(幽灵清理)
last_critic_round: 0
design_changed_after_impl: false # sprint 已按 6 轮(critic+codex+review)ship 完成，原 in-flight 警告已消解

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

2026-06-23（**ai_state 对账修正 · ⟵ 从这读起**）: 发现 `_index.md` frontmatter YAML 损坏(`latest_decisions`/`latest_lessons` 单行 flow 数组后又跟 block 数组 + 孤立 `]`)→ `yaml.safe_load` 抛 `ParserError` → **所有读 _index.md 的 Athena hook(index-updater/pace-continuator/delivery-gate)静默失败**,这是状态冻结在 2026-06-22 03:11 design 阶段的根因。已修:① 修复坏 YAML(改回单行 flow 数组,已 `python3 -c yaml.safe_load` 验证 parse 通过)。② 对账滞后字段:stage design→ship、active_worktrees 清空(`git worktree list` 仅 main,`agent-a13c533445cf2f1e5` 是幽灵)、design_changed_after_impl→false、last_subagent/at 刷新、pointers 指向本 sprint、next_action 重写为完成态+backlog。③ 补本叙事条目。**Sprint(evidence-accuracy-hardening) R1-R6 实际早已 ship**(12 commits/681 绿/origin 同步,见 `sprints/2026-06-22-tender-evidence-accuracy-hardening/goal.md` §九),只是 index 没跟上。**架构档已补**:architecture/system-tender-evidence-resolution.md + ARCHITECTURE.md 总入口(铁律[架构现状即真相]);**未动 counts**(hook 自维护;YAML 修复后 hook 已自动回填 latest_architecture_update → 自动维护链确认复活)。

2026-06-21（**会话收尾归档 · 用户去 mac mini 部署**）: 本会话全部代码已 push origin/main、421 passed/ruff、
进程全关、交叉 review(codex+reviewer+spec) 无 P0 + cleanup 4 项已修(`10fc2ad`)。**可部署**。
- **评标 goal G1/G2 三指标(有扣有得/扣分明细/上下文章节定位)均已实现并在用户给的 `烛照-标段一v3.pdf` 上跑通**
  (13 项 scored/6 项部分得分/basis 扣分明细/evidence 章节定位)。
- **唯一悬空待决(非阻塞)**：用户认为"投标项目号是中国移动 20000020251114074 与本招标不同"**只是名字不一样、不该整单废标**。
  待用户确认后改 tender-evaluate.md：**项目名/编号不一致 → 重大扣分点+风险标注，不自动废标**(verdict 走正常打分而非 rejected)。
  下会话起点 = 用户确认这条 → 改 prompt → 起服务 UI 实测。
- **部署要点(mac mini)**：`uv sync --extra ocr`(纯 uv sync 会卸 pypdf/openpyxl/docx)；配 `.env`(参照
  `enterprise-agent.env.example`，本机 .env 不入库)：MODEL_BASE_URL/AUTH_TOKEN/MODEL_NAME、OCR_CLOUD+OCR_VL_*、
  TENANT_KEYS、CORS_ALLOWED_ORIGINS 改成 mac mini 地址；可选 TENDER_TIMEOUT_SEC/CLAUDE_MAX_BUFFER_BYTES/
  OCR_MAX_FILE_BLOCK_CHARS/TENDER_CONTRACT_MAX_RETRY。前端 `npm --prefix agent-front run build` + 后端
  `uv run python -m server.cli serve`(或 SERVE_UI_DIST=true 由后端托管 dist)。

2026-06-21（**GOAL 立项：评标逐项扣分+证据定位**）: 用户实测设为 goal「持续优化直到满足」：
G1 满分扣减(不要一律不通过/0,已识别的问题应扣几分) + G2 证据定位准确(定位项=实际找到的)。详见
`sprints/2026-06-21-tender-scoring-goal/goal.md`。**已停所有在途任务**(2 tender reclaimed)、代码全在 origin/main。
**关键约束**:当前测试标(烛照-标段一v3.pdf)封面是中国移动 20000020251114074 项目→对华为南通是真废标(逐项 0 正确),
**G1 满分扣减路径必须用真投华为南通的标才能验**(用户侧 TODO 提供匹配标)。下一步=等匹配标→改 tender-evaluate.md
G1/G2 指令→真标实测验收。

另:本会话稍早还修了 tender 零重试(`763dbeb` 加重试环,治 deepseek 文本模式偶发不出 JSON,同标重跑可成)。

2026-06-21（实测驱动修复会话）: 用户端到端实测 audit/tender/ocr，连续修一批真问题，全部 push origin/main，
418 passed/ruff/前端 lint+build 过。

**已上线（origin/main，最新→旧）**：
- `0a0d1bb` 报销+评标前端实测修复（**codex 按契约实施**：报销 7 项 + 评标 T1-T5 废标显因/右上角评分汇总/进度按名册派生/compare 停轮询/评分区高度+左侧逐项扣分）。
- `eed8765` **OCR 自适应抽取**：`/ocr/fill` 无 schema → 字段集由文档决定（修"回填被写死项目备案表框死、文档不匹配全空"）。前后端全栈 + 5 单测。
- `774feb7` tender 文本模式 + JSON 硬化 + 输出 token（修大底稿 165K 下 SDK 结构化输出 error_max_structured_output_retries）。
- `2c693b0` OCR 截断 40K→200K（百页扫描标书不再被静默砍；env OCR_MAX_FILE_BLOCK_CHARS 可调）。
- `1b2d289` 报销 prompt 硬化（字符串值禁半角双引号→防非法 JSON 解析失败）。
- `21dd161` audit 非 manual_review 剥离残留 manual_review_reason。
- `9f06853` 移除 MAX_BUDGET_USD 成本封顶 + max_buffer_size 默认 20MiB（深度交叉 review PASS）。

**实测结论**：audit 通过；OCR 自适应通过（**慢，待优化**）；tender 评标技术链路通（能读全标书+提取 14 项 scoring+逐项判定）。
**tender 数据已彻底清空**（用户重测起点，projects/tasks/results/compare 全清 + 提交目录删；DB 备份 logs/platform.sqlite3.bak-before-tender-wipe）。

**Backlog（待优化，非阻塞）**：
- **OCR 速度慢**（用户 2026-06-21 实测反馈，待优化）：/ocr/fill 自适应一次识别+模型映射较慢；云 OCR(158 页扫描)+大底稿(200K)+模型映射串行。优化方向候选：识别/映射并行或流式、分页增量、底稿按需截断、云 OCR 并发、命中缓存。
- tender 评分"满分扣减"路径**仍未用真实匹配标验证过**：现有测试标(烛照-标段一v3.pdf)封面是中国移动 20000020251114074 项目(非华为南通)→ 正确废标；需一份真投华为南通的标才能验逐项扣分非 0。
- 老遗留：tender-criteria codex review 待补；dependabot 11 漏洞(依赖)。

---

2026-06-21（A/B/C 连做会话）: 用户指令"先 A 做完 → B → C"，三项全落地，409 passed/ruff，
A+B 已 commit（`dfec5fe`/`fe6f3dc`，**未 push**，等用户确认后推）。

**A —— .claude 域装配 sprint P1 完成**（`dfec5fe`）：抽 `server/common/domain_profile.py` =
`DomainProfile` 注册表 + `assemble_domain_prompt` 通用装配器（仅依赖 platform，满足分层 common 不 import 域）；
`EXPENSE_PROFILE` 留 `audit/runner.py`；runner 公共面（build_inline_audit_prompt / load_case_block /
load_expense_rules / _resolve_case_dir）改薄委托，调用点+旧测试零破坏。**纯重构零行为变化**：critic F2
字节级回归——重构前对固定 fixture 生成 golden 快照（`tests/fixtures/domain_profile/golden_*.txt`），
装配器与委托后的 build 两路均逐字节一致。**下一步 = P2**（audit 指令外移 `.claude/domains/expense/instructions.md`）。

**B —— OCR P4 端到端验证通过 + 修真 bug**（`fe6f3dc`）：retry tender `772aa513`。首轮 **failed**，抽出新真 bug：
claude-agent-sdk 默认单条 stdout JSON **1MiB 缓冲上限**被突破（注入数十 KB OCR 底稿 + agent 直读大 PDF
的 tool_result）→ `JSON message exceeded maximum buffer size`。修复：`build_options` 设
`max_buffer_size=10MiB`（env `CLAUDE_MAX_BUFFER_BYTES` 可调）。**重跑 completed**：agent 经 OCR 底稿
读懂招标/投标两份文件，给出**有据结论**（投标文件"烛照-标段一v3.pdf"实为另一项目[中国移动 20000020251114074]
应答 + 逾期 → `rejected`，引 `tender_evalmethod_005/006/008`，claim_id=示例云平台有限公司）。
**P4 OCR 注入确证生效，不再因读不了 PDF 降级**。注：该 fixture 投标是错投标，正确废标而非打分；要演示评分路径
需一份真正对应本招标的投标文件。

**C —— 前端端到端联调（自动部分全通）**：前端集成早已在 origin/main（旧"未 push"是勘误）。lint ✓ / build ✓
（tender-review chunk 编译过）/ vite dev(5173) proxy → 后端(9999) 转发取 tender 结论 ✓ / SPA 首页 200 ✓。
`agent-front/.env.dev` 本地指向改 `127.0.0.1:9999`（本地 dev 覆盖，含 key，**不入库**）。**剩用户手动点 UI 验收**
（无浏览器无法代跑）；agent-front 无实质待 push 内容。服务已停。

**C2 —— 移除成本封顶 + buffer 20MiB + 深度交叉 review**（`9f06853`）：按用户要求彻底删 `MAX_BUDGET_USD`
成本封顶（build_options defaults + enterprise-agent.env.example + 本地 .env + README 全清），成本改由
`AUDIT_INLINE_MAX_TURNS=8`+`AUDIT_TIMEOUT_SEC`+`MAX_CONCURRENT_AUDITS` 三闸约束（示例配置已注明）；
`max_buffer_size` 默认 10→20MiB（env `CLAUDE_MAX_BUFFER_BYTES` 可调），文档化进示例+README。
**深度交叉 review**（reviewer+spec-compliance+evaluator）**VERDICT=PASS 4.25/5,无 P0**;P1（README 残留/
运维边界说明）当场修掉;P2 留下 sprint（EXPENSE_PROFILE 接入消费点 / load_expense_rules 走 profile）。

**当前状态 = 本地领先 origin/main 3 commit（A `dfec5fe` / B `fe6f3dc` / C `9f06853`），410 passed/ruff，
可部署。用户准备叫 codex 部署。待决**：① 是否 push origin/main（codex 远端拉取需要）；② 是否继续 A 的 P2/P3（tender lean）。

2026-06-21（会话边界 · 重开起点）: 上一长会话两件大事到位，状态全 push origin/main。

**① OCR 域强化 sprint —— P1+P2+云+P4 全完成**（`6aa3792`→`63e0bb8`→`a5c4bcd`，385 passed/ruff）：
- P1 pymupdf 文本层直读(find_tables) / P2 置信度 `file_clarity` / 云 OCR(`OCR_CLOUD` 开关, aistudio PaddleOCR-VL,
  certifi SSL) / **P4 OCR 预处理注入 audit+tender**(底稿进上下文，模型不再 Read PDF)。实测:烛照标书 10MB pymupdf
  0.5s/17 表;云 OCR 5.9s。
- **依赖坑**:OCR 在 `ocr` extra → 装 `uv sync --extra ocr`(纯 uv sync 会卸 pypdf/openpyxl/docx);pymupdf+certifi 已进 extra;机器已装 poppler。
- **待办(非阻塞)**:① **端到端验证 P4** = retry tender `772aa513`(现有 OCR 底稿+poppler，应真出评分不再降级);
  ② 云响应置信度接出(现 `clarity=unknown`，照实际 jsonl `layoutParsingResults` 结构再接);③ tender-evaluate 命令提一句"优先用底稿"。

**② 新 sprint：.claude 域驱动上下文装配 —— design 就绪待实现**（`sprints/2026-06-21-claude-domain-context-assembly/design.md`，
critic R1 **APPROVE-WITH-CHANGES** 已纳入）：诊断 = tender 内联流走 `["project"]` 载全本 CLAUDE.md(背无关 expense/system 细节)=真挤占;
audit 已 lean(`AUDIT_LEAN_CONTEXT`→`setting_sources=[]`)是模式来源。方案 = `DomainProfile` 注册表 + 通用 `assemble_domain_prompt` 装配器 +
域指令外移 `.claude/domains/{域}/instructions.md` + tender 对齐 audit(lean) + CLAUDE.md 瘦成路由器。
- **核心 = P1-P3(tender lean)**;P4 CLAUDE.md 瘦身 = 最低优先级卫生(生产全走 inline worker，CLAUDE.md 只在 CC 对话时生效)。
- **关键(critic)**:F1 tender 必须 `run_agent_json(…, setting_sources=[])` **放弃 run_command_json**(否则没真 lean);F2 P2 字节级
  prompt 比对;F5 P3 值级回归(烛照/张三 case 前后 verdict/claim_id/score 一致);F3 tender-evaluate.md 标 deprecated 保留;F4 system 排除本 sprint。
- **下会话起点 = 用户确认设计 → 跑 P1**(抽装配器，原样包住 audit，零行为 + 字节级单测)。

**老遗留**:tender-criteria codex review 待补(`codex review --base 13d58a7`);dependabot 10 漏洞;前端 agent-front 集成已 commit(待端到端测+push)。
模型现状:用户切 `deepseek-v4-pro[1M]`(api.deepseek.com/anthropic);OCR 走 `OCR_CLOUD=1` 云服务。

2026-06-21（OCR 域强化 sprint · P1+P2+云路径落地）: 依用户设计 `sprints/2026-06-21-ocr-domain-hardening/
design.md` 实施。**P1**(`6aa3792`)：native `read_pdf_text` pypdf→**pymupdf**(get_text 阅读顺序 + find_tables
抽表)；`_render_body` 同渲染 blocks+tables(旧逻辑 tables 分支吃掉 blocks 丢正文)。**P2**：`file_clarity`
(clear/low/unknown/failed)确定性置信度信号 + 底稿显式标注；engine `_page_confidence` 把 PaddleOCR-VL 逐块
score 接出。**云 OCR**(`63e0bb8`)：LiteLLM 内网不可用 → 接 **aistudio 线上 PaddleOCR-VL**(异步 job-poll)。
`OCR_CLOUD=1` 走云 / =0 走 litellm/本地，一套 `OCR_VL_SERVER_URL/API_KEY/MODEL_NAME` 换值即切；
`_recognize_via_paddle_cloud`(urllib multipart→轮询带总超时→取 jsonl，只取文本不下图)+ certifi 修 SSL
(macOS CERTIFICATE_VERIFY_FAILED)。**活体验证 5.9s 出真实中文底稿**(河道护栏概算/590万，印章检出)。**377 passed/ruff**。
- 依赖坑：OCR 全在 `ocr` extra，装 **`uv sync --extra ocr`**(纯 uv sync 会卸 pypdf/openpyxl/docx)；pymupdf
  之前声明未装(P1 才暴露)；certifi 已进 ocr extra。
- 遗留(非阻塞)：云响应 `clarity=unknown`(逐块 score 字段没对上 `_page_confidence`，文本完美；照实际 jsonl
  结构再接)；3 个 OCR commit(`ed74bc8`→`6aa3792`→`63e0bb8`)本地未推。
- **下一步 = P4**：把 `extract_dir+build_extraction_block` 接进 `tender_worker`(run_command_json 前) +
  `audit_worker`(build_inline_audit_prompt 内)做确定性 OCR 预处理 → 发票/标书审核真用上 OCR，且彻底绕开模型
  自己 Read PDF 卡 poppler 的脆弱点(round4「OCR 未接」缺口)。

2026-06-21（凌晨 · 真实评测验证 + 两后端 bug 修复）: 用户授权经 **server API** 跑真实 audit/tender 评测
（不直连 Claude）。首轮**两单皆 failed**，抽出两真 bug：① **audit schema 闸误杀**——`[1M]` 模型输出常漏
server 元数据(claim_id/reviewed_by/timestamp)+ risk_dimensions 给成对象，G1 在 enrich 前硬校验原始输出 →
反复重试至失败；② **tender 600s 超时**(单步 `[1M]`≈114s × 五步 > 600s)。**两个都修+重跑验证**：
- 修复 `517ca1f`（已 push origin/main）：`contract.py` SchemaProcessor 加 `normalize` 相(硬校验前盖元数据)+
  线程 request_id(顺序 normalize→硬校验→语义闸→enrich)；`output_contracts.py` `normalize_audit_result`
  (claim_id 缺→request_id / reviewed_by / timestamp / extracted_data 默认 + 复用 coerce/cleanse 规整)；
  `json_bridge.py` 透传 request_id；语义承重闸(verdict/policy_ref/评分一致性)**不放松**。363 passed/ruff。
- tender 超时 600→1200 走 `.env`(本机 gitignored；audit 亦 600)。
- **重跑两单皆 completed**：audit 真实 `manual_review`(claim_id=request_id 服务端盖章=修复生效铁证)；
  tender 真实投标人 **示例云平台有限公司**(不再假名)，schema 合规。
- ⚠️ **新发现第 3 问题(backlog,本次未修)**：tender **评分为空**=agent 子进程**读不了 PDF**
  (结论 `extracted_data.blocker`/explanation："本机缺少 PDF 解析能力"，卡 S1 取评标办法)→ 正确降级 manual_review。
  日志线索：`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` 硬化强制权限 default，疑 Read 工具/PDF 读取被挡；audit 不受影响
  (读 audit-request.json 非 PDF)。**用户选"先 push，PDF 暂缓"**。下次起点：查子进程 PDF 读取(env-scrub/allowedTools)
  或 tender 接 OCR。服务已停；评测结论持久化在 `data/db`，重启可回看。

2026-06-20（深夜末2 · e2e 联调 + UI 改造分工，**进行中**）: 用户端到端测前端。起后端 9999 +
前端 5173(vite)，proxy 指本机，全链路 200 通。修真 bug：① `.env` line11 误置
`MODEL_BASE_URL=127.0.0.1:4000` 覆盖 line4 anyrouter(dotenv 后值生效)→ 已注释（OCR 自走
`OCR_VL_SERVER_URL`，见 `server/ocr/engine.py`，与 MODEL_BASE_URL 无关）；② `agent-front/.env.dev`
proxy `192.168.1.47`→`127.0.0.1:9999`。**模型(待验证)**：anyrouter 拒纯 `claude-opus-4-8` 强制 1m；
用户改 `MODEL_NAME=claude-opus-4-8[1M]` 可路由但报销 180s 超时 → 加 `AUDIT_TIMEOUT_SEC=600`
（评标本就 `TENDER_TIMEOUT_SEC=600`）。**真实评标/审核尚未成功跑通一次**（"投标人假名"=评标 failed
占位，待跑通验证；回退备选小写 `[1m]`）。**UI 改造分工(用户测试反馈~10 项)**：契约
`sprints/2026-06-20-tender-ui-rework/codex-handoff.md`（A 创建项目可填字段／B 列表复选框+批量删重审+
追加审核入口／C 报销页精简+顶部步骤可点／D tender 步骤样式对齐／E compare 404 前端静默）——
后端仅加 `AUDIT_TIMEOUT_SEC=600`（A①/B⑥ 后端早就绪）。**前端最终由 CC 实现**（用户中途从 codex 收回）：
generator subagent 在 worktree 出第一版（A/B/C/D/E 全项，lint/build/38测绿）→ **交叉审查**（reviewer +
spec-compliance 一致 **REWORK**，唯一阻塞 **B⑤ 批量删/重审**因 `GET /tender/projects` 不返回 bids[] 静默无效）
→ CC 修 F1/F2（批量先 `fetchQuery(getTenderProject)` 取真实 request_id）/F4（allSettled+报失败）/F5/F6/F7/F8/F9，
F3 留（mock `'accepted'` 实为后端真状态）→ patch 合入 main，lint/build/**38 测全绿** → 提交+推送+删 worktree。
评审记录见 `sprints/2026-06-20-tender-ui-rework/reviews/cross-review-pass1.md`。服务仍停（用户要求退出终端）；
**真实评标/审核仍未成功跑通一次，待用户回来验**。**勘误**：更早写的"已 push origin/main"失准，本次推送一并补齐。

2026-06-20（深夜末 · 收尾会话，三候选 + 存储改造 + 前端集成）: 多块连续交付，**358 passed/ruff，36+ commit 已 push origin/main**。
- **tender 评标改造链**(早段)：criteria 直读招标文件第三章→后改为"评标办法位置以实际标书为准"(删第三章硬编码) + tender 任务三件套对齐 audit + tender-data-model goal(招标项目实体+多投标人追加+回看+价格横比 Phase1/2) **已 ship**。
- **存储结构改造** `sprints/2026-06-20-storage-restructure/`：`data/submissions/<tenant>/<domain>/[<project_id>/]<request_id>/`(域命名空间+tender 项目层级)。死数据已清(data/contracts 死合同域+smoke)。codex 设计 APPROVE-WITH-CHANGES + 代码 **REWORK→fixed(symlink 逃逸 P1)**;H4 隔离保持+跨域拒绝+maintenance 适配。
- **上传方式** `sprints/2026-06-20-external-source-mode/`(部分**废弃**)：URL/外部路径全地址读取**砍掉**(SSRF 风险)；改为现有 multipart upload + **新增单 `file` 字段**(besides files[])。两种都客户端推字节,无 SSRF。
- **前端集成** `sprints/2026-06-20-tender-frontend-integration/`：CC 出对接契约 → codex 集成 tender-review 接真实 /tender API(api.ts/use-tender-review-page/组件,lint/test/build 过)。**已 commit 未 push,待用户端到端测**(需 .env 改用 anyrouter)。
- 交叉审查模式固化：每块 codex 设计评审 + codex/cc 代码评审,REWORK→fixed。codex 屡次抓到 cc 漏的真 bug(provisional 缺失/symlink 逃逸/retry 丢 project_id)。

2026-06-20（深夜 · tender 数据模型优化 goal Phase1）: 用户要求"数据模型详细设计 → codex review → 设为 goal
实施"。**设计 + codex 评审 + Phase1 实现全完成**。设计 `sprints/2026-06-20-tender-data-model/design.md`：把
"每次评一家的孤立任务"升级为"**招标项目实体 owns N 家投标评标**"（支持同招标追加多家/按招标查看/结果回看/
Phase2 价格横比）。**codex 设计评审 APPROVE-WITH-CHANGES**（`reviews/codex-design-review.md`，5 findings 全纳入：
名册合并 results∪tasks 防删任务丢人/建 project 幂等/archive 显式参数非**opts/group_id 不泄漏路由/API 收敛 5 端点）；
前端 `agent-front/.../tender-review/types.ts TenderProject` 作 schema 金标准。**Phase1 实现**(429bf5d,325 passed/ruff)：
`tender_project_store`(幂等) + 泛型 TaskStore 加 group_id + results 加 project_id(显式参数透传) + 5 端点
(POST/GET /tender/projects、详情+名册、/projects/{id}/evaluate 追加、/projects/{id}/results 回看) + 命令钉
`extracted_data.tender_project_id`。codex P1.1 回归(删任务后结论仍回看)已测。**Phase2(价格横比/排名/compare)留 backlog**。
下一步候选:Phase2 / 前端对接 / 代码级交叉审查(待用户定)。

2026-06-20（深夜 · tender 评标改造 + server API 对等，两 sprint 落地）: **`tender-criteria-from-bid-doc`
实现完成**(T1-T5)——评标标准改为直读招标文件第三章《评标办法》出会话 `criteria`(新契约
`contracts/tender/criteria.schema.json` + `extracted_data.criteria` 随结论落 SQLite)，翻护栏(直读=权威)，
承重 `policy_refs` 引通则层真实 rule_id / criteria 走 `evidence_chain`(对齐 H1 真伪闸)，清 statute/项目层死引用；
+ 用户运营模型优化(单投标人边界 / 捕获横比数据 / claim_id 稳定化 / criteria 跨标人一致)。cc-review **PASS**
(3 非阻塞 CONCERNS)，codex review **BLOCKED**(gpt-5.5 网关 3 次 stream disconnected，指令固化待恢复补跑)。
**`tender-task-api-parity` 实现完成**——tender 路由补齐 list/retry/delete + 准入闸 + worker F4/F5 加固，与
audit 完全对等(数据回看链路 submit→list→get result 两域可用；store 层泛型 TaskStore + result_store 早已共用)。
**319 passed/ruff**，本会话 6 commits。下一步=前端 tender 页对接(新 sprint，前端 features/tender/ 待建)。
注:删无用记忆 project_model_gateway；tracked tool-trace.jsonl 已 gitignore(防 key 片段入库)。待用户决:是否加
`GET /{域}/results` 历史端点(删任务后仍可回看结论)。

2026-06-20（晚 · 两个新 sprint）: **`backend-hardening` 已 ship** — 收口 round4/round5 两轮一致认定的
基础设施/正确性债（H1 真伪闸默认开+F3 / H2 F6 原子化 / H3 F4·F5 async / H4 F2 租户子树隔离），交叉审查
REWORK→修(M1/F1/F4/E2)→**301 passed/ruff**，8 commits。**`tender-criteria-from-bid-doc` 设计就绪待实现**
（下会话）：评标标准改为从招标文件第三章直读(=会话项目规则)，删预建项目层 `{编号}.rules.json`（已删 r2024007
样例），翻护栏，与 H1 真伪闸对齐(policy_refs 引法规 / criteria 走 evidence_chain)。详见两 sprint 的 design.md/checklist.yaml。
注：`tender_worker` 未吃到 backend-hardening 的 async 加固（另案 backlog）。

2026-06-20（agent-capability-redesign goal **完成**）: 用户驱动的跨切面架构 sprint（依据
`sprints/2026-06-19-review-backend-refactor/reviews/round4-fullstack-review.md`）。五诉求收敛为
**两脊椎（验证闸 + 记忆轴）**，G0-G5 全部触达、两批交叉审查均 **PASS**、**287 passed**、已 push origin/main。

- **G0a** 删 legal/contract + HR 死域（round4 F8，15 文件 + 6 处 un-wire）；**G0b** 泛型化
  `server/stores/task_store.TaskStore` 收敛 audit/tender 重复（F7）。
- **G1 验证闸**（F1 BLOCKER）：`apply_schema_semantics` 加 jsonschema 形校验 + approved/rejected 须引
  ≥1 policy_ref + 引用真伪闸（env 门控 `RULE_REF_CHECK`，默认关）+ 评分 score≤max 一致性。
- **G2** `common/plan.schema.json` + `extracted_data.plan` 形校验（类型化计划，命令可选产出）。
- **G3** 外部企业信用工具脚手架：`server/ops/credit_api.py` + `CreditApiSettings`(env `CREDIT_API_URL/KEY`)
  - `contracts/tools/credit-check.schema.json` + cli `credit-check`；**未配置→manual_review，填 url+key 即用**。
- **G4** memory-query SKILL 三层记忆(制度>案例>工作)+规则版本复检+衰减；**G5** `server/stores/override_store.py`
  - cli `override-result` + distill 消费文档（人工否决→案例记忆 复利回路）。
- 决策见 `compound/2026-06-20-decision-verification-gate-and-scaffolding.md`。
- **backlog + 用户侧 TODO（唯一归宿 = 该 sprint `checklist.yaml` 的 `backlog:` / `user_todo:` 段）**：
  evidence_chain 解析+算术重算（撞「Python 不判断」gotcha）、worker/route 泛型化、G3 评标内自动注入、
  G4/G5 全自动闭环；用户侧：G3 填信用 API key、G4 部署侧改 gitignored 的 case-memory.schema.json。
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
见同目录 `reviews/summary.md` 的 🔴 运维项）。**下一项 item1 `contract-audit-feature` 待 design 阶段启动（next_action 已指向）**；
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
- `2026-06-23 06:41:35`: stage=ship sprint=2026-06-22-tender-evidence-accuracy-hardening turn-end
- `2026-06-22 03:11:05`: stage=design sprint=2026-06-22-tender-evidence-accuracy-hardening turn-end
- `2026-06-21 15:37:29`: stage=ship sprint=2026-06-22-multimodel-tender-optimization turn-end
- `2026-06-21 08:11:37`: stage=ship sprint=2026-06-21-tender-harness-redesign turn-end
- `2026-06-20 13:56:20`: stage=ship sprint=2026-06-20-external-source-mode turn-end
- `2026-06-20 10:49:49`: stage=ship sprint=2026-06-20-tender-data-model turn-end
- `2026-06-20 08:32:52`: stage=impl sprint=2026-06-20-tender-data-model turn-end
- `2026-06-20 07:57:58`: stage=review sprint=2026-06-20-tender-task-api-parity turn-end
- `2026-06-20 06:53:12`: stage=design sprint=2026-06-20-tender-criteria-from-bid-doc turn-end

- `2026-06-20 02:49:56`: stage=ship sprint=2026-06-20-agent-capability-redesign turn-end

- 2026-06-02 [migrate] v9.6.2(legacy flat) → v9.6.4. 备份见 `.ai_state.backup-*`。
