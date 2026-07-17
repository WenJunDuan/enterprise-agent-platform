# D2 · server/tender/ feature 包重构 — design【DRAFT / 预研】

> roadmap: 2026-07-doc-intelligence / Wave0 / D2 (tender-feature-package)
> path: **Refactor（红区，server-refactor）** · effort L · 状态: **DRAFT 预研**
>
> ⚠️ **本文档是 D1 收尾间隙的预研草稿，非可直接 impl 的定稿。impl 前置三条**：
> 1. **D1 merge 回 main**——D2 是"纯移动为主"重构，迁移基线必须是 D1 merge 后的 main
>    （D1 已前置迁走评标核心到 server/tender/runner.py、tender_worker 变调度壳、
>    tender_doc_pipeline 改 import、tender_output 加 is_real_number）。本清单基于 D1
>    worktree 当前状态推演，**D1 merge 后须用 rg/wc 精确复核迁移面**。
> 2. **用户拍板 F6 分层决策**（方案 A / B，见下）——决定迁移清单大小与是否有行为接缝。
> 3. **critic 一轮**（红区 System/Refactor 门禁）。
> 4. 红区铁律：generator + `isolation: worktree` 强制。

## 背景（WHY）

2026-07-02 全仓架构评估 P0-1：**tender 域没有 feature 包**，约 3250 行评标逻辑散在
`routes/`（tender_worker/tender_compare_worker/tender_doc_pipeline/tender.py）与
`common/`（tender_output/evidence_resolution）。后果：

1. **分层混乱**：业务逻辑挤在 routes 层（本应只做 HTTP 壳）与 common 层（本应只放跨域
   共享物）。audit/ocr 都有独立 feature 包，唯 tender 没有——D1 已开头（runner.py 落地），
   D2 收全。
2. **22 文件超 300 行红线**，tender.py 单文件 912 行。
3. **D8 底稿瘦身的落点依赖 D2**：D8 要改的 tender_worker 检索逻辑必须先归位 server/tender/，
   否则二次搬迁（items.yaml D8 depends_on D2）。

## 方案

### 迁移清单（基于 D1 worktree 现状推演，D1 merge 后复核）

| 源 | 目标 | 性质 |
|---|---|---|
| `routes/tender_worker.py`（D1 后仅剩调度壳） | `server/tender/worker.py` | 纯移动 |
| `routes/tender_compare_worker.py` | `server/tender/compare_worker.py` | 纯移动 |
| `routes/tender_doc_pipeline.py`（D1 后 TENDER_OCR_PURPOSE 已挪走） | `server/tender/doc_pipeline.py` | 纯移动+接缝 |
| `common/tender_output.py` | `server/tender/output.py` | **取决于 F6** |
| `common/evidence_resolution.py` | `server/tender/evidence.py`（或留 common，见深评#10） | **取决于 F6** |
| `routes/tender.py`(912) | 拆薄为 HTTP 壳 + 按 banner 分节 | 拆分 |

### ✅ F6 决策（2026-07-16 用户拍板 = 方案 A · schema 分家）：tender_output / evidence_resolution 归属

**根因**（已核验代码）：`common/contract.py:252` 末尾 import `output_contracts` →
`output_contracts.py:30-37` import `tender_output` 6 个校验函数 + `:460` import
`evidence_resolution.resolve_audit_evidence` → `:462-470` **全挂在共享
`DEFAULT_OUTPUT_SCHEMA_NAME`(audit-result) 上**。双重耦合：
- **分层**：common(output_contracts) → tender_output/evidence。若直接把这两个模块迁进
  `server/tender/`(feature)，就是 common→feature 逆向依赖，撞 layering 守卫（撞 T5 (d)）。
- **行为**：tender 专属校验（scoring/plan/disqualification 一致性）无条件跑在
  expense/audit 结果上；纯 audit 调用也被 contract.py:252 副作用拉入 tender 模块。

**方案 A（schema 分家，深评 #7 推荐）**
- 注册 tender 专属 schema 处理器：tender 的 6 校验 hook + resolve_audit_evidence 挂
  **tender schema 名**；expense/audit 用纯通用处理器（不再跑 tender 校验）。
- tender_output/evidence 从 tender 模块自己调 `register_schema_processor` →
  可**合法迁入 server/tender/**（feature 自注册，output_contracts 不再 import 它们）。
- 附带修 contract.py:252 import-time 副作用（纯 audit 不再拉入 tender）。
- **代价/风险**：tender_worker/runner 现传 `schema_name=DEFAULT_OUTPUT_SCHEMA_NAME`，
  分家后要改传 tender schema 名——**这是行为接缝，非纯移动**，需 D1 eval 回归闸 +
  针对性测试护航（证明 expense 结果不再跑 tender 校验、tender 结果校验不变）。
- 彻底解分层+行为纠缠，D2 目标"tender 逻辑全归位"达成。

**方案 B（两模块留 common）**
- tender_output/evidence_resolution **不迁**，留 common 层；D2 只迁 worker/compare_worker/
  doc_pipeline + 拆 tender.py。
- **零行为变更、最省事**，但 tender 逻辑仍有一部分留在 common（output/evidence 共约
  ？行），D2"归位"目标打折扣，耦合债留到未来（D7 会再碰 evidence_resolution，见深评#10）。

**决议：方案 A（2026-07-16 用户拍板，见 compound/2026-07-16-decision-schema-split-tender.md）。**

**实现路径（供 critic 核 + design 定稿细化）**：
1. 定 tender 专属 schema 名（如 `TENDER_OUTPUT_SCHEMA_NAME`）。**critic 待定**：新 json schema 文件
   vs 复用 audit-result.json 校验规则 + 仅处理器链分家——tender 结论仍须符合
   `.claude/contracts/common/audit-result.schema.json`，**倾向复用同一 json + 独立处理器注册**
   （schema 内容一致、只是 normalize/validate/enrich/resolve 处理器链挂 tender 名）。
2. `tender_output`（6 校验）+ `evidence_resolution`（resolve_audit_evidence）迁入 server/tender/，
   从 tender 模块调 `register_schema_processor(TENDER_SCHEMA, …)` 自注册（feature 自注册合法）。
3. `output_contracts.py` 去掉 `:30-37` tender import 与 `:460` evidence import，只留通用
   audit-result 注册（不再挂 tender 校验）；`contract.py:252` 副作用不再拉入 tender（纯 audit 干净）。
4. `tender_worker`/`runner` 改传 `schema_name=TENDER_SCHEMA`（D1 `runner.py` 现传
   `DEFAULT_OUTPUT_SCHEMA_NAME`）——**这是本 sprint 的行为接缝，D1 eval 回归闸 + 接缝测试护航**。
5. 接缝测试（必补）：expense/audit 结果不再跑 tender 校验（新断言）、tender 结果校验行为不变、
   纯 audit import 不拉入 tender 模块（守卫 contract.py 副作用已解）。

### 范围附加项（深评 #8 / #12，随 F6 一并定）

- **#8 worker background job harness**：audit/tender/compare 三 worker 的
  准入闸+强引用集+信号量+超时+三态 upsert 60-70% 同构，第三消费者已在。深评建议
  "D2 tender worker 迁包时顺手抽"。**建议作为 D2 内独立一步**（先纯迁移绿、再抽 harness
  绿，各自 commit），或若 D2 已够大则降级独立 sprint——待定。
- **#12 tender.py 分节**：banner 已就位（:133/223/441/627/854），
  tasks(~250)/projects(~185)/docs(~225)/compare(~60) 拆分低风险，深评评"方案可行"。

### 明确不进 D2（防范围膨胀）

- 深评 #9 stores admin/tenant 双份查询参数化（~150-200 行）→ 独立绿区项，不搭 D2。
- 深评 #5 cache fingerprint 修复 / #6 死代码删除 → D4 首任务或独立绿区。
- 深评 #10 evidence_resolution 匹配内核升格 → D7 起点，不在 D2。

## 影响范围（待 D1 merge 后精确化）

- 移动：server/routes/tender_*.py（3-4 文件）→ server/tender/
- F6=A 时额外：common/tender_output+evidence → server/tender/ + output_contracts/contract
  的 schema 注册重构（行为接缝）
- 测试护航：文件名含 tender 14 个 / 内容引用 tender 25 个（D1 Round 2 F7 实测）+
  test_layering 守卫扩展（server/tender/ 子模块全部纳入）
- 不动：audit 域、ocr 域、expense 域（F6=A 时 expense 校验行为变化须专门验证=不再跑
  tender 校验，属预期改善不是回归）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 纯移动引回归 | D1 eval 回归闸 + 14/25 测试全量护航；红区 worktree 隔离；每步单独 commit |
| F6=A schema 名变更改行为 | 针对性接缝测试（expense 不跑 tender 校验 / tender 校验不变）；D1 eval 复跑 |
| 迁移基线漂移（D1 未 merge） | **本 draft 不定稿**；D1 merge 后 rg/wc 复核清单再进 critic |
| D2 范围过大（迁移+harness+拆分） | 分步 commit；harness 抽取可降级独立 sprint |

## 验收标准（D2 范围定稿 = 纯移动；以文末「Round 2 后 · D2 范围定稿」为准）

- [x] （前置）D1 已 merge 回 main（merge 77d9ffe，main 818 绿）
- [x] （前置）范围决策：F6 schema 分家 + F5 evidence 拆分 → 拆独立 sprint（本 D2 不做）；#8 harness 亦不进 D2
- [x] （前置）迁移面已核实干净（2026-07-16 rg 实证）：3 待迁文件仅下行 import（common/platform/stores/ocr/tender），无 features→routes/ops 上行边；消费者仅 routes/tender.py（壳）+ tender/runner+__init__，余皆注释
- [ ] T1 `routes/tender_worker.py` → `server/tender/worker.py`；routes/tender.py 改 import；pytest 绿 + 单独 commit
- [ ] T2 `routes/tender_compare_worker.py` → `server/tender/compare_worker.py`；改 import；pytest 绿 + 单独 commit
- [ ] T3 `routes/tender_doc_pipeline.py` → `server/tender/doc_pipeline.py`（改 import + 更新 prewarm_scheduler.py:5 "routes 层" 陈述注释）；pytest 绿 + 单独 commit
- [ ] T4 `routes/tender.py`(912) 按 banner(:133/223/441/627/854) 拆薄为 HTTP 壳 + tasks/projects/docs/compare 分节路由（业务逻辑已在 T1-T3 归位）；pytest 绿 + 单独 commit
- [ ] T5 test_layering 守卫扩展至 server/tender/ 新子模块；全量 pytest 绿（818 基线）+ ruff 净
- [ ] F8 红区纪律：每个 Ti 各自一 commit、pytest 全绿再进下一 Ti（回滚锚点）
- [ ] （runbook，不阻塞 merge）D1 eval 回归闸复跑无劣化（部署机需网关）

## 备选（放弃）

- 一次性大爆炸迁移（不分步）：红区纯移动 3250 行不分步 = 回归定位噩梦，违反"每步 commit
  可回滚"。放弃。

---
_参考：compound/2026-07-03-explore-arch-deep-review-deltas.md #7/#8/#9/#12；
items.yaml D2 note；D1 design.md Round 2 F6。_

---

## Round 1 · Critic Findings（2026-07-16）

### VERDICT: NEEDS_REVISION
（2 条 P0 会让 F6 5 步实现路径在执行时直接卡住/静默留坑，须补再进下一轮。）

**F1 [P0] schema 分家"复用同一 json"与代码机制冲突，步骤1 不可直接执行**
- `contract.py:159-175` `apply_schema_semantics` 把 `schema_name` **同时**当处理器注册表 key +
  物理文件路径（`:32-40` `resolve_output_schema_path`）。给 tender 挂新 schema 名（新 key）又想
  复用同一 json 不建新文件 → 互斥：新名会去找 `.claude/contracts/tender/audit-result.schema.json`
  （不存在，该目录仅 compare-result/criteria/extract-result/review-delta/tender-info）→ `JSONContractError`。
- 补：二选一写进步骤1——(a) `register_schema_processor` 加可选 `schema_path` 字段
  （tender 注册时 `schema_path=DEFAULT_OUTPUT_SCHEMA_NAME`）；(b) 复制 byte-identical 的
  `.claude/contracts/tender/audit-result.schema.json` + 漂移测试（仿 `output_contracts.py:349-352`
  `_AUDIT_SCHEMA_TOP_FIELDS` 守卫）。

**F2 [P0] 迁移清单漏第二调用点 `server/cli.py` `tender-evaluate-json`**
- `cli.py:195-215` 直接调 `run_command_json(schema_name=DEFAULT_OUTPUT_SCHEMA_NAME)`，不经 runner.py。
  步骤4 只改 `runner.py:223` → cli.py 路径静默退化成跑通用 audit 校验（bug 从第二入口复现）。
  `test_cli_tender_evaluate.py:18,89` 硬编码断言 schema 名会掩盖回归。
- 补：迁移清单+接缝测试补 cli.py 第4调用点，同步改 test 断言；3 条接缝测试 → 4 条。

**F3 [P1] tender schema processor 自注册触发点未定义，静默失效风险**
- `register_schema_processor(TENDER_SCHEMA)` 需 import 时执行，迁移后谁 import 触发未写。
  无人 import → `_SCHEMA_PROCESSORS.get` 得 None → `apply_schema_semantics` 静默退化为仅裸 json
  校验（`contract.py:166-167` `processor is None: return`），不报错、行为悄悄变弱。
- 补：明确 `server/tender/__init__.py` 或 `runner.py` 顶部 import 输出模块；补测试直接断言
  `_SCHEMA_PROCESSORS` 有 TENDER_SCHEMA（而非只测行为副作用）。

**F4 [P1] #8 worker harness 与"不动 audit 域"矛盾**
- `audit_worker.py` 是三胞胎之一，抽 harness 必 touch audit_worker，撞 draft「影响范围」的
  "不动 audit 域"；不 touch 则只 2/3 消费者接入，抽象合理性打折。
- 补：#8 明确移出 D2 → 独立 sprint（跨 audit+tender+compare 一起做才站得住），验收 T3 删或标"不进 D2"。

**F5 [P1] evidence_resolution 整搬使 ocr 测试反向依赖 tender，深评#10 张力未拍板**
- `test_ocr_pipeline.py:686` / `test_boq.py:167` import `server.common.evidence_resolution` 的通用
  语料原语（`CorpusIndex/existence_ratio/normalize_text/parse_corpus`，深评#10 指 `:103-453` 通用、
  `:453-642` 才 audit 专属）。整搬 → 两 ocr 测试被迫 import `server.tender.evidence`（语义耦合，
  D7 升格共享检索内核时二次搬迁）。draft"或留 common"未决。
- 补：二选一——(a) 按#10 拆：`parse_corpus/CorpusIndex/existence_ratio/normalize_text` 留 common
  （或独立 `server/common/corpus.py`），仅 `resolve_audit_evidence` 整合层随 tender 迁+挂 tender
  schema 名；(b) 整搬 + 明确记录"ocr 测试耦合 tender 包"技术债留 D7。不留"或留 common"悬而未决。

**F6-F8 [P2，不阻塞，impl 顺手带]**
- F6：`eval.py:34` 已 `import tender_output.is_real_number`（D1 产物），迁移清单补这处 import 路径改。
- F7：风险表拆两行——本地 pre-merge = 14/25 pytest + layering + 接缝测试；部署机 post-merge =
  D1 eval 闸真跑（需网关，非阻塞）。别让人误以为 eval 闸能本地 CI 自动跑。
- F8：验收加"每个 Ti 各自一 commit，pytest 全绿再进下一 Ti"（红区回滚锚点）。

### 进 impl 前必补清单（5 项 F1-F5，落实后进下轮 critic 或直接 APPROVE）
1. **F1** schema_path 别名 vs 复制物理 schema 文件二选一 + 漂移测试设计
2. **F2** 迁移清单+接缝测试补 `server/cli.py` 第二调用点 + `test_cli_tender_evaluate.py` 断言
3. **F3** 自注册 import 触发点 + "TENDER_SCHEMA 已注册"直接断言测试
4. **F4** #8 worker harness 移出 D2（独立 sprint），T3 删除/标"不进 D2"
5. **F5** evidence_resolution 拆分（按#10）vs 整搬记债 二选一拍板

---

## Round 1 修订应答（2026-07-16，F1/F5 用户已拍板）

> 进 impl 前 design 定稿**以本应答为准**（覆盖上文 draft 中"待定/或留 common/随 F6 定"等未决表述）。
> 已核验代码（contract.py:32-175 / evidence_resolution.py 结构 / cli.py:195-215 / test_cli_tender_evaluate.py）。
> **范围校准**：D2 = tender 纯移动 + F6 schema 分家（**含 contract 机制向后兼容小改**）+ evidence 拆分；
> 不再是纯"零行为移动"。

**F1 → schema_path 别名（用户拍板）**
- `SchemaProcessor`（contract.py:61-79 frozen dataclass）加字段 `schema_path: str | None = None`；
  `register_schema_processor`（:85-100）加同名可选参数透传。
- `apply_schema_semantics`（:161 取 processor 后）把物理 schema 解析改用 `processor.schema_path or
  schema_name`——`_validate_against_json_schema`（:103）增一个"物理 schema 名"参数，由 apply 传入
  `processor.schema_path or schema_name`（未注册 processor 时回退 schema_name，audit/expense 零变化）。
- tender 注册：`register_schema_processor(TENDER_OUTPUT_SCHEMA_NAME, normalize/validate/enrich/resolve=…,
  schema_path=DEFAULT_OUTPUT_SCHEMA_NAME)`——key=tender 专属名（挂 tender 处理器链），物理 json 复用
  audit-result.json（不建新文件、无漂移）。
- 接缝测试：tender key 走 tender 处理器链 + 物理形校验仍用 audit-result.json（形校验行为不变）。

**F2 → 补 cli.py 第二调用点**
- `cli.py:212` tender-evaluate-json 的 `schema_name=DEFAULT_OUTPUT_SCHEMA_NAME` → `TENDER_OUTPUT_SCHEMA_NAME`。
- `test_cli_tender_evaluate.py:18` `EVAL_SCHEMA` + `:32/:89/:93` 断言同步改 tender schema 名；测试
  `test_evaluate_bid_json_uses_audit_result_schema` 语义/名改为走 tender schema。
- 接缝测试 3 条 → **4 条**（+cli.py 路径确实走 tender 校验，防 bug 从第二入口复现）。

**F3 → 自注册触发点**
- tender_output 迁入 `server/tender/output.py` 后，模块级调 `register_schema_processor(TENDER_OUTPUT_SCHEMA_NAME, …)`；
  由 `server/tender/__init__.py` import output 模块保证"加载 server.tender 即注册"（runner/worker/eval/cli
  任一入口 import server.tender 都触发）。
- 补测试：直接断言 `_SCHEMA_PROCESSORS` 含 `TENDER_OUTPUT_SCHEMA_NAME`（不只测行为副作用）。

**F4 → #8 worker harness 移出 D2**
- #8（audit/tender/compare worker 三胞胎抽 background job harness）**不进 D2**，独立 sprint
  （跨三消费者一起做才站得住，避免撞"不动 audit 域"）。D2 只做 tender worker 纯移动 + F6。
  验收标准无 harness 项；范围附加项段的 #8 标"移出 D2"。

**F5 → evidence_resolution 拆分（用户拍板：通用留 common）**
- 通用检索内核留 common（**建议独立 `server/common/corpus.py`，为 D7 结构化检索预留**）：
  `normalize_text/_parse_file_head/_normalize_filename/parse_corpus/CorpusIndex/_cap_corpus/
  existence_ratio/page_status/parse_source/_classify`（evidence_resolution.py:112-453 语料解析+匹配打分原语）。
- tender/audit 专属整合迁 `server/tender/evidence.py`：`resolve_audit_evidence`(:500) + scoring 专属助手
  (`_check_one/_check_hits/_hit_moves_score/_downgrade_scoring_item/_flag_low_clarity_sources`, :355-499)，
  挂 tender schema 的 resolve hook。
- 精确边界 impl 时按"是否碰 scoring 语义"划（碰 scoring→迁 tender / 纯语料·匹配→留 common）。
- 效果：ocr 测试（test_ocr_pipeline.py:686 / test_boq.py:167 用 CorpusIndex/existence_ratio/
  normalize_text/parse_corpus）import 改指 corpus.py，**不耦合 tender**；D7 直接复用 corpus.py。

**F6-F8（P2，impl 顺手带）**
- F6：`eval.py:34 from server.common.tender_output import is_real_number` → 迁移后新路径
  （tender_output → server/tender/output.py）。
- F7：验收护航拆两层——本地 pre-merge = 14/25 pytest + layering + 接缝测试；部署机 post-merge =
  D1 eval 闸真跑（需网关，非阻塞）。别让人误以为 eval 闸能本地 CI 自动跑。
- F8：每个 Ti 各自一 commit，pytest 全绿再进下一 Ti（红区回滚锚点）。

**状态**：F1/F5 已拍板、F2/F3/F4 已定，5 项 impl 前必补均已落地为可执行指引。**下一步可选**：再过一轮 critic
确认（推荐，因引入 contract 机制小改）/ 或主 agent 直接判 ready 进 impl。

---

## Round 2 · Critic Findings（2026-07-16，主 agent 已独立核验）

### VERDICT: NEEDS_REVISION

Round-2 critic 顶真实代码复核 R1 修订应答；主 agent 独立复核确认下述 P0/P1 属实
（读 output_contracts.py 全文 + rg 计数 test_contract_registry.py + 核 cli 路径 import 链）。

**G1 [P0] F6 schema 分家漏了核心三函数拆分 + 隐藏大批测试迁移（R1 应答未覆盖）**
- 已核实：`output_contracts.py:462-470` 单一处理器把 `normalize_audit_result`/`_validate_audit_result`/
  `enrich_audit_decision` 挂在 `DEFAULT_OUTPUT_SCHEMA_NAME`(audit-result) 上；这三函数**直接内嵌 tender 专属校验**——
  normalize 调 `_has_hard_disqualification`(:409)/`_normalize_optional_plan`(:443)；validate 调
  `_verify_scoring_consistency`/`_verify_score_mode_consistency`/`_verify_plan_shape`(:309-311)；
  enrich 调 `_finalize_user_explanation`(:193)。六 helper 全 import 自 `common/tender_output`(:30-37)。
- R1 应答 F1 只写"去掉 tender import / tender 注册 normalize/validate/enrich=…(裸 …)"，**从未写明这三函数
  必须一分为二**（通用版留 output_contracts 挂 DEFAULT；tender 组合版进 server/tender/output.py 叠加 tender 校验）。
  照字面实施 → 要么 audit/expense 仍跑 tender 校验(违 方案A 目标)，要么 tender 校验一并丢失。
- 隐藏测试迁移：`tests/test_contract_registry.py` **38 处** `DEFAULT_OUTPUT_SCHEMA_NAME` 引用，大量用 tender 载荷
  断言 tender 行为(废标/资格/scoring/plan/r4，:264-636) + `test_evidence_resolution.py:590-608`。tender 校验
  搬离 DEFAULT 后这批断言直接失败/静默失效 → 违"T5 全量 pytest 绿"。R1 的"接缝测试 3→4 条"严重低估。
- 补(若 F6 留 D2)：显式写出三函数拆分方案(通用/tender 边界 + 6 helper 逐个归属) + 把 test_contract_registry
  tender 行为块迁移列为验收独立 sub-task。

**G2 [P1] F3 自注册对 cli.py 入口未证**
- 已核实：cli.py→command_adapter→json_bridge→contract 全链路**零 `server.tender` import**(rg 确认)；
  cli.py:212 `tender_evaluate_json` 现传 `DEFAULT_OUTPUT_SCHEMA_NAME`。impl 若把 `TENDER_OUTPUT_SCHEMA_NAME`
  硬编码/经 core 转出而不 `from server.tender.output import`，`python -m server.cli tender-evaluate-json`
  独立进程永不触发注册 → `_SCHEMA_PROCESSORS.get` 得 None → 静默退化裸 JSON 校验 = 原 F3 缺陷经 CLI 复现。
- 补：强制 cli.py `from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME`；注册断言测试用隔离子进程，
  不得因同 pytest 进程内他模块已 import server.tender 蒙混。

**G3 [P2] 验收标准清单文档漂移**
- `## 验收标准`(:119-128 旧 draft 段) 仍列 `T3 [若纳入] worker background job harness 抽取`，与 R1 应答 F4
  "验收标准无 harness 项"矛盾。按 铁律[文档即真相] 须真删/renumber，不能只在下文散文覆盖。
- 附：迁移清单只列 eval.py，漏 `test_tender_output.py`/`test_evidence_resolution.py`/`test_boq.py`/
  `test_ocr_pipeline.py` 的 import 路径改动(`server.common.{tender_output,evidence_resolution}` → `server.tender.{output,evidence}`)。

### 已闭合 / 部分闭合
- **F2 RESOLVED**：cli.py:212 确为唯一第二调用点(audit/compare/doc_pipeline 各自独立 schema，未受影响)。
- **F5 RESOLVED**：corpus 拆分边界与真实 evidence_resolution.py 结构一致(通用原语 :112-346 不反调 scoring :355-500)；
  ocr 测试仅 import 通用原语，post-split 指向 corpus.py 干净。P2 nit：resolve_audit_evidence 懒 import
  `enrich_audit_decision`(feature→common 合法)，impl 时须确认 G1 拆分后的通用 enrich 仍够 tender 降级路径用。
- **F1/F3 PARTIALLY RESOLVED**：schema_path 别名机制本身经核可用(frozen dataclass 加可选字段安全)，但依赖 G1
  的深层拆分未写明；F3 机制对 runner/worker/eval 成立、对 cli 不成立(见 G2)。

### 关键结论：F6=A 的真实成本
R1 把 F6 定性为"含 contract 机制**向后兼容小改**"。Round-2 证伪：F6=A 实为**共享 contract 层的行为重构**
（拆 3 核心函数 + 迁移 test_contract_registry 大批断言 + 6 helper 边界判定），回归面显著，非"小改"。
**下一步取决于范围决策**（见 session：保 F6 在 D2 补全修订+round3 / 或 F6+F5 拆独立 sprint、D2 只做纯移动）。

---

## Round 2 后 · D2 范围定稿（2026-07-16，用户拍板 F6+F5 拆分）

> **本节为 D2 最终范围，覆盖上文 draft 迁移清单与 Round1 应答中一切关于 F6/F5 归属的表述。**
> 触发：Round-2 critic G1 证伪"F6=A 向后兼容小改"——实为共享 contract 层行为重构。用户拍板：
> **F6(schema 分家) + F5(evidence 拆分) 拆出独立 sprint；D2 只做已核实为干净的纯移动。**

### D2 in-scope（纯移动/拆分，回归面小）
- T1 `routes/tender_worker.py` → `server/tender/worker.py`
- T2 `routes/tender_compare_worker.py` → `server/tender/compare_worker.py`
- T3 `routes/tender_doc_pipeline.py` → `server/tender/doc_pipeline.py`
- T4 `routes/tender.py`(912) 按 banner 拆薄为 HTTP 壳 + tasks/projects/docs/compare 分节路由
- T5 test_layering 守卫扩展 + 全量 pytest 绿 + ruff

**迁移面已核实干净（2026-07-16 rg 实证）**：三个待迁文件仅下行 import
（common/platform/stores/ocr/tender），无 features→routes/ops/app 上行边；`ocr/prewarm_scheduler.py`
是被 doc_pipeline 消费（features→ocr 下行，合法），非反向。consumer 仅 `routes/tender.py`（壳，
routes→features 下行）+ `tender/runner`+`__init__`（同层），余皆注释。故为真·纯移动，无依赖破除接缝。

### D2 out-of-scope → 新 sprint `tender-schema-split`（F6+F5，待立）
承接 Round-2 未闭合项，作新 sprint 的 design 输入（不丢）：
- **F6 schema 分家**：拆 `normalize_audit_result`/`_validate_audit_result`/`enrich_audit_decision`
  为"通用版留 output_contracts 挂 DEFAULT + tender 组合版进 server/tender/output.py 叠加 tender 校验"（G1）；
  6 helper 通用/tender 边界判定；`test_contract_registry.py` 38 处 tender 行为断言迁移 TENDER schema；
  schema_path 别名（F1 机制 Round-2 已验可用）；cli.py `from server.tender.output import`（G2）+ 隔离子进程注册断言测试。
- **F5 evidence 拆分**：通用语料原语 → `server/common/corpus.py`；`resolve_audit_evidence` + scoring 助手
  → `server/tender/evidence.py`（边界与机制 Round-2 已验 F5 RESOLVED）。
- 依赖：F6/F5 sprint **depends_on D2**（worker 归位后再动 output/evidence/schema，避免二次搬迁）。

### 门禁判定
Round-1/Round-2 的 NEEDS_REVISION 阻塞项**全部为 F6 专属**，随 F6 移出 D2 即消解。D2 剩余纯移动
经 rg 核实无开口 finding。**主 agent 判 D2 定稿 ready 进 impl（红区 worktree 强制：generator +
`isolation: worktree`，T1-T5 TDD，每 Ti 单 commit + pytest 绿再进下一）。**

_决议：compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md。_
