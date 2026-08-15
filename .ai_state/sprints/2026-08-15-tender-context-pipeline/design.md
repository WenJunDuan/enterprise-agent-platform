---
sprint_slug: "2026-08-15-tender-context-pipeline"
path: "Refactor"
created: "2026-08-15"
last_updated: "2026-08-15"
executor: "待定（红区，generator subagent + worktree）"
---

# Design — 评标上下文管道：规则层常驻 + 证据层按项检索 + 主链路不静默掉落

## 背景

2026-08-14~15 连续三次生产事故，表面症状各不相同，根子是同一个：**评标把"全部材料塞进单次会话"当作前提**，而投标材料体量已经远超模型可用窗口。

| 日期 | 症状 | 当时的处置 | 事后判断 |
|---|---|---|---|
| 08-14 上午 | `Prompt is too long`，四单无结论 | 加字节预算闸（默认 64,000B） | 治标；且默认值按错误的"64K 窗口"前提定 |
| 08-14 下午 | 截断砍掉「第四章 评审方法和程序」→ 反复 Read 找评分标准 → `error_max_turns` | 预算改按 `MODEL_CONTEXT_WINDOW` 推导（得 2.1MB） | 又错：该 env=1,048,576 而 **bundled CLI 实测约 200K token 即拒**，等于没有闸 |
| 08-15 | 预算设 250KB，截断把**招标文件整份**挤掉（784KB→132KB，只剩投标）→ `insufficient_evidence`，scoring=0 | 改按文件角色四层分配，规则源优先 | 规则保住了，但挤压转嫁到投标证据，模型原话："The rest was cut… this makes the bid evaluation largely impossible" |

**三次都在给同一条降级路径打补丁。** 真正的结论是：**分配算法怎么改都不够——分给谁都不够**。

### 决定性事实（2026-08-15 部署机实测）

```
招标层预热底稿    38,541 字     ready   ← 会按 criteria 瘦身
投标层预热底稿   370,529 字     ready   ← load_doc_layer_context_slim 文档明写
                                          "投标底稿永远原样透传，不参与瘦身"
合计            409,070 字 ≈ 409K token（中文 1字≈1token）
bundled CLI 实测上限        ≈ 200K token
```

即 **主链路（doc_layer_reuse）即使完全正常命中，这一单同样爆窗**。"以前能跑"只是因为投标材料小。

### 另外两个已实测的链路缺陷

1. **主链路在静默掉落**：两层预热都 `ready`，评标却记 `source=inline_ocr`、`bid_id=null`——绕过预热底稿，对整个目录重跑 inline OCR（产 784KB 原始底稿）。前后端 `form_json.bid_id` 字段两侧核对一致，断点在提交时机/状态传递，需查实。**掉落时无任何可见信号**，只在日志里留一行 INFO。
2. **`inline_ocr` 是零瘦身裸路径**：`context_slim` 只挂在 doc_layer 路径上，回落后完全没有内容裁剪，只有我加的字节截断在硬砍。

### 现成基础设施（不必新建）

- `server/ocr/rag.py`：`index_document(structure, body, conn)` + `search(query, conn, tag, limit)`，FTS5 + BM25 + **页锚**（`page_anchor`）
- `server/stores/rag_store.py`：`rag_chunks` 虚拟表，按 `tag` 过滤，BM25 排序
- `server/tender/context_slim.py`：按 criteria 检索招标章节（D8 已建成）
- **缺口**：`context_slim.py:231` 只 `index_document(structure, tender_text)`——**投标文件从未入索引**

## S0 Spike 实测（critic F1 要求，2026-08-15 本机实测，可复跑）

复跑命令见文末附录 B。结论直接推翻了初稿"复用 `rag.search` 即可"的假设：

| 查询 | 命中 | 判定 |
|---|---|---|
| `报价` | **0** | trigram tokenizer 对 <3 字查询恒零命中 |
| `业绩` | **0** | 同上 |
| `施工组织设计 技术标` | **0** | `rag.py:83` 把整串包成单一 phrase，跨空格 trigram 不存在 |
| `报价*`（前缀） | **0** | 前缀符对 trigram 无效 |
| `投标报价` / `施工组织设计` / `项目负责人` | 1 | ≥3 字**单**短语才命中 |
| `"投标报价" OR "报价一览"` | **1** | ✅ 2 字词扩展成 ≥3 字短语再 OR 可命中 |
| `"施工组织设计" OR "技术标"` | **1** | ✅ 多词必须拆 OR，不能单 phrase |

**「报价」「业绩」「工期」「资质」这类 2 字评分项名在评标里极常见**——按初稿直接调 `rag.search`，这些项会全部 `evidence_unresolved`，整单变成"可见但不可用"的第四次失败。

### S0-B 部署机真实数据实测（2026-08-15，投标底稿 163,170 字 / 真实 criteria）

**索引侧全部达标**：

| 指标 | 实测 |
|---|---|
| `build_doc_structure`（投标） | **60 章节 / 0.02s**（待查实项 #3 解决：structure 存在且可用） |
| `index_document` | **146 chunk / 0.02s** ← F7「索引缺失现场补建」可行性坐实 |
| chunk 字数分布 | min 21 / 中位 212 / p90 3,453 / **max 26,107**；**10 个超 8,000 字** ← 二次切分确属必需 |

**召回侧三方案对比**（同一索引，真实 criteria 项 + 常见项名）：

| 方案 | 命中率 | 判定 |
|---|---|---|
| 现行 `rag.search` 裸用 | **38%**（真实项「价格-最后报价」= 0） | 不可用 |
| ≥3 字短语扩展 + 拆 OR（初版 KD2） | 62% | **不可取**：靠硬编码词缀猜措辞，等于"针对单份文件改"，换标书即失效 |
| **普通表子串扫描旁路** | **88% / 4ms** | **采用** |

**根因（比 critic 预判更硬的约束）**：原文含「报价」19 次、Python 侧 10 个 chunk 命中，**而 SQL `LIKE` 与 FTS `MATCH` 双双返回 0**。SQLite FTS5 trigram 表上，`LIKE` 会被优化成走 trigram 索引，因此 **2 字中文词既 MATCH 不到也 LIKE 不到**——不是查询写法问题，是存储层能力边界。

**KD2 据此定案**：新增一张**普通表**存 chunk 文本副本（与 `rag_chunks` 同源写入）；`<3 字`查询走该表子串扫描，`≥3 字`走 FTS5 BM25。文档无关、零硬编码词缀、不改现有招标侧检索行为（无回归风险）。副本存储成本 = 底稿同量级，可接受。

## 目标

1. 单次评标会话的注入量**与投标材料体量脱钩**，稳定在可控区间（目标 ≤60K token，含脚手架）。
2. 评标在 **10 分钟内**出结论（用户口径：超 20 分钟即视为架构/提示词有问题）。
3. 主链路掉落、criteria 失败、证据不足**一律可见**，不得静默降级。
4. 预算口径**单点**，且以实测有效上限为准。

## 非目标

- 不引入外部向量库/embedding 服务（内网隔离，FTS5+BM25 已够；语义检索属二期，触发条件另议）。
- 不改判分语义与输出契约（`audit-result.schema.json` 不动）。
- 不重构 `server/ocr/` 的识别引擎（L2 路由是另一 sprint）。
- 不做前端大改（仅补"链路降级/证据不足"的可见提示）。

## 已调研的现成方案（critic F4；coding-standards P1 硬要求）

| 候选 | 判定 | 理由 |
|---|---|---|
| **按评分项 map-reduce 多次小会话**（每项一次会话，带该项全章证据，最后汇总） | **部分采用**（作为 S3 未达标时的升级路径，本轮不做） | 召回天然更稳（不依赖 BM25，可整章给）；但 20+ 项 × 每次会话开销，10 分钟目标下延迟风险高（现单会话已 20 分钟超时），且跨项一致性（同一证据两项引用冲突）需额外机制。**先做单会话+检索，若 S4 实测达不到 10 分钟或召回不足，再升级到本方案**——届时本节即为决策依据 |
| **预热期对投标做结构化压缩 pass**（按项摘要 + 索引，再注入摘要） | **否决（本轮）** | 摘要环节引入第二次模型判断，误差叠加且不可追溯（摘要丢掉的证据在评标时无从发现）；与"证据必须逐字可回查"的既有纪律冲突 |
| **外部向量库 / embedding 语义检索** | 否决 | 内网隔离部署，多一个服务多一份运维；且 S0 证明 FTS5 经查询构造修正后可用，尚未到需要语义检索的地步。触发条件：S4 实测 BM25 召回率不达标且短语扩展无法补救 |
| **复用现成 `rag.py` search 不改** | **否决（S0 证伪）** | trigram + 单 phrase 包裹导致 2 字项名恒零命中，必须扩展查询构造 |
| **既有 `context_slim` 直接扩到投标** | **采用为基座** | D8 已建成招标侧按 criteria 检索，本设计是把同一机制扩到投标侧 + 修查询构造，不另起炉灶 |

## 关键决策

### KD1 · 规则层常驻，证据层按项检索

```
规则层（常驻全量）  招标 criteria 结构化后 ≈20KB 量级
                    ├ eligibility_rules[]   资格规则
                    └ items[]               评分项（名称/满分/score_mode/tag）

证据层（按需检索）  投标全文入 FTS5 索引（当前完全缺失）
                    ＋招标索引（D8 已建）也参与检索 ← critic F5
                    每项证据预算独立，合计受 KD3 闭式账目约束
```

单会话注入 = 脚手架 + criteria + 当次检索到的证据片段，**与投标是 40 页还是 400 页无关**。

**招标原文不是全撤（critic F5 更正）**：criteria 只有"评分项名 + 满分 + 档次描述"，装不下几十页技术参数表。凡 `basis` 指向招标某章节的评分项（典型："技术偏差：逐条响应第 X 章技术参数"），检索时**同时从招标索引取出对应 chunk**，与投标证据并列注入——否则该类项手里只有一行 criteria，无从比对，必然判错或全部 unresolved。

### KD2 · 检索粒度与页锚保真（按 S0 实测改写）

**查询构造必须适配 trigram tokenizer**（S0 证明"拿来即用"不成立）：

- **双通道检索（S0-B 定案）**：`<3 字`查询走**普通表子串扫描**（88%/4ms，文档无关）；`≥3 字`走 FTS5 BM25。**禁止用硬编码词缀扩展 2 字词**——S0-B 实测该路线仅 62% 且依赖猜测具体标书的措辞，换一份标书即失效。
- **多词必须拆 OR，禁单 phrase**：`"投标报价" OR "报价一览"` 命中，`投标报价 报价一览` 单 phrase 为 0。需**扩展 `rag.py` 的查询构造**（初稿写"尽量只读复用"低估了改动面，此处更正）。
- **零命中不是终点**：任一项零命中时，依次降级 ① 换扩展短语重试 ② 按该项 `basis` 指向的章节直接取 chunk ③ 仍无 → `evidence_unresolved` 且**记录实际用过的查询串**（用户可见，便于判断是漏检还是真没有）。
- **chunk 形态保底**：投标 OCR 若识别不出章节 → 0 chunk 或单个巨 chunk。规定二次切分：无章节结构时按**页级 + 定长（带页锚）**切分，单 chunk 上限硬约束（超限即再切）。
- 页锚由 chunk 直接带出（`page_anchor`），证据链 `【第N页】` 不靠模型推算——比现状（模型从大段底稿自己数页码）更可靠。
- 索引写入时机：投标层预热 OCR 完成后立即建索引；**索引缺失时现场同步补建**（FTS5 对 37 万字是秒级），补建失败才降级，且降级单强制 `manual_review` 不出分（critic F7：旧路径对 400 页投标产出的是**带 warning 的错误评分**，比失败更危险）。

### KD3 · 预算口径单点化 + 闭式账目（按 critic F2 改写）

**现存口径清单（全部必须收编，初稿只提了两处）**：

| 位置 | 常量 | 现值 | 处置 |
|---|---|---|---|
| `context_budget.py:47` | `_BYTES_PER_TOKEN` | 3 | 统一单位后保留（仅字节↔token 换算） |
| `context_budget.py:51` | `_SCAFFOLD_RESERVE_TOKENS` | 30,000 | **收编**（初稿写 18K+7K=25K，与之矛盾） |
| `context_budget.py:54` | `_AGENT_LOOP_MARGIN_DIVISOR` | 4 | 收编 |
| `context_budget.py:57` | `FALLBACK_MAX_BYTES` | 256,000 | 收编 |
| `context_slim.py:38` | `_DEFAULT_CHARS_PER_TOKEN` | 1.0 | **单位冲突**：与 3B/token 并存 → 统一 |
| `context_slim.py:39` | `_DEFAULT_CONTEXT_MARGIN_TOKENS` | 4,096 | 收编 |
| `context_slim.py:29` | `_CHUNKS_PER_QUERY` | 3 | 纳入证据预算账 |

**全文统一以 token 计**（字节只在换算处出现，注明中文 UTF-8 3B/字≈1token）——64,000B 那次事故的单位错正源于混用。

**闭式账目**（必须恒成立，AC5 按此断言）：

```
scaffold + criteria + Σ(per_item_evidence) + margin ≤ TENDER_EFFECTIVE_CONTEXT_TOKENS
```

各项取值**在 impl 前用事故项目真实 criteria 核基线**（实测 14 评分项 + 资格若干 ≈20+ 查询），不得凭估算落笔——初稿"每项 ≤8KB × 20 项 ≈54K + 脚手架 25K = 79K > 60K"当场就不闭合，是"落笔即不可达"的重演。

**跨项去重是账目的一部分**：多个评分项常命中同一 chunk（如同一张报价表），组装期按 `chunk_id` 去重后再计账；单 chunk 超长时先裁剪再计入。

**标定与失效保护**：`TENDER_EFFECTIVE_CONTEXT_TOKENS` 由二分实测 CLI 拒绝阈值得出，测法与测得值入档可复跑。**标定过期的防护**：CLI 拒绝时的错误必须点名该常量与标定档路径，提示"实测上限已变，请按附录复测"——防止它变成第五个写死的错数字。`MODEL_CONTEXT_WINDOW` 退出预算用途（它描述模型能力、不描述 CLI 行为）；若无其余消费者则一并退役。

### KD3b · 检索时机与兜底边界（critic F3，初稿未定义）

**检索在会话前由服务端机械完成**（非 agentic 工具）。理由：会话中检索会把轮次与注入量重新变成不可控变量，而 08-14 事故正是"反复 Read → `error_max_turns`"。服务端组装 = 注入量在发起前即已确定，可被 AC5 机械断言。

**"模型按需 Read 整份投标"的无界旁路取消**。初稿把它列为风险缓解，实为绕过全部预算机制的后门。替代：
- 命令侧保留**有界分页 Read**（单次上限 + 会话累计上限，**计入 AC5 账内**）；
- 超出上限时提示"该项证据需人工调阅"，而非继续读。

注：`server/common/contract.py:38` 已把 `Prompt is too long` 列入不可重试（初稿背景表未反映）——即爆窗现在是**一次性硬失败**，更没有"多读几次试试"的余地。

### KD4 · 掉落与失败一律可见

| 情形 | 现状 | 目标 |
|---|---|---|
| 预热 ready 却走 inline_ocr | 仅日志 INFO | 结论 `warnings` 增加一条 + 前端可见；并**先修使其不该发生** |
| criteria 抽取失败 | `ValueError("no usable items")`，无细节 | `criteria_looks_usable` 返回**具体原因**（无 items/非数组/缺名字/无数值满分），透传到状态与界面 |
| 某评分项检索不到证据 | 现状无此概念 | 该项 `evidence_unresolved` + 说明检索了什么、命中 0 条 |
| 证据层未建索引 | 无 | 显式 warning，回落"招标原文+投标截断"旧路径并标注 |

原则：**降级可以发生，但必须留下用户看得见的痕迹**——三次事故的共同放大器都是静默。

### KD5 · 主链路掉落根因修复

查实 `bid_id=null` 的成因（前后端字段已核对一致，怀疑提交时机/状态未就绪），修复后加回归测试：**两层预热 ready 时，评标必须命中 `doc_layer_reuse`**。这是可机械断言的不变量。

## 影响范围

```text
server/tender/context_slim.py     KD1/KD2 证据层检索；投标入索引
server/tender/doc_layer.py        KD1 组装改为 criteria + 检索证据
server/tender/doc_context.py      KD4/KD5 掉落可见 + bid_id 修复
server/tender/context_budget.py   KD3 口径统一（字节闸降为最终兜底）
server/tender/doc_pipeline.py     KD4 criteria 失败诊断
server/ocr/rag.py                 KD2 检索参数（可能微调，尽量只读复用）
agent-front/.../analyzing-view    KD4 降级/证据不足可见（小改）
tests/                            新增：证据检索、掉落不变量、诊断透传
```

## 风险与缓解

1. **检索召回不足 → 漏掉关键证据**（最大风险）。缓解：每项检索 top-N 取足（N 可配，默认偏大）；检索命中 0 条时**不判 0**、标 `evidence_unresolved` 并显示查询词；保留"整份投标可被模型按需 Read"的兜底能力。
2. **索引构建增加预热耗时**。缓解：与 OCR 同阶段完成、只做一次；实测记录耗时增量，超过阈值则改异步。
3. **一次事故三次误修的教训**：本次**禁止再靠调数字收敛**。任何预算取值必须附实测方法与测得值；AC 里写死"标定可复跑"。
4. **改动面横跨 tender 多模块**（红区）。缓解：切片交付，每片可独立验收；先做可见性（KD4）与掉落修复（KD5），再做检索改造（KD1/KD2）——前两者能立即止血且风险低。

## 切片与顺序

- **S1（可见性，低风险）**：KD4 可见性 + KD5 掉落根因修复。
- **S2（口径统一）**：KD3 单点预算 + 闭式账目 + 实测标定。为 S3 提供正确目标值。
- **S3（主体）**：KD1/KD2 证据层入索引 + 查询构造修正 + 按项检索组装。
- **S4（验证）**：真实标书端到端，**必须在部署矩阵最小窗口模型（DeepSeek/qwen）上跑**（08-14 教训：在 Claude 上验收完就 ship，代价是生产当验收环境）。记录耗时与注入量，对齐 10 分钟目标。

**期望管理（critic F6，必须让用户知道）**：S1/S2 **不能让事故单恢复出分**。修好掉落后主链路命中 → 409K token 注入 → CLI 一次性硬失败（`contract.py:38` 已列不可重试）；S1+S2 加上裁剪 → 复演 08-15 的"largely impossible"。**S1/S2 的价值只是把静默变可见**，大投标单要到 S3 才可评。不写清这点，S1 交付会给出虚假的安全感。

## 验收标准

- [x] **AC0（S0 门槛）— 已完成**：部署机真实底稿实测在档（见 S0-B 节）。索引 146 chunk/0.02s、structure 60 章节；召回率 裸用 38% → 子串旁路 **88%/4ms**。**双通道方案达标，可进 S3**；若后续标书实测跌破 70%，按「已调研方案」表升级 map-reduce。
- [ ] **AC0b**：实现后用同一份真实底稿复跑，命中率不低于 88%；新增普通表副本与 `rag_chunks` 同源（chunk_id 一一对应，无遗漏）。
- [ ] **AC1**：两层预热 `ready` **且传入 bid_id** 时评标必须命中 `doc_layer_reuse`（回归断言）；合法无 bid_id 的散单路径不在此约束内。
- [ ] **AC2**：任何降级（掉落 inline、criteria 失败、证据缺失、索引缺失）在结论 `warnings` 与前端均可见，无静默路径（守卫测试：遍历降级分支，断言每条都产出可见信号）。
- [ ] **AC3**：`criteria_looks_usable` 失败时返回可读原因，透传至任务状态与界面。
- [ ] **AC4**：投标文件在预热完成后进入 FTS5 索引；`rag.search` 能按评分项名检出带 `page_anchor` 的 chunk。
- [ ] **AC5**：注入量满足 KD3 闭式账目 `scaffold + criteria + Σ(per_item) + margin ≤ TENDER_EFFECTIVE_CONTEXT_TOKENS`，各项取值以事故项目真实 criteria 核过基线（不接受估算值）。**与投标页数无关**：同一招标 + 40 页 / 400 页两份投标，注入量差异 ≤20%。测量口径：组装完成后对最终 prompt 计 token（命令写进附录 B），计时起点=评标任务 `started_at`。
- [ ] **AC6**：预算口径单点——KD3 清单里 7 个常量全部收编到单一来源，全文以 token 计；`MODEL_CONTEXT_WINDOW` 退出预算用途；标定方法与测得值入档可复跑；**CLI 拒绝时的错误消息点名该常量与标定档路径**。
- [ ] **AC7**：真实标书端到端 ≤10 分钟出结论（计时起点=任务 `started_at`），**在部署矩阵最小窗口模型上验**；`scoring` 逐项有分/有 status，证据链页锚来自检索结果；零命中项记录实际查询串。
- [ ] **AC8**：NO_NEW_FAILURES；ruff 净；前端三件套绿。

## 待查实项（S0 阶段完成，impl 前必须清零）

1. `bid_id=null` 的确切成因（前端未传 / 后端解析 / 提交时机），需复现路径。**前后端字段已核对一致**，剩余怀疑面=提交时机与状态就绪。
2. bundled CLI 的真实上下文上限（二分实测）→ 得出 `TENDER_EFFECTIVE_CONTEXT_TOKENS` 标定值。
3. 投标 OCR 文本的 `structure`（`index_document` 要求 structure+body 同源配对）是否已有；无章节结构时的二次切分方案实测（KD2 已给方向，需验证 chunk 大小分布）。

## 附录 A · 评审记录

### Round 1 · Critic Findings（Fable 5, 2026-08-15）

**VERDICT: NEEDS_REVISION** — 方向正确（检索式证据层是唯一与体量脱钩的路子，且复用现成 FTS5），但主承重梁"中文 BM25 召回"零实测、预算算术不闭合，不补则 S3 落地日即第四次事故。

- **F1 [P0]** 检索召回未验证，且 `rag.search` 现行语义与 KD2 直接相抵：`rag_store.py:29` 是 trigram tokenizer、`rag.py:83` 把整串包成单一 phrase → 2 字项名恒零命中、跨空格 phrase 无匹配；投标无章节结构时 0 chunk 或巨 chunk。
- **F2 [P0]** AC5 的 60K 无推导且账不闭合（脚手架 25K + 20 项 ×8KB ≈ 79K > 60K）；`_SCAFFOLD_RESERVE_TOKENS=30_000` 与设计自述矛盾；KB/token 单位混用，重演 64,000B 单位错。
- **F3 [P0]** "整份投标可被模型按需 Read"是绕过全部预算的无界旁路（08-14 事故正是反复 Read → max_turns）；且未定义检索发生在会话前还是会话中，两者预算/轮次账完全不同。
- **F4 [P1]** 缺「已调研的现成方案」节，尤其未对照 map-reduce 多次小会话。
- **F5 [P1]** 撤走招标原文后，`basis` 指向招标章节的评分项断粮。
- **F6 [P1]** S1/S2 对大投标单不是恢复服务，缺期望管理；S4 须在最小窗口模型上验；标定过期需防护。
- **F7 [P1]** "索引缺失→回落旧路径"是把已实证会产错误结论的路径当降级归宿（错评分比失败更危险）。
- **P2**：AC 测量方法/计时起点未指定、`N 可配`是无消费者的新配置项、AC1 需为散单留限定语、`MODEL_CONTEXT_WINDOW` 若无消费者应退役。

### Round 2 修订（本次，逐条对应）

| Finding | 处置 |
|---|---|
| F1 | **新增 S0 Spike 实测节**（本机实跑，7 组查询数据在档）+ KD2 按实测改写（≥3 字短语扩展、多词拆 OR、零命中三级降级并记录查询串、无章节时页级+定长二次切分）+ 新增 **AC0 门槛**：召回率不达标则升级 map-reduce，不硬上 |
| F2 | KD3 改写：列出**全部 7 个现存常量**并逐一收编、全文统一 token 计、给出**闭式账目公式**、要求以事故项目真实 criteria 核基线、跨项去重计入账目 |
| F3 | 新增 **KD3b**：检索**在会话前由服务端机械完成**（非 agentic）；**取消无界 Read 旁路**，改有界分页 Read 且计入 AC5；补记 `contract.py:38` 爆窗已是一次性硬失败 |
| F4 | 新增「已调研的现成方案」节，5 个候选逐个判定；map-reduce 记为**S3 未达标时的升级路径**并写明取舍理由 |
| F5 | KD1 更正：招标索引**同样参与检索**，`basis` 指向招标章节的项按需带出招标 chunk |
| F6 | 切片节补**期望管理**：S1/S2 只把静默变可见，大单到 S3 才可评；S4 必须在最小窗口模型上验；AC6 要求 CLI 拒绝错误点名标定常量与档案路径 |
| F7 | KD2 改：索引缺失**现场同步补建**（37 万字秒级），补建失败才降级，且降级单强制 `manual_review` 不出分 |
| P2 | AC5/AC7 补测量口径与计时起点；删除"N 可配默认偏大"改为受账目约束；AC1 补散单限定语；`MODEL_CONTEXT_WINDOW` 明确退出预算用途 |

## 附录 B · 可复跑命令

**S0 检索行为实测**（本机，无需部署机）：

```bash
uv run python -c "
import sqlite3, sys; sys.path.insert(0,'.')
from server.stores import rag_store
from server.ocr.rag import _escape_match_query
conn=sqlite3.connect(':memory:'); rag_store.ensure_schema(conn)
rag_store.insert_rows(conn,[dict(chunk_id='c1',file='投标.pdf',chapter_path='商务标',
  chapter_title='报价一览表',tag='bid',page_start=1,page_end=2,page_artifact='original',
  chunk_text='投标报价：人民币壹佰贰拾万元整。施工组织设计详见技术标第三章。项目负责人张三。')])
for q in ['报价','投标报价','施工组织设计','施工组织设计 技术标']:
    print(q, len(rag_store.query_rows(conn,_escape_match_query(q),tag=None,limit=5)))
"
```

**预算常量清单核对**：

```bash
grep -n "_BYTES_PER_TOKEN\|_SCAFFOLD_RESERVE_TOKENS\|_AGENT_LOOP_MARGIN_DIVISOR\|FALLBACK_MAX_BYTES" server/tender/context_budget.py
grep -n "_CHUNKS_PER_QUERY\|_DEFAULT_CHARS_PER_TOKEN\|_DEFAULT_CONTEXT_MARGIN_TOKENS" server/tender/context_slim.py
```

**部署机底稿体量核对**（SSH 可达时）：

```bash
docker exec agent-backend python3 -c "
import sqlite3; c=sqlite3.connect('/app/data/db/platform.sqlite3')
print(list(c.execute('SELECT project_id,ocr_status,length(ocr_text) FROM tender_bid_docs ORDER BY created_at DESC LIMIT 3')))"
```
