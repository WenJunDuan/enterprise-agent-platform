---
sprint_slug: "2026-08-14-trace-storage-governance"
path: "Feature"
created: "2026-08-14"
last_updated: "2026-08-14"
executor: "S1/S2 绿区可主 agent 直做；如并行则 generator subagent"
---

# Design — 业务数据 / 运行日志分类治理 + 评标 trace 完整留存

## 背景

用户提出的定性（原话要点）：**评标与审核的过程数据是「业务数据」，与「纯粹的运行日志、报错日志」不一样**，要求把两者整理清楚，并「把整个过程都保存下来」。

上位动机不是"整理文件"，而是**标注驱动的提示词精简闭环**：完整留存模型的思维链 / 工具调用 / 判断依据 → 人工标注判断准不准 → 用标注集当回归闸 → **敢于删提示词**。

这个动机来自 2026-08-14 生产事故的复盘：`tender-evaluate.md` 38,754B 里约 25% 是「治 XXX 误判」的行为矫正散文（S3 段带 `治` 标注的行占 3,641B/14,486B），棘轮只进不出。**加一段有明确动机（刚出事故），删一段没有任何依据**——没有回归标注集，谁也不敢删。标注集是唯一能让提示词缩短的工具。

对照 Claude Code：它敢不存 coding 案例，一半因为模型会写代码，**另一半因为写错了有闭环兜着**（测试红/类型错，模型当场看见并自愈）。本平台的评标 agent 判错了没有任何信号回流——JSON 通过 schema 校验（形状没问题），没人告诉它判错了——于是唯一防线就是提前把所有坑写进提示词。**要停下棘轮，先得建反馈闭环；要建闭环，先得有数据。**

而现在**每跑一单评标就永久丢一单证据**（见下）。这是本 sprint 的紧迫性来源。

## 已调研的现成方案

- **混合存储（大 blob 走文件 + 可查询元数据进库）**：主 agent 的初步倾向。architect 审议结论是**方向成立但已建成，不要再建**——blob 层 = `data/sessions/events/` JSONL（append-only、gzip 归档、已进备份），索引层 = 既有 `results` + `sessions` 表（verdict / manual_review_reason / tenant / project_id / bid_id / cost / 时间全可 SQL 查），关联键 = `request_id`（事件文件名内嵌 + 每条事件体内均有）。**故驳回"新建 trace 索引表"**：标注 MVP 的检索需求（按 verdict/日期/租户筛单 + 取全 trace）现有两表 + 一次 glob 全覆盖；标注者要标注就必须读 blob 全文，索引表省不掉那次读。
- **OTel / 结构化 tracing 框架**：否决。内网隔离部署，每多一个服务多一份运维；且需求是"留证据供人标注"，不是分布式链路追踪。
- **PostgreSQL 替换 SQLite**：已于本会话拍板否决（单 uvicorn 进程、WAL 已配、库 116KB、隔离网多一个服务不划算）。
- **`override_store`（`server/stores/override_store.py`）**：既有的「人工否决 → 高置信负样本 → distill」回路，是标注标签存储的现成先例。S4 设计标注 schema 时应参照/扩展它，**不另发明一套**。本 sprint 不动它，仅记录。

## 目标

1. 给出**可机械执行**的三类判据（业务数据 / 运行日志 / 可再生缓存），并对现有落盘物逐项归类。
2. 用守卫测试机械保证「业务数据不被当日志清掉」。
3. 补齐 trace 留存缺口，使一次评标的**全过程可回溯、可标注**。

## 非目标

- 不建 trace viewer、不建标注 UI、不建新索引表、不引入事件 schema registry / 版本协商、不上 OTel。**标注 MVP = 人 + JSONL + jq**；以上任何一项在标注流程真实运转前出现即越线。
- 不做 store 模块收拢（判据见下，不构成蔓延）。
- 不设计标注集与回归闸本体（S4，另开 sprint，需先积累数周真实 trace 才有素材）。
- 不动 `server/ocr/`（`2026-08-14-l2-model-routing` sprint 禁区，已核冲突为零交集）。

## 关键决策

### KD1 · 三问决策树（分类判据）

对任何落盘物按序问，第一个命中即归类：

1. **可再生？** 删掉后，仅凭「其余落盘物 + 当前代码」能否确定性重建 → 能 = **可再生缓存**
2. **影响业务结论的可解释性？** 丢了它，某一单业务结论（verdict / 评分 / 证据链）是否无法回溯、解释或标注（判别特征：内容与某个 `request_id` / 案卷绑定）→ 是 = **业务数据**
3. **兜底**：只描述"进程运行得怎么样"，消费者只有排障的人 → **运行日志**

新增落盘物走同一决策树，不依赖清单。Q2 的措辞把**评标 trace 明确划进业务数据**——thinking / tool_call / 中间文本是结论的形成过程，是证据的一部分。

现有落盘物归类见附录 A 表。

### KD2 · 策略矩阵

| 类 | 位置 | 保留期 | 进备份 | maintenance 权限 | 访问 |
|---|---|---|---|---|---|
| 业务数据-结构化 | `platform.sqlite3` | 永久 | 是（`.backup` 在线备份） | **零权限** | SQL |
| 业务数据-trace | `data/sessions/events/` | 永久 | 是（tar） | **仅 gzip，禁 unlink 原文件之外的删除** | 文件，按 `request_id` glob |
| 业务数据-原件 | `data/submissions/` | 7d（已拍板保留期） | 是 | 允许 rmtree（唯一允许删业务数据处，有显式保留期决策） | 文件 |
| 运行日志 | `logs/` | 大小滚动 | 含入（低价值但便宜） | 全权限 | grep |
| 可再生缓存 | `data/ocr-cache/`、`rag_chunks` | 无承诺 | 可跳过（`BACKUP_SKIP_OCR_CACHE=1`） | 全权限 | n/a |

**关键认知：`deploy/backup.sh` 的滚动 3 份是灾备不是留档。** 留档语义完全由"源目录永不删"承担；一旦该语义被破坏，备份 3 天后即不可逆。故 KD3 的守卫测试是**唯一机械防线**，不能省。

### KD3 · maintenance 删除面守卫测试

矩阵是文档，文档拦不住代码。断言 `server/ops/maintenance.py` 的删除类操作（`rmtree` / `unlink`）作用根仅限 {`logs/`, `SUBMISSION_ROOT_DIR`, `data/ocr-cache`}；对 `SESSION_EVENT_DIR` 只允许"先产出 .gz 再 unlink 原文件"；对 `DB_DIR` 零触碰。手法对齐仓库既有 `tests/test_layering.py` 先例。

现存命名债：trace 历史上从 `logs/sessions` 迁到 `data/sessions`（`migrate.py:110`），且 `maintenance.py` 仍把它和日志放在同一函数序列里处理。**当前行为正确（gzip 不删），但无守卫防止未来有人"顺手"改成删除。**

### KD4 · trace 留存补齐（本 sprint 主体）

**现状缺口（已现场核实）**：

- `session_logging.py:98-131` 的 `log_message` 只有 TextBlock / ToolUseBlock / ToolResultBlock 三分支。SDK 确有 `ThinkingBlock`（`claude_agent_sdk/types.py:932`，字段 `thinking` / `signature`），落进 for 循环被**静默跳过**。
- `tool_call.input` / `tool_result.content` 截 **1000 字符**；`session_end.result` 截 2000。
- **model / effort / 案卷指纹：任何地方都没记**（`results` 表无 model 列，events 无 model 字段）。内网将并存 DeepSeek / qwen，无此字段则标注集无法按模型分组，回归闸失去对照轴。

**紧急度修正（architect 驳回主 agent 的初判）**：主 agent 原判"ThinkingBlock 落盘是唯一紧急项"。实际 **`tool_result` 截 1000 是等价甚至更严重的持续丢失**——`/tender-evaluate` S1 用 `Read` 直读评标办法，`tool_result` 是评分依据的**直接来源**，1000 字符等于全丢；且它在**每一单、每种模型形态**都在丢，而 ThinkingBlock 只在 Anthropic 兼容形态丢（deepseek 文本模式的 `<think>` 内嵌 TextBlock 已被 `assistant_text` 捕获，两形态互斥，补分支不会双写）。两者同文件同性质，**必须同片**。

**留存清单与截断策略**：

| 项 | 事件 | 现状 | 目标 |
|---|---|---|---|
| prompt 全文（含脚手架+底稿） | `session_start.prompt` | 全量 ✓ | 保持 |
| model / effort / structured 标志 | `session_start` 新增字段 | **无** | 新增 |
| 案卷指纹 | `session_start` 新增字段 | 无 | 底稿 sha256 + 字节数 + case 路径 |
| thinking | `assistant_thinking` 新事件 | **整块丢弃** | 全量落 `thinking`；**`signature` 不落**（验签 blob，无标注价值，白占体积） |
| 中间 assistant 文本 | `assistant_text` | 全量 ✓ | 保持 |
| tool_call input | `tool_call.input` | 截 1000 | **≤256KB 全文**，超界 UTF-8 安全截断 + 显式标记 + `original_bytes` |
| tool_result | `tool_result.content` | 截 1000 | 同上 |
| 最终 JSON | `session_end.result` | 截 2000 | 同上（`structured_output` 已全量） |
| 重试轮次关联 | — | 每 attempt 独立文件共享 `request_id`，按文件名时间序可辨 | 不加管道，够用即止 |

**为什么保留 256KB 上界而非彻底无界**：`tool_result` 内容来自用户上传案卷，是**信任边界输入**，无界落盘会让单个畸形案卷写爆磁盘——这是边界防御不是过度防御（铁律[反过度工程]双向条款）。取值理由：≥ 底稿注入闸 `TENDER_CONTEXT_MAX_BYTES` 默认 64,000B 的 4 倍，正常业务事件永不触顶，只拦异常。截断必须 UTF-8 安全，复用 `_bound_ocr_block` 已踩过半字符坑的手法。

**元数据字段的取舍分界**：`model` / `effort` / 案卷指纹三项是**过后不可补**的（数据缺失即永久缺失），现在就要；而"给 `results` 加 model 列"可以等（`result_store.py:310` 已有 `existing_columns` ALTER 回填机制，随时可加）。提示词模板版本**不单独建字段**——prompt 全文已落盘，模板 hash 可离线从 trace 推导。抵制"再加个 git commit、再加个环境快照"的滑坡。

### KD5 · store 模块不做收拢（22 个不构成蔓延）

判据（命中任一才算蔓延）：① **重复**：两模块含仅表名不同的同构逻辑；② **散布**：一次单概念变更需同改 ≥2 个 store 模块。

现场核查两条都不命中：任务状态机族**已抽过泛型**（`task_store.py` 300 行 + 4 个 thin binding：`audit_task_store` 23 行 / `ocr_job_store` 19 行 / `tender_compare_task_store` 20 行 / `tender_task_store` 40 行，文件头注明 round4 F7 即那次去重）；session 族 5 文件是 300 行律 + SRP 的门面拆分（`session_store.py` 文件头自述），非重复。**模块数量本身不是判据**——22 是「单库多表 + 每表一模块 + 300 行律」三条既定约束的算术结果。

记账的债（不纳入本批）：`result_store.py`(554) 与 `tender_doc_store.py`(553) 双双越 300 行 P0 线，属既有基线越线，按 coding-standards 记显式豁免——**上界=不再增长，触碰即拆**。

## 切片与排序

- **S1 · trace 完整性**（本 sprint 主体，紧急）：ThinkingBlock 落盘 + 截断解除 + 元数据入头。改动面 `server/common/session_logging.py`（主体）+ `server/common/json_bridge.py`（`SessionLogger(...)` 构造点传 model/effort/指纹，约 3 行）。绿区（2 文件，预计 <100 行）。
- **S2 · 判据固化 + 守卫**（可与 S1 并行）：守卫测试 + `architecture/` 存储长效档（KD1 判据 + KD2 矩阵）。绿区。
- **S3 ·（后置，触发式）** trace 检索便利化：`results.model` 列 / trace 定位 CLI。**触发条件 = 标注工具真实出现**；现在无第二消费者，glob + 现有表已覆盖。
- **S4 ·（另开 sprint）** 标注集与回归闸本体：标注 schema、如何当提示词回归闸、与 `override_store` 的关系。依赖 S1 积累数周真实 trace，属 brainstorm/roadmap 入口。

排序：**S1 → S2（可并）→ 数据积累期 → S4 → S3（被 S4 拉动时）**。

## 影响范围

```text
server/common/session_logging.py      S1 主改动面（缺口在 L98-131、L149）
server/common/json_bridge.py          S1 SessionLogger 构造点 L175（约 3 行）
tests/test_session_trace_capture.py   S1 新建
tests/test_maintenance_guard.py       S2 新建（守卫）
.ai_state/architecture/               S2 存储长效档 + ARCHITECTURE.md 引用
```

零交集确认：与 `2026-08-14-l2-model-routing`（锁 `server/ocr/routing.py`/`engine.py`/`cache.py`，其 AC5 禁 diff 含 tender/audit/routes）**无共享文件，可并行**。

## 风险与缓解

1. **把 trace 塞进 SQLite**（最大架构错误诱惑，因 `results.payload` 列有先例）→ 大 blob 进 WAL 单写库会放大 checkpoint 体积与 `.backup` 锁窗口，且标注是顺序读文件的负载。**守住「blob 走文件、索引走已有表」**。
2. **截断解除做成无界** → 信任边界输入必须留 per-event 硬上界（KD4 已定 256KB）。
3. **改 `session_logging` 时顺手动 `on_progress` 路径** → 前端进度流与落盘在同一消息循环（`json_bridge.py:204-244`），S1 必须是**纯落盘增强**，进度流回归是隐蔽炸点，AC 已放对照项。
4. **元数据字段贪多** → 只收 model/effort/指纹三项（过后不可补者），其余可离线推导的一律不加。
5. **误信备份兜底** → 滚动 3 份使"源目录不删"语义一旦破坏，3 天后不可逆；S2 守卫是唯一机械防线，不可省。
6. **过度工程越线** → 非目标节的禁止清单即红线。

## 验收标准

- [ ] **AC1**（S1 thinking）：构造含 `ThinkingBlock` 的 AssistantMessage 喂 `log_message` → 事件文件出现 `assistant_thinking`，`content` 与 `block.thinking` **逐字节相等**；`signature` **不出现**在落盘记录。
- [ ] **AC2**（S1 截断）：`tool_call.input` / `tool_result.content` / `session_end.result` ≤256KB 时**全文保留**（须含 >1000 字符对照用例，红线基线：当前实现该用例必失败）；>256KB 时 UTF-8 安全截断 + 显式标记 + `original_bytes` 字段，截断后内容可严格 decode。
- [ ] **AC3**（S1 元数据）：`session_start` 含 `model` / `effort` / 底稿指纹字段；**调用方未传时字段缺省、行为不变**（既有测试零修改通过）。
- [ ] **AC4**（S1 防双写）：deepseek 文本模式路径（TextBlock 含 `<think>`）行为**逐字节不变**（对照用例）。
- [ ] **AC5**（S1 进度流零回归）：既有 json_bridge / 进度流测试全绿，`on_progress` 行为无变化。
- [ ] **AC6**（S2 守卫）：断言 maintenance 删除面作用根仅 {`logs/`, `SUBMISSION_ROOT_DIR`, `data/ocr-cache`}；对 `SESSION_EVENT_DIR` 仅"先产出 .gz 再 unlink 原文件"；`DB_DIR` 零触碰。**向 maintenance 加 `rmtree(SESSION_EVENT_DIR)` 的假想变更必须让该测试红**（须实测这条红，不能只写断言）。
- [ ] **AC7**（S2 档案）：KD1 三问判据 + KD2 矩阵入 `architecture/`，含「新增落盘物先过决策树」一句，ARCHITECTURE.md 存储节引用。
- [ ] **AC8**（质量门）：NO_NEW_FAILURES（基线 diff 空）；ruff 净；tdd-evidence 八字段（AC1/AC2/AC6 均有真 red→green）。

## 附录 A · 现有落盘物归类表

| 落盘物 | 归类 | 依据 |
|---|---|---|
| `platform.sqlite3` 业务表（results/sessions/audit_tasks/tender_*/requests/review_deltas/memory_assets/overrides） | 业务数据 | Q2：按 request_id 支撑结论回溯 |
| `platform.sqlite3` 的 `rag_chunks`(FTS5) | 可再生缓存（寄居业务库） | Q1：可从底稿重建（`rag_store.py`） |
| `data/sessions/events/**.jsonl` | **业务数据** | Q2：trace 即结论形成过程（`paths.py:5` 注释已承认此定性） |
| `data/submissions/` 上传原件 | 业务数据（显式短保留豁免） | Q2 命中，已有拍板保留期 7d |
| case 目录内 `units.jsonl` 边车 | 可再生 | Q1：原件在则可重 OCR |
| `data/ocr-cache/` | 可再生缓存 | Q1（`server/ocr/cache.py:20`） |
| `knowledge/` 规则与记忆 | 业务数据 | Q2 + **gitignored 无仓库副本，丢失不可恢复** |
| `logs/app/`、`logs/runtime/`、`logs/serve/` | 运行日志 | Q3 |
| `logs/runtime/app-server/server.pid` / `server.status.json` | 运行日志（进程态） | Q3：重启即重建 |

## 附录 B · 体积估算（支撑"全量留存不需新清理策略"）

单次评标单 attempt：`session_start` ≈120KB（脚手架 50KB + 底稿上限 64KB + 头部）；thinking(xhigh) 10–50KB；中间文本+终 JSON 10–30KB；tool 事件波动最大（S1 直读招标文件章节，按 5–10 次 Read × 均 30KB 估 150–300KB）。**典型单会话 ≈300–500KB**，硬上界（3 attempt × 事件均触 256KB 顶）仍在个位 MB。

按日 20 单：≤10–20MB/天原始，7 天后 gzip（中文 JSON 压缩比 ≈4–5x）→ **年增量约 1–2GB**。内网单机磁盘无压力。**结论：体积不构成对全量留存的反对理由。**
