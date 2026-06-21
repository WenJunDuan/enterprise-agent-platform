---
# Athena PACE 项目状态 (.ai_state/_index.md)
# v9.6.4 schema. 由 athena-migrate 从旧扁平结构 (pre-v9.6.2) 迁移生成于 2026-06-02。
version: "9.6.4"

# === PACE 路由状态 ===
path: "System" # storage-restructure 已 ship(357 passed,codex REWORK→fixed symlink逃逸);前端集成已提交待用户测;external 模式设计待实现
stage: "ship" # 多 sprint 已收口;新会话起点:①实现 external 全地址读取(本地路径+URL,SSRF 防护,设计就绪) ②前端联调
current_sprint_slug: "2026-06-20-external-source-mode"
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
  reviews_count: 48
  cleanup_count: 1
  compound:
    learning: 4
    trick: 0
    decision: 3
    explore: 0
# === Pointers (指向最新相关文件) ===
pointers:
  latest_design: "sprints/2026-06-20-tender-data-model/design.md"
  latest_review: "sprints/2026-06-20-tender-data-model/reviews/codex-design-review.md"
  latest_cleanup: "sprints/2026-06-19-contract-audit-feature/cleanup-pass.md"
  latest_brainstorm: ""
  latest_decisions:
    ["compound/2026-06-20-decision-verification-gate-and-scaffolding.md", "compound/2026-06-19-decision-ops-below-routes-layering.md", "compound/2026-06-19-decision-agent-front-cc-out-of-scope.md"]
      "compound/2026-06-20-decision-verification-gate-and-scaffolding.md",
      "compound/2026-06-19-decision-ops-below-routes-layering.md",
      "compound/2026-06-19-decision-agent-front-cc-out-of-scope.md",
    ]
  latest_lessons:
    ["compound/2026-06-18-learning-absence-is-not-zero.md", "compound/2026-06-17-learning-cross-review-and-soft-timeout.md", "compound/2026-06-17-learning-classify-fix-exposes-latent-bug.md", "compound/2026-06-02-learning-legacy-v962-migration.md"]
      "compound/2026-06-18-learning-absence-is-not-zero.md",
      "compound/2026-06-17-learning-cross-review-and-soft-timeout.md",
      "compound/2026-06-17-learning-classify-fix-exposes-latent-bug.md",
      "compound/2026-06-02-learning-legacy-v962-migration.md",
    ]
  latest_architecture_update: "2026-06-20T10:04:38.538Z"

# === PACE 联动字段 (hook 自动维护) ===
next_action: "本会话(2026-06-20 深夜)收尾,358 passed/ruff,已 push origin/main(后端+state);前端集成已 commit 未 push(待用户测)。完成:tender-data-model goal ship + tender-task-api-parity + 第三章硬编码修 + 存储改造(submissions 域命名空间+tender 项目层级,codex REWORK→fixed symlink逃逸)+ 单 file 字段上传(URL 外读废弃-SSRF)+ 前端 tender-review 接真实 API(codex 集成)。**新会话起点**:①用户端到端测前端(需先把 .env 第 11 行 MODEL_BASE_URL=127.0.0.1:4000 删掉,让 line4 anyrouter 生效;后端 serve+前端 dev,proxy 已配 /tender)有问题就修 ②前端联调若 OK 则 push agent-front。遗留:tender-criteria codex review 待补(codex review --base 13d58a7);dependabot 10 漏洞(依赖,另议)"
last_subagent: "generator"
last_subagent_at: "2026-06-02T09:25:27.661Z"
active_worktrees: ["agent-ab48b114f14b94af4"]
last_critic_round: 0
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
- `2026-06-20 13:56:20`: stage=ship sprint=2026-06-20-external-source-mode turn-end
- `2026-06-20 10:49:49`: stage=ship sprint=2026-06-20-tender-data-model turn-end
- `2026-06-20 08:32:52`: stage=impl sprint=2026-06-20-tender-data-model turn-end
- `2026-06-20 07:57:58`: stage=review sprint=2026-06-20-tender-task-api-parity turn-end
- `2026-06-20 06:53:12`: stage=design sprint=2026-06-20-tender-criteria-from-bid-doc turn-end

- `2026-06-20 02:49:56`: stage=ship sprint=2026-06-20-agent-capability-redesign turn-end
- `2026-06-20 01:47:27`: stage=impl sprint=2026-06-20-agent-capability-redesign turn-end
- `2026-06-19 12:07:21`: stage=ship sprint=2026-06-19-contract-audit-api turn-end
- `2026-06-19 10:20:54`: stage=impl sprint=2026-06-19-contract-audit-feature turn-end
- `2026-06-19 08:33:33`: stage=impl sprint=2026-06-19-tender-ingestion-workflow turn-end

- 2026-06-02 [migrate] v9.6.2(legacy flat) → v9.6.4. 备份见 `.ai_state.backup-*`。
