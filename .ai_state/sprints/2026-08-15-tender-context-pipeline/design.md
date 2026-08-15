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

## 关键决策

### KD1 · 规则层常驻，证据层按项检索

```
规则层（常驻全量）  招标 criteria 结构化后 ≈20KB 量级
                    ├ eligibility_rules[]   资格规则
                    └ items[]               评分项（名称/满分/score_mode/tag）
                    ※ criteria 抽取成功时**不再注入招标原文**，只注入结构化 criteria

证据层（按需检索）  投标全文入 FTS5 索引（当前完全缺失）
                    S3 评第 k 项时：以该项 item 名称 + 关键词检索 top-N chunk
                    每项证据预算独立（如 ≤8KB），N 项合计有硬上界
```

单会话注入 = 脚手架(≈18K token) + criteria(≈7K) + 当次检索到的证据片段。**与投标是 40 页还是 400 页无关。**

### KD2 · 检索粒度与页锚保真

- 复用 `rag.search`，`tag` 过滤 + BM25。chunk 携带 `page_anchor`，证据链的 `【第N页】` 由检索结果直接带出，不靠模型推算——**这是比现状更强的保证**（现状模型从大段底稿里自己数页码）。
- 每项检索 query 由 criteria item 名称 + 该项 `basis`/关键词构造；检索不到时该项标 `evidence_unresolved`，**不判 0**（沿用既有纪律）。
- 索引写入时机：投标层预热 OCR 完成后立即建索引（与 `ocr_status=ready` 同事务或紧随其后），评标时直接查。

### KD3 · 预算口径单点化，按实测上限标定

- 现状两套口径打架：`context_slim._preextract_char_budget` 用 `MODEL_CONTEXT_WINDOW`(=1,048,576)，`context_budget.derive_default_max_bytes` 用另一套推导；而**真实约束是 bundled CLI ≈200K token**，两个 env 都不反映它。
- 统一到单一来源：新增 `TENDER_EFFECTIVE_CONTEXT_TOKENS`（实测标定，默认取保守值），两处共用。**`MODEL_CONTEXT_WINDOW` 不再作为预算依据**（它描述模型能力，不描述 CLI 行为），仅保留给需要它的其他用途。
- 标定方法写进档案：二分实测 CLI 拒绝阈值，记录测得值与测法，后续换模型/换 CLI 版本按同法复测。

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

- **S1（止血，低风险）**：KD4 可见性 + KD5 掉落根因修复。做完主链路命中率恢复，且再掉落时能一眼看见。
- **S2（口径统一）**：KD3 单点预算 + 实测标定。为 S3 提供正确的目标值。
- **S3（主体）**：KD1/KD2 证据层入索引 + 按项检索组装。
- **S4（验证）**：真实标书端到端跑通，记录耗时与注入量，对齐"10 分钟内"目标。

## 验收标准

- [ ] **AC1**：两层预热 `ready` 时评标必须命中 `doc_layer_reuse`（回归测试断言；实测事故场景不再回落）。
- [ ] **AC2**：任何降级（掉落 inline、criteria 失败、证据缺失、索引缺失）在结论 `warnings` 与前端均可见，无静默路径（守卫测试：遍历降级分支，断言每条都产出可见信号）。
- [ ] **AC3**：`criteria_looks_usable` 失败时返回可读原因，透传至任务状态与界面。
- [ ] **AC4**：投标文件在预热完成后进入 FTS5 索引；`rag.search` 能按评分项名检出带 `page_anchor` 的 chunk。
- [ ] **AC5**：单次评标注入量 ≤60K token（含脚手架），且**与投标页数无关**——用 40 页与 400 页两份投标实测，注入量差异 ≤20%。
- [ ] **AC6**：预算口径单点，`MODEL_CONTEXT_WINDOW` 不再被用作预算依据；实测标定方法与测得值入档，可复跑。
- [ ] **AC7**：真实标书端到端 ≤10 分钟出结论，`scoring` 逐项有分/有 status，证据链页锚来自检索结果。
- [ ] **AC8**：NO_NEW_FAILURES；ruff 净；前端三件套绿。

## 待查实项（设计期未定，实施前必须查清）

1. `bid_id=null` 的确切成因（前端未传 / 后端解析 / 提交时机），需复现路径。
2. bundled CLI 的真实上下文上限（二分实测，得出可标定的数字）。
3. 投标 OCR 文本的 `structure`（`index_document` 需要 structure+body 配对）是否已有——若无需补，成本要评估。
