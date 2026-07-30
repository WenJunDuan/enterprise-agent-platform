---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "System" # 2026-07-30 demo 完整文档格式/OCR/criteria/双容器部署
stage: "impl" # design 四轮 critic 已 PASS，进入 TDD 实现
current_sprint_slug: "2026-07-30-demo-full-doc-ocr"
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
  features_count: 2
  issues_count: 0
  refactors_count: 0
  systems_count: 6
  reviews_count: 61
  cleanup_count: 2
  compound:
    learning: 12
    trick: 2
    decision: 8
    explore: 1
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-07-30-demo-full-doc-ocr/design.md"
  latest_review: "sprints/2026-07-23-eia-domain-page/reviews/pass1.md" # X1 pass1=PASS(reviewer 0P0/1P1/2P2+spec M1→修 53fd7ac);D9 pass2 见 sprints/2026-07-20-streaming-ocr/reviews/
  latest_cleanup: "sprints/2026-06-19-contract-audit-feature/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions: ["compound/2026-07-20-decision-ocr-as-standalone-service.md", "compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md", "compound/2026-07-16-decision-schema-split-tender.md", "compound/2026-07-15-decision-ocr-service-layer.md", "compound/2026-07-02-decision-ocr-routing-ladder.md"]
  latest_lessons: ["compound/2026-07-18-learning-prompt-gate-contradiction-literal-model.md", "compound/2026-07-18-learning-lazy-import-behavioral-seam.md", "compound/2026-07-15-learning-slots-dataclass-hollow-getattr.md", "compound/2026-07-01-learning-flash-tender-eval-inconsistency.md", "compound/2026-07-01-learning-adversarial-empirical-review-catches-text-leaks.md"]
  latest_architecture_update: "2026-07-20T07:13:21.930Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "【2026-07-23 收口版 · X1+X2 双 DONE 已合入,push 执行中;唯剩 D9 等 SSH 密钥名】**X2 收口**(用户拍板"worktree 和分支代码全部合并提交 push"):merge 4329d91,T4 四证据主 agent 亲跑全绿(后端 981 passed/2 skip+ruff 净;前端 155 pass+build+eslint 净),分支/worktree 全清仅 main;模型违约经用户知情拍板接受;独立 review 双审留 backlog 可后补。**X1 尾迭代**:561205a 删预跑虚假数据+带色 icon → 4f43894 恢复填充示例按钮+删空态提示 → a4512fa 清单卡全宽。**②③已了结**(②X1/X2 均用户知情接受;③generator.md pin 已改 opus)。**push 已完成**:ff10fa3..541bafb,main==origin 同步,16 commits(X1 全程+3 轮用户验收迭代/X2 merge 4329d91/双 sprint 档案)。**唯剩①**:SSH 密钥文件名(root@192.168.1.105 抓 D9 日志→runtime-verify 5 点核对→D9 ship 收口)。 ▽拍板前版本▽ 【2026-07-23 勘误版 · X1 DONE;X2 T1-T3 在分支未 merge;模型违约+hook 三连事故已处置留痕;三项待用户拍板】**待用户输入/拍板**:①**SSH 密钥文件名**——用户令抓 mac mini(root@192.168.1.105)D9 日志,默认钥/config/agent 全无匹配,主 agent 被拒 ls ~/.ssh(尊重),需用户告知文件名或 `ssh-add ~/.ssh/<key>` 后说一声;②**模型违约处置**——`~/.claude/agents/generator.md` frontmatter `model: sonnet` pin 压过 Agent 调用 model:opus 覆盖(transcript 取证 X1 217 条+X2 180+条消息全 sonnet-5),违反用户"禁 sonnet":X1 已 merge 且过全套门禁(独立验+reviewer 0P0+spec+修复),接受 or opus 重做?X2 T1-T3 在分支未 merge,merge or opus 重做?。**已拍板③**:generator.md pin sonnet→opus 已改(2026-07-23 落地,含注释留痕)。**X1 追加 polish 561205a**(用户验收反馈:提交页删预跑期虚假数据——头部材料/类别/受理编号统计盒+AI 分析描述句;batchNo 改 startAnalysis 时经 api 接缝获取、reset 清空;删「加载示例」按钮但 **mock 数据层保留**(用户明示:晚点做真实数据对接,先别删);水土气声换语义色 icon sky/amber/teal/violet 仅染方块;146 pass/build/eslint 净)——用户在 X1 上继续迭代=事实接受 X1 现状,②仅剩 X2 merge-or-重做待拍。**X2 现状**:T1 契约 8baef0f/T2 服务端 5fbf482/T3 前端 d6bc5cc 于分支 `worktree-agent-a9ea79174969a5183`(未 merge);T2 经主 agent 独立验 **981 passed/2 skip+ruff 净**(基线 955+26;fitz 缺失系 uv sync 少 --extra ocr 已恢复);T3 未独立验,T4 四证据未跑。**hook 三连事故(已处置)**:X2 agent worktree 的 Stop hook 反向同步 .ai_state 三次摧毁主仓档案(截为 0 字节/整文件回滚/删除未跟踪 sprint 目录),且主工作区曾被错误切到 agent 分支——worktree 已拆除(分支保留),主工作区复位 main=53fd7ac,全部档案由主 agent 从上下文重建并 commit 固化;**教训:.ai_state 写后即 commit,勿信工作区**;此 hook bug 应报 proposals.md(9.9.3 compact-snapshot/worktree 同步缺陷)。**main 现状**:53fd7ac(X1 merge 2d8d822+review 修复 53fd7ac),领先 origin 6 commits 未推(待 X2 拍板后攒批 ATHENA_ALLOW_PUSH=1+proxy 推)。**D9 挂起**:等 SSH 通后主 agent 亲抓日志按 handoff 5 点核对。 ▽勘误前版本▽ 【2026-07-23 · 双插入 sprint:X1 环评域 DONE + X2 tender 名称留存 impl 进行中(opus worktree),D9 仍待 mac mini】**X1(2026-07-23-eia-domain-page)全流程收口**:design 两轮 critic→opus worktree T1-T4(API 断连断点续跑)→主 agent 独立验→merge 2d8d822→review pass1(reviewer 0P0/1P1/2P2+spec M1 统计条漏做)→修 53fd7ac(死导出/魔数/统计条改案件列表派生)→VERDICT PASS(reviews/pass1.md);146 pass/build/eslint 净;第四域「智能环评检测」上线排 OCR 前(/eia 三步向导+/eia/desk);后端真分析域出界待用户拍(design 方案 C)。**X2(2026-07-23-tender-case-header,用户报告:评标拿到项目名/投标单位名但不留存不显示)**:根因四点(命令只要标识语义/契约无案卷头/worker 不回填/前端只认手填)→design 三轮 critic 硬仗定稿(R1 五条含 P0 锚点错+P0 漏 results 归档链=api.ts:35,70 生产死字段即第一现场;R2 F6 P0 bids 表=tender_doc_store.tender_bid_docs 非 tender_project_store+F7 P1 bid_id join key 缺失手填优先纯空转→采①方案补链;R3 PASS+2 P2 并入)→**opus generator worktree 实施中**:T1 契约 bidder-info.schema+命令纯追加/T2 服务端(ResultRecord 加 bid_id+bidder_name 拍平往返测试+json_bridge&command_adapter 可选 bid_id 透传+tender_bid_docs 三键原子只填空回填+projects.py 三处透出 join 手填)/T3 前端(extractBidderCompanyName 首选 bidder_info 键+resolveBidderDisplayName 倒正为手填最高优先+散单案卷头)/T4 四证据。红线:task_store 共享层零改动/audit 零行为变化/手填永不被覆盖/不编造。**完成后主 agent 独立验 pytest+bun test+build+eslint→merge→review 双审→与 X1 攒批一起 push**(ATHENA_ALLOW_PUSH=1+proxy,见 memory)。深研定版:项目经理/工期/质保/有效期入观察清单(有消费者再钉)。**警示:本会话 _index.md 曾被 hook 截为 0 字节,已从 git ff10fa3 恢复+重放增量——后续编辑前先验 wc -l**。**D9 挂起待外部**:mac mini 实跑日志回传即优先切回收口(5 点核对→ship 契约,详见▽存档▽)。 ▽上轮存档▽ 【2026-07-20 · D9 页级流式 OCR 代码全交付+review PASS+polish,唯缺 mac mini 实跑 runtime-verify(用户亲验+codex 回传日志),会话交接】**D9 sprint 2026-07-20-streaming-ocr 全流程**:design 两轮 critic(round1 NEEDS_REVISION→round2 APPROVE-WITH-CHANGES,F1-F6+G1/G2 units.jsonl 边车方案定稿)→impl T1-T5 逐任务 worktree+主 agent 独立验 merge(T1 回调接缝 ebf9113/T2+T3 端点+worker f36f537/T4 前端 Tabs 双模式 3539392;后端 952+前端 121 绿)→**review pass1 REWORK**(独立 reviewer 对抗审查发现 **P0 F1**:流式回调在 native→OCR 回退路径产生重复/过期页级单元,主 agent 读码确认)→回 impl 修 merge 176e91c(_dispatch_native_pdf_text 抽出+native 不即时发+_emit_pages_from_blocks 从最终/augmented blocks 发,955 passed+F2 三回归 RED 证据)→**pass2 PASS**(pass2 独立子 agent 因用户断网中断不可恢复→主 agent 复审 F1 解决/无新阻塞,透明记录)→**polish**(P2-a docstring 修/P2-b read_pdf_text.on_page 生产旁路→保留+文档化 defer/security+doc 扫描净/ARCHITECTURE 新增 OCR 流式任务层)。全部 merge+push origin(至 **3d80836**,领先→已同步),worktree/分支全清仅 main,955 passed/2 skip/ruff 净。**唯一剩 runtime-verify**(System 契约末环):用户 GO=先 ship 跳本机实跑→改为**用户 mac mini 亲自部署实跑 /ocr/jobs 流式+前端点击流,codex 规整日志回传**作实跑证据。**回传后主 agent**:按 sprints/2026-07-20-streaming-ocr/runtime-verify-handoff.md 核对 5 点(提交202→渐进渲染→终态→双模式并存→边界)+ units.jsonl 页锚/扫描页非空白(F1 核心)→写 runtime-verify.md→达标则完成 ship 契约(review-manifest.yaml 等)+roadmap D9→done+**fable5 全局扫描代码+.ai_state**(用户约定收尾动作,已挂 plan.md)。暴露 bug 则回 impl。**其余在册**:部署机三项(D8 runbook 四指标/D4 前置 V4Pro 基线/D10② vision)随同一 mac mini 窗口;D4 重定义倾向=OCR 拆独立服务(compound 2026-07-20,直读+路由+模型池内聚,本项目只调一个 API,待 D4 窗口确认);D5 pending;D8 复测标准量化/向量二期仍待拍。 ▽上轮存档▽ 【2026-07-20 · Athena harness 9.9.3 ship-契约结构性 bug 根治 + 双仓 push,会话收口】本会话为 harness 维护会话(未碰产品代码,测试基线仍 920 passed/2 skip/ruff 净不变)。收口旧 next_action 挂账 item ③(9.9.3 ship 契约: current_roadmap 非空即要求全 item completed=中程必挂),两修复+一文档全落地: **P1** validateRoadmap 只校验 current sprint 对应 item(slug 尾段匹配)为 done/completed,兄弟 pending 不再挡、错 roadmap 仍 FAIL(Rlues 40b0637); **P2③** ship 契约按变更面分级=轻门禁: 净 diff(对 upstream)≤60 行且仅触及文档/配置/依赖/.ai_state/测试(排除 hooks/settings/源码逻辑)→ 只校验 roadmap 一致性,跳过 review-manifest/tdd-evidence/三件套;源码/harness/超预算走完整契约 fail-closed;.ai_state 计入文件面不计入行预算(规避 token-usage 抖动误判)(Rlues f8c214c); **docs** stages.md ship 节载明 push 门禁合法放行(Rlues 60103b1)。四文件均落 cc+cx 装态(~/.claude+~/.codex)与源仓(Rlues/vibeCoding/{claude,codex}/9.9.3),源==装 diff 逐字节一致。验证: CC 真 hook 调用(stage=ship + .ai_state-only diff→空输出/exit0 轻门通过);CX py_compile + 分类端口 10/10 PASS。EAP .ai_state 记账 f4dac09(proposals P2→FIXED + 本 _index)。**push 正道(关键·替代'切 ship→推→回 plan'绕行)= `ATHENA_ALLOW_PUSH=1 git push`**——pre-bash-guard(CC 认内联 env / CX 认子串)直接放行,零状态篡改零伪造;github push 需加 `-c http.proxy=http://127.0.0.1:6152`(git 子进程不继承代理,报 SSL_ERROR_SYSCALL 即此,curl 能通即证网络 OK);见 memory athena-push-guard-allow-flag。**两仓(Rlues + EAP)origin 均同步无 ahead/behind**。**产品盘面(自 D11/E4 起未变,全卡外部)**: doc-intelligence D1/D2/D3/D6/D7/D8(代码)/D11 DONE + E4 dependabot DONE;D10 in_progress(①直连 ③耗时指标 ④runbook DONE,②vision 附件预嵌=backlog 卡 vision 模型);D4/D5/D9 pending。**下一步全卡部署机/用户方向,本机产品侧盘面见底**: ①部署机窗口=D8 runbook(TENDER_SLIM_CONTEXT=1 真标书跑 S7 harness 成本/时延/一致性跨度/policy_refs 四指标,达标再改默认值)+ D4 前置(V4Pro 基线锁一致性硬门)+ D10② vision 模型;②待用户拍=D8 复测通过标准量化 / D9(agent-front 红区授权,R7 已 done)/ 向量二期触发时机;③harness 侧已无残留。 ▽更早存档已裁剪(2026-07-20 整理)▽ 2026-07-19 及更早的会话收口存档见 git 历史(1da3cb5/8eb2a32 之前各版 _index.md)与对应 sprint 档案(sprints/*/design.md·route-note.md·acceptance.md)。"
last_subagent: "codex-exec" # tender-report-dimensions D0-D5 headless (codex 0.142.1, gpt-5.5)；必须 env -u HTTP_PROXY -u HTTPS_PROXY 否则 streaming API 挂起，见 compound/2026-06-25-trick-codex-proxy-hangs-streaming.md
last_subagent_at: "2026-06-25T00:00:00.000Z"
active_worktrees: ["/Users/mac/workspace/enterprise-agent-platform-demo-full-doc-ocr-0730"]
last_critic_round: 4 # demo-full-doc-ocr: R1-R3 修订，R4 PASS
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
