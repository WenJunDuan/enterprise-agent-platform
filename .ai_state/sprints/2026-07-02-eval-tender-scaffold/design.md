# D1 · eval_tender 评测脚手架正式化 — design

> roadmap: 2026-07-doc-intelligence / Wave0 / D1 (eval-tender-scaffold)
> path: Feature (infra) · effort M · 状态: **定稿（GO）**。round1 critic F1-F4 已全部修订（正文含
> `round1 Fx 修订` 标记）；round2 F5 [P0] 的 OCR 分层归属已于 **2026-07-15 用户拍板方案 i**
> （ocr 降为 feature 域之下服务层，守卫改单向，详见文末 Round 2 决议），正文 T2/T5 已按
> 方案 i 连带修订。impl 从 T1 起，每 T commit + pytest 绿再进下一 T。

## 背景（WHY）

1. **S7 harness 已蒸发**：`logs/s7-flash-stress/run_stress.py`、`logs/s7-model-compare/run_compare.py`、
   `REPORT.md` 放在 gitignored 的 `logs/`（.gitignore:9），从未入库，现已从磁盘消失。压测方法论仅
   幸存于 `compound/2026-07-01-learning-flash-tender-eval-inconsistency.md` 与旧 items.yaml progress。
   ——"评测资产放临时目录"被证明不可持续，必须正式化进版本控制。
2. **全 program 的回归闸**：D4（L2 路由）/D5（agent 化）/D6-D8（结构化+RAG+底稿瘦身）每一项都改变
   识别或底稿形态，没有 golden case + 一致性评测就无法证明"评标质量不回退"。D8 的验收
   （S7 结论复测）直接依赖本脚手架。
3. **核心方法论**（S7 学到的，必须固化）：评标评测**不能只看完成率/verdict**——Flash 6/6 产出合法
   结论但同标书 3 次实得合计 `[40, 66, 9]`（7 倍漂移）。必须看结构化 `scoring[]` 的**项数与实得合计
   的跨次方差**，辅以 `policy_refs` 非空合规率、契约重试次数、时延。

## 方案

### 选定：`server/tender/eval.py` 纯评分核 + 复跑 runner（镜像 audit 先例）

结构完全对齐 `server/audit/eval.py` 的成熟形态（纯评分离线可测 / runner 需真实网关部署机跑），
在其 GoldenCase 骨架上扩展评标特有维度：

```
server/tender/__init__.py          # 新包（同时为 D2 迁移预留家）
server/tender/eval.py              # 纯评分核 + CLI runner（python -m server.tender.eval）
tests/test_tender_eval.py          # 纯评分部分单测（离线全绿）
tests/eval_fixtures/tender/
  golden_manifest.json             # 合成模板（真实 case 在部署机 data/，gitignored，先例同 audit）
  README.md                        # runbook（见下）
```

**评分维度（GoldenTenderCase → score_case + score_consistency）**：

| 维度 | 判定 | 来源 |
|---|---|---|
| verdict / manual_review_reason | 精确匹配（沿用 audit） | golden 期望 |
| eligibility_checks | 逐条 pass/fail/manual 匹配 | golden 期望 |
| scoring[] 单次 | 每项 status ∈ 期望集合；实得合计落带宽 `[min,max]` | golden 期望 |
| **跨次一致性**（新增核心） | repeat-N（默认 3）同 case：出分项数极差 ≤ `max_item_spread`；实得合计极差 ≤ `max_total_spread` | S7 学习 #1 |
| policy_refs 合规 | 承重结论 policy_refs 非空率 = 100%（硬规则） | S7 配套问题① |
| 运维指标 | 每次重试数 / 时延，只记录进报告不判 pass（基线数据） | S7 配套问题② |

**null 语义（round1 F2 修订）**：出分项数 = `scoring[]` 中 score 为实数的条目数；实得合计 =
该子集 score 之和。实数判定**复用生产同源逻辑** `server.common.tender_output._is_real_number`
（顺带升为公开名 `is_real_number`，1 行 alias，避免再造跨模块 import 私有名的臭味；
feature → common 方向合法）。全 null run（S7 案例B run3 崩塌形态）出分项数记 0、合计记 0，
照常进极差计算——正是要让"崩塌"撑大极差被闸住。

**阈值策略**：`max_item_spread` / `max_total_spread` 进 manifest 可配置；首版默认**警告模式**
（打印超标不置 fail），待部署机用 V4Pro 跑 3 次建立基线后收紧为硬门（记入 manifest，二次 commit）。
理由：无基线先锁死阈值 = 拍脑袋，会把闸做成摆设或路障。
**止损（round1 F4 修订）**：硬门锁定是 **D4 开工的前置条件**（已写入 roadmap items.yaml D1/D4
note），警告模式不得跨 Wave 存活。

**Runner（round1 F1 修订 + round2 F5 方案 i 修订：分层合法 + 复用生产路径，两者兼得）**：
- **评标核心下沉**：把 `_run_evaluation` 及其 doc-layer 助手（`_wait_doc_layer_ready` /
  `_load_doc_layer_context` / 相关开关读取）从 `routes/tender_worker.py` **移入**
  `server/tender/runner.py`（公开名 `run_tender_evaluation`）；routes 层保留任务调度壳
  （schedule/execute/track）改为 import feature 层——方向 routes → features 合法，
  入口结构与 audit 同构（`routes/audit_worker` → `server/audit/runner`）。
- **OCR 依赖处置（方案 i，2026-07-15 拍板）**：分层教义修订——ocr 从 tender/audit 的平级
  sibling 降为 feature 域之下的**服务层**（现实已有 audit_worker / tender_worker /
  tender_doc_pipeline 三处按服务消费）。`_run_evaluation` 内嵌的 `ocr_preprocess_block`
  调用**随代码一起下沉**（tender→ocr 自此合法，不再注入）；`TENDER_OCR_PURPOSE` 从
  `routes/tender_doc_pipeline.py:33` **挪家至 `server/tender/`**，tender_doc_pipeline 改为
  从 feature 层 import（routes→features 合法），消除 tender→routes 逆向依赖。
  守卫改**单向**：允许 tender/audit→ocr，禁止 ocr→tender/audit（既有 audit↔ocr 互斥断言
  同步改单向）。audit feature 层现无 ocr 依赖，D1 不改 audit 现状。
- 为什么不按 critic 原案"新 runner 直调 run_command_json ~15 行"：eval 是回归闸，必须打**生产
  同一条路径**（doc-layer 底稿复用、criteria 注入、契约重试都是被测行为，D8 底稿瘦身复测正要测
  这里）；平行重写会造第二真相源。下沉方案同时满足 F1 的分层约束与"测生产路径"的根本目的。
- 副产品：D2 的"worker 核心迁包"一块被前置完成，D2 剩余范围相应缩小。**以纯移动为主，
  但含两处接缝改动（round2 连带修订，"零行为"表述作废）**：① `TENDER_OCR_PURPOSE` 挪家
  （routes 引用点改 import）；② tender→ocr import 方向合法化（守卫改单向）。接缝须补
  针对性测试，其余由既有 worker/read-layer/timeout 回归测试守护。
- 每 case 串行 repeat-N（评标 ~3-5 min/次且打真实网关，不并发，防限流/互相干扰计时）。
- 单 case 异常记 ERROR 不中断全局（沿用 audit 先例）。
- `--model` CLI 覆盖 → 环境无关的 A/B：同 manifest 分别跑两个模型出两份报告人工对比
  （不做双模型自动对比逻辑，KISS——S7 的对比是一次性分析，闸只需单模型回归）。

**配置（迁自 S7 remaining）**：
- `config.AuditSettings` 同级新增 `TENDER_EVAL_MODEL`（空 = 用全局 MODEL_NAME）；
- `tender_worker` per-call model 覆盖，仿 `_TENDER_EFFORT` 先例（read env → run_command_json 透传）；
- 不再做 `get_flash_model_config()` 专名（S7 原案），泛化为任意模型名覆盖——Flash 只是取值之一。

**Runbook（README 固化，防知识再蒸发）**：
- 部署机跑：`uv run python -m server.tender.eval --manifest <m> [--repeat 3] [--model deepseek-v4-pro]`
- CC 内跑必须 `env -u ANTHROPIC_BASE_URL -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_MODEL`
  （CC 注入的 base url 压过 .env 触发 offline_guard，compound 学习 #3）；
- 切小窗口模型前必设 `MODEL_CONTEXT_WINDOW`（触发 S7 截断 guard），重跑观察"run3 崩塌"是否消失
  ——**用户侧待办**：填真实窗口值后用本脚手架复测。

### 备选（放弃）

- **A. 脚本放 `tests/eval_tender.py`**（S7 remaining 原表述）：pytest 会收集它但它需要真实网关，
  要加 skip 标记且语义别扭（它不是单测是 harness）。audit 先例已选 `server/audit/eval.py`，对称胜出。
- **B. 通用化改造 audit/eval.py 成跨域 eval 框架**：两域评分维度差异大（audit 无 scoring/一致性维度），
  强行抽象是过早 DRY；等第三个消费者出现再抽（OCP）。共享的只有"manifest+纯评分+报告"理念。
- **C. harness 继续放 logs/ 快速迭代**：已被证伪——蒸发一次了。

## 影响范围

- 新增：`server/tender/`（包 + eval.py + runner.py）、`tests/test_tender_eval.py`、
  `tests/eval_fixtures/tender/*`
- 修改：`server/routes/tender_worker.py`（评标核心+doc-layer 助手**迁出**至 runner.py，
  routes 留调度壳改 import）、`server/routes/tender_doc_pipeline.py`（`TENDER_OCR_PURPOSE`
  挪家至 server/tender/ 后改 import，方案 i 接缝）、`server/platform/config.py`
  （+TENDER_EVAL_MODEL，≈10 行）、`server/common/tender_output.py`（`_is_real_number`
  升公开名，1 行）、`tests/test_layering.py`（tender 域 4 条守卫 + audit↔ocr 互斥改单向，见 T5）
- 行为面：迁移以纯移动为主，两处接缝（TENDER_OCR_PURPOSE 挪家 / tender→ocr 合法化）补
  针对性测试；model 覆盖默认空=现行为
- 不动：审核域、OCR 域、前端

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 真实 case 成本（~$3/次 × repeat3 × N case） | eval 只部署机手动触发不进 CI；manifest 从 2 个标书起步 |
| 阈值无基线拍脑袋 / 警告模式长期化 | 首版警告模式，V4Pro 基线跑完锁硬门；**硬门锁定=D4 开工前置**（F4 止损，记入 roadmap） |
| worker 核心迁包引回归 | 以纯移动为主+两处接缝（方案 i）；接缝补针对性测试，test_tender_worker_timeout / test_tender_read_layer / test_tender_routes 等全量守护；D2 剩余范围因此缩小 |
| `server/tender/` 新包撞 layering 测试 | 新包按 feature 域规则注册进 test_layering（不 import audit/ocr），本 sprint 内补 |
| 合成 fixture 与真实标书结构漂移 | README 明确"模板仅示意 layout，期望值须在部署机标定后填" （同 audit 先例措辞） |

## 验收标准（Sisyphus 清单）

- [ ] T1 `server/tender/eval.py` 纯评分核：GoldenTenderCase 解析 / score_case（verdict+eligibility+
      scoring 带宽+policy_refs）/ score_consistency（repeat-N 极差，null 语义复用公开化的
      `tender_output.is_real_number`）/ format_report — **TDD 先测后实现**
- [ ] T2 评标核心迁包：`_run_evaluation`+doc-layer 助手 → `server/tender/runner.py`（公开名
      `run_tender_evaluation`），routes/tender_worker 留调度壳改 import；**方案 i 接缝**：
      `ocr_preprocess_block` 调用随迁（tender→ocr 合法）、`TENDER_OCR_PURPOSE` 挪家
      server/tender/（tender_doc_pipeline 改 import）——接缝补针对性测试，其余纯移动
      （既有 worker/read-layer/timeout 测试全绿为证）；eval 侧 runner：repeat-N 串行 +
      单 case 容错 + `--manifest/--repeat/--model` CLI
- [ ] T3 config `TENDER_EVAL_MODEL` + per-call 覆盖（仿 _TENDER_EFFORT），默认空零行为变更
- [ ] T4 `tests/eval_fixtures/tender/`（合成 manifest 模板 + runbook README 含 env -u 坑 +
      MODEL_CONTEXT_WINDOW 提示）
- [ ] T5 `tests/test_tender_eval.py` 纯部分离线全绿（含全 null run 极差边界用例 F2 +
      `repeat < 2` 边界用例，round2 F7）；`test_layering.py` 补 tender 域 4 条守卫
      （F3，按方案 i 修订）：(a) tender↔audit 互斥 / (b) **ocr→tender 与 ocr→audit 单向禁止
      （tender/audit→ocr 合法，既有 audit↔ocr 互斥断言改单向）** / (c) ops forbidden 加
      server.tender / (d) common+stores forbidden 加 server.tender；全量 pytest 绿
- [ ] 部署机验证（用户/部署机侧）：真实 manifest 跑通出报告；A/B 两模型两报告；
      MODEL_CONTEXT_WINDOW 填值后复测截断——此三项属 runbook 验收，不阻塞代码 merge

---

## Round 1 · Critic Findings (critic, 2026-07-02T06:30:00Z)

### VERDICT: NEEDS_REVISION

### 评分

| 维度 | 评分 (1-5) | 关键 finding |
|---|---|---|
| 边界条件 | 3 | manual_review 项 score:null 合计运算已有处理（tender_output.py:147-183），但 score_consistency 对全 null 场景的极差算法 design 未说明 |
| 错误处理 | 4 | 单 case 容错已沿用 audit 先例；score_consistency 极差对 repeat-N < 2 场景未提 |
| 测试覆盖 | 3 | score_consistency 是新增核心维度，无离线测试策略说明；mock run_tender_evaluation 返回值如何构造 manifest 未提 |
| 历史决策对齐 | 2 | **严重**：server/tender/eval.py 拟 import server.routes.tender_worker（wrapper），feature 层 import routes 层，违反已落地的分层守卫 |
| 复杂度 | 4 | 范围合理，M 努力量准确；D2 预留 hook 设计 OK |
| 历史教训 | 4 | 基本固化了 S7 教训；env -u 坑、MODEL_CONTEXT_WINDOW 坑都写进 runbook |

---

### Findings（按严重度）

#### F1 [P0] 分层违反：server/tender/eval.py import server.routes.tender_worker，feature 层反向依赖 routes 层

- **现象**：design 方案节明确"Runner 入口：tender_worker 新增公开 wrapper run_tender_evaluation(...)，eval 只 import 公开名"（design.md:51-53）。即 server/tender/eval.py（feature 层）import server.routes.tender_worker（routes 层）。test_layering.py 的分层守卫方向为 app → routes → ops → features → core → common → stores → platform（test_layering.py:9），feature 层 import routes 层是逆向依赖，pytest 会立即 fail。
- **对比先例**：server/audit/eval.py 只 import server.audit.runner（同 feature 层），绝不碰 routes（eval.py:29）。tender eval 必须镜像此模式。
- **建议**：新建 server/tender/runner.py（约 15 行），直接调用 server.common.command_adapter.run_command_json（common 层，eval → feature → common 方向合法）；eval.py import server.tender.runner；tender_worker 的公开 wrapper 保留供 HTTP 层，但 eval.py 不 import 它。
- **引用**：tests/test_layering.py:9,86-101；server/audit/eval.py:29

#### F2 [P1] score_consistency 对 score:null 项的极差算法未规范，与 tender_output._is_real_number 语义存在分歧风险

- **现象**：design 定义"出分项数极差 / 实得合计极差"（design.md:42），但 S7 案例B 第3次实得合计 9 接近全 null 极端，当某次所有 score 为 null 时，"出分项数"算法不明（null 算出分项还是不算）。tender_output.py:263-264 的 _is_real_number 是生产代码的判断基准，eval.py 若独立实现不同语义，基线数据会失真，后续收紧阈值的依据变形。
- **建议**：design 补一句规范：出分项数 = score 通过 _is_real_number 校验的 scoring[] 条目数；实得合计 = 同上条目之 score 求和。score_consistency 实现直接导入并复用 _is_real_number（server.common.tender_output，common 层，分层合法）。T1 验收项补"全 null run 极差=0 的离线测试"。
- **引用**：server/common/tender_output.py:263-264；compound/2026-07-01-learning-flash-tender-eval-inconsistency.md 教训#1

#### F3 [P1] T5 layering 补测内容模糊，现有断言对 tender 域是空白守卫

- **现象**：test_layering.py 的 test_feature_domains_do_not_import_each_other 只硬编码 audit↔ocr 互斥对（test_layering.py:88-90）；test_ops_does_not_import_routes_app_or_features 的 forbidden 元组只含 server.audit/server.ocr（test_layering.py:99）；test_common_does_not_import_feature_or_upper_layers 的 forbidden 同理（test_layering.py:75-76）。新建 server/tender/ 后若只补注释，tender 域对 ops/common/stores 的反向 import 完全没有守卫。
- **建议**：T5 改为 4 条明确断言目标：(a) tender↔audit 互斥，(b) tender↔ocr 互斥，(c) ops forbidden 加 server.tender，(d) common+stores forbidden 加 server.tender。
- **引用**：tests/test_layering.py:75-76,88-90,99,113-114

#### F4 [P2] 警告模式首版无止损追踪机制，基线收紧是隐性义务

- **现象**：design 说"V4Pro 基线跑完再锁硬门（二次 commit）"（design.md:47），但该步骤不在任何验收项或 items.yaml note 里，D4/D5/D6 均 depends_on D1 做回归（items.yaml:66,95），若警告模式漂移到 Wave1，一致性问题永远不 fail，S7 教训未真正固化。
- **建议**：runbook README 增加"基线收紧 checklist"步骤；items.yaml D1 note 补一句"基线跑完须二次 commit 锁硬门，D4 上线前此步为前置条件"，使收紧成为可追踪待办。
- **引用**：design.md:46-48；items.yaml:65-66（D4 depends_on D1）

---

### 建议下一轮重点（若 NEEDS_REVISION）

1. **F1 分层修复（必须）**：新建 server/tender/runner.py 薄包装 run_command_json，eval.py 只 import 该 runner，不 import server.routes.*。tender_worker 的公开 wrapper 保留但不被 eval 引用。
2. **F2/F3 规范补全**：design 方案节补 score_consistency null 处理语义（一句话对齐 _is_real_number）；T5 展开为 4 条具体 layering 断言目标。
3. **F4 止损**：在 T4 runbook README 增加"基线收紧 checklist"，D1 items.yaml note 补追踪句，防止警告模式无限漂移至 D4 验收前。

---

## Round 2 · 主 agent 代码核验 Findings (2026-07-03)

> 触发：用户要求"对照代码检查优化点是否正确"。逐条核验 design 事实主张后发现
> round1 F1 修订（评标核心下沉）引入了 critic 与 design 均未覆盖的传递依赖问题。

### VERDICT: NEEDS_DECISION（一处 program 级分层决策，其余维持定稿）
### → 已决议（2026-07-15）：用户拍板**方案 i**，见文末决议记录；design 转 GO

### F5 [P0] T2 下沉方案与 T5 自加守卫直接冲突：`_run_evaluation` 携带 tender→ocr / tender→routes 传递依赖

- **现象**：`_run_evaluation` 的 inline OCR 回落调用 `ocr_preprocess_block`
  （routes/tender_worker.py:19 import `server.ocr.pipeline`，:198 调用），并使用
  `TENDER_OCR_PURPOSE`（:21 import `server.routes.tender_doc_pipeline`，常量定义在
  tender_doc_pipeline.py:33）。整体移入 `server/tender/runner.py` 后：
  ① tender(feature) → ocr(feature)，**T5 守卫 (a)/(b) 的 tender↔ocr 互斥会立即 fail 刚迁入的代码**；
  ② tender(feature) → routes，正是 round1 F1 抓的那类逆向依赖换形式复发。
- **对照先例**：audit 的真实同构解法是 **OCR 预处理留在 routes 层注入**——routes/audit_worker.py:15
  import ocr_preprocess_block，feature 层 `run_inline_directory_audit` 只收注入好的 `ocr_block`，
  docstring 明写"feature 域 audit/ 不可跨域 import ocr/"（server/audit/runner.py:129-131）。
  design 声称"与 audit 完全同构"的前提未满足。
- **波及 D2**：`tender_doc_pipeline` import `server.ocr.pipeline` + `server.ocr.prewarm_scheduler`
  （tender_doc_pipeline.py:19-20），D2 迁它进 server/tender/ 时同一矛盾再爆。且 tender 与 audit
  不同：真实标书是扫描件、S7 harness 正是复用生产 `_run_evaluation` 含 OCR 路径——eval 绕不开 OCR。
- **两个可选解（program 级，拍一次管 D1+D2）**：
  - **方案 i（主 agent 推荐）**：修订分层教义——ocr 从 tender/audit 的平级 sibling 降为 feature 域
    之下的服务层（现实已有三处按服务消费：audit_worker / tender_worker / tender_doc_pipeline）。
    T5 守卫改**单向**：允许 tender→ocr，禁止 ocr→tender/audit。改动最小、承认既成事实、
    eval CLI 保持 `python -m server.tender.eval` 与 audit 对称。
  - **方案 ii**：坚持 sibling 教义——OCR 回落留 routes 侧注入（`run_tender_evaluation` 收
    `ocr_block` 或注入 callable），`TENDER_OCR_PURPOSE` 挪家；代价：eval CLI 需 OCR 故不能落
    server/tender/eval.py，须上浮 app 层（如 `python -m server.cli eval-tender`），破坏入口对称，
    D2 迁 tender_doc_pipeline 还要再造注入缝。
- **连带修订**：无论选哪个，T2 的"纯移动零行为"表述不再成立（必然有接缝改动），须改口并给接缝补
  针对性测试。

### F6 [P1] D2 迁移清单中 `tender_output` / `evidence_resolution` 被 common 层自身消费，迁不动

- **现象**：`server/common/output_contracts.py:30,460`（common 层共享契约机，audit 亦消费）
  import 这两个模块。D2 按 items.yaml 迁它们进 server/tender/ → common→feature 逆向依赖，
  撞 T5 守卫 (d)。D1 的 `is_real_number` 升公开名方案不受影响（D1 时点 tender_output 仍在 common）。
- **处置**：已记入 items.yaml D2 note 与 decisions_needed，D2 design 时解。

### F7 [P2] 小账两笔

- items.yaml D2 "39 个 tender 测试文件护航"是虚数：实测文件名含 tender 的 14 个、内容引用 tender
  的 25 个。已在 D2 note 修正，防 D2 时误判护航面。
- score_consistency 对 `repeat < 2` 的行为（round1 critic 曾提）未进 T5 验收用例，T5 补一条边界。

### 已核验为正确（免重查清单）

`_is_real_number` 在 tender_output.py:263 ✓；`build_options` `defaults.update(overrides)` 支持
per-call model 覆盖、`_TENDER_EFFORT` 先例管道通（T3 可行）✓；audit eval/runner 先例结构与 design
描述一致 ✓；F4 硬门锁定=D4 前置已双向记录 ✓；roadmap D2-D11 依赖图自洽 ✓。

---

## Round 2 决议记录（2026-07-15，用户拍板）

- **决策：方案 i** —— ocr 从 tender/audit 的平级 sibling 降为 feature 域之下的服务层；
  T5 守卫改单向（允许 tender/audit→ocr，禁止 ocr→tender/audit）；eval CLI 保持
  `python -m server.tender.eval` 与 audit 入口对称。program 级，一并解 D2 的
  tender_doc_pipeline→server.ocr 同题（items.yaml D2 note ① 随之关闭）。
- **依据**：改动最小；承认既成事实（audit_worker / tender_worker / tender_doc_pipeline
  三处已按服务消费 ocr）；方案 ii 需 CLI 上浮 app 层破坏入口对称，且 D2 还要再造注入缝。
- **连带修订已执行**：正文 Runner 节（OCR 依赖处置）、影响范围（+tender_doc_pipeline）、
  风险表、T2（接缝改动+针对性测试，"纯移动零行为"作废）、T5（守卫 (b) 改单向）。
- **教义落盘**：architecture/ARCHITECTURE.md 分层节补拍板注记（守卫落地后改图）；
  compound/2026-07-15-decision-ocr-service-layer.md。
- **GO 生效**：impl 从 T1 起，TDD，每 T commit + pytest 全绿再进下一 T。
