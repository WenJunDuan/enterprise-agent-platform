---
sprint_slug: "2026-08-12-prompt-architecture"
path: "Refactor"
created: "2026-08-12"
last_updated: "2026-08-12"
executor: "generator subagent model=opus, isolation: worktree (红区 Refactor)"
---

# Design — 提示词架构重构：热路径下沉 + 语义单源 + 预算门禁 + 占位清理

## 背景

2026-08-12 第三方审计结论（会话审计，数据实测）：

- `tender-evaluate.md` 38,754B/141 行，判分纪律棘轮只进不出——每次事故加一段，从未做
  "热路径精简 + references/ 下沉"；规则挤压已实际产生行为缺陷（本周修的"待横比泛化"
  "主观免责套话"均为规则互压产物）。
- skills 渐进披露机制闲置：6 个 skill 仅 4 个 references 文件，全部命令只有 2 处确定性
  Read 下沉点（s1-locate-criteria.md 是唯一业务先例）。
- 语义复本：`pending_reason` 枚举活在 4 处（evaluate prompt / audit-result.schema /
  output.py / 前端 types），tag 语义活在 3 处；本周判分纪律修订实际同步了 5 个位置。
- `common/`(406B)、`system/`(273B) 两个 skill 为占位空壳，构成路由假选项。

预期收益（诚实口径，2026-08-12 会话已向用户说明）：主收益是**正确率与一致性**（注意力集中 +
语义单源防漂移）与**维护成本**；token 节省有限；单次时延可能因 Read 略增、但契约重试率下降
预计净正。收益验证走 D1 eval 回归闸 A/B（见 T0/AC7）。

## 目标

1. `tender-evaluate.md` 瘦身到 ≤15KB：只留 S0-S4 骨架 + 硬门，裁决细则下沉
   `tender-eval/references/` 并在对应步骤确定性 Read。
2. `pending_reason` / criteria `tag` 枚举单源化：schema 为唯一权威（enum + description），
   prompt 引用不复述，output.py 从 schema 读枚举。
3. 提示词预算门禁：pytest 级字节上界断言，超界即红，棘轮不再回长。
4. common/system 占位 skill 处置：并入或删除，引用零悬空。

## 非目标

- **不改任何判分语义**——本 sprint 是纯搬家/收拢（Refactor），tender-evaluate 的全部规则
  内容逐字保留（含 2026-08-12 三轮判分纪律修订），只改放置位置与引用方式。
- 不做前端 types 代码生成（4 处复本收敛到 2 处：schema 权威 + 前端手写消费加指向注释即可，
  生成器属过度工程）。
- 不动 expense 域 prompt（验证收益后另行推广）。
- 不改 run_command_json 注入机制、不新增 prompt-loader 抽象。

## 已调研的现成方案

渐进披露即仓库自有惯例（skills references/ + 命令内确定性 `Read` 指令，先例
`s1-locate-criteria.md`，Anthropic Agent Skills 官方模式），无需外部组件。预算门禁用 pytest
断言而非新 hook——不新增 harness 机制（反过度工程；且随 CI 跑，跨机器一致）。schema 读枚举用
标准库 json，无新依赖。

## 关键决策

### KD1 · 热路径下沉（P1）

`tender-evaluate.md` 目标结构（≤15KB）：

- **保留（骨架+硬门）**：执行方式说明、S0-S4 各步的目标与产出物清单、决断总纲与"独立评审
  单元"纪律、pending_reason 硬闸一句话（枚举见 schema）、输出契约核心（单 JSON、verdict 三值、
  禁 review_dimension）、页锚两坐标系规则**简版**（三行）、单投标人边界。
- **下沉到 `.claude/skills/tender-eval/references/`**（新建 **5** 个，单文件 ≤10,240B，
  critic R1-F1 修订——原 4 文件方案字节账算不拢：S1 细则实测 9,039B 无去向、s3 按原定义装
  L75-95+L99 达 9,607B 超原 8KB 上界）：
  1. `s1-criteria-structuring.md`：S1 的 criteria 结构化提取细则全文（五种 score_mode 的
     结构化字段定义、formula_spec 变量 source 白名单、拆子项/复合行拆分、rejection_rules、
     max:null 规则）——S1 开头与既有 s1-locate-criteria.md 一并 Read。
  2. `s3-scoring-modes.md`：五种 score_mode 裁决细则全文（deduction/banded 含主观档次直接
     选档纪律/additive 禁整项 punt/formula 变量闭合与报价拆层/pass_fail 判0二分与读不清
     保护）。**必须含 pending_reason 取值+一句话语义简表（标注"权威=audit-result.schema.json"）**
     ——枚举在 S3 运行时上下文必须可达，否则模型凭记忆写错值反推高重试率（critic R1-F3）。
  3. `s4-verdict-summary.md`：verdict 合成、废标独立 gate 与 confirmed 闸、一致性二分决断、
     综合意见口径、policy_refs 规则、口头总分一致性。
  4. `evidence-citation.md`：证据定位细则（页锚书写**全文（权威版）**、quote 逐字、印刷页 vs
     OCR 页、回查闸说明）——骨架里的页锚三行简版标注"细则以本文件为权威"。
  5. `output-json.md`：JSON 合法性细则、extracted_data 字段契约对照、
     **manual_review_reason 枚举全文**（critic R1-F3 配套）。
- Read 指令位置（每文件**恰读一次**，后续步骤回指不重复 Read——critic R1-P2）：S1 开头读
  1（连同既有 s1-locate-criteria.md）；S2 开头读 4（证据书写细则供 S2/S3 共用，S3 处只写
  "证据书写按已读 evidence-citation.md"）；S3 开头读 2；S4 开头读 3；输出前读 5。
- **逐节字节预算表（critic R1-F1，基准 eac2a16 实测，AC1 依此复核）**：

  | 骨架保留节 | 预算 B |
  |---|---|
  | 头部+页锚简版 | ≤1,200 |
  | 执行方式+S0 | ≤700 |
  | S1 目标句+Read 行（细则下沉后） | ≤900 |
  | S2 全文保留（实测 2,200） | ≤2,400 |
  | S3 资格审查+决断总纲+Read 行 | ≤2,800 |
  | S4 骨架+Read 行 | ≤1,800 |
  | 输出契约核心 | ≤2,600 |
  | 单投标人边界 | ≤1,300 |
  | **合计** | **≤13,700 ≤ 15,000 ✓** |
- **Read 失败语义**：容器内 `.claude/` 随部署同步、文件必在；若 Read 失败属部署缺陷，模型
  应在结论 explanation 声明"评分细则文件缺失，本单按骨架规则保守评定"并将整单降
  manual_review（rule_gap）——fail-visible，不静默。此语义写进命令骨架一行。
- **附录 A（本设计文末）：段落去向对账表**——现文件每个段落 → 去向（保留/哪个 reference），
  reviewer 按表逐段核对"零语义删改"。

### KD2 · 语义单源化（P1）

- `audit-result.schema.json`：`pending_reason` enum 每个取值补 `description`（一句话语义 +
  适用场景，内容取自现 prompt 第 76 行的定义，逐字迁移）。scoring item 定义处同补。
- `criteria.schema.json`：`tag` enum（scored/requires_cross_bid_comparison/requires_external_data/
  requires_live_event）补 description（语义取自现 prompt/SKILL.md）。
- `tender-evaluate.md` 骨架只写："score:null 必带 pending_reason，枚举与各值语义见
  audit-result.schema.json（服务端按 schema 校验，选最贴切的一个）"；s3 reference 里可保留
  简表但标注"权威=schema"。
- `server/tender/output.py`：硬编码枚举集合改为**惰性首用加载 + 缓存**（critic R1-F4 钉死
  实现，禁止模块加载期读——output.py 加载期 import `server.common.contract` 部分符号会成环，
  见该文件 L35-42 注释与 compound/2026-07-18-learning-lazy-import-behavioral-seam.md）：
  独立函数 `_load_pending_reasons(path) -> frozenset`（测试直调它并传篡改副本路径即得
  tamper 测试，无需 reload/env 配置项）+ 首用缓存。schema 路径经
  `server.common.contract.resolve_output_schema_path` 惰性解析，**不得手搓 PROJECT_ROOT 拼接**
  （防与 contract.py 双写漂移）。注意：**audit-result.schema.json 的 pending_reason
  enum+description 已存在**（H1 6c766a5 交付），KD2 此项是核对齐 prompt L76 语义 + 接线，
  不是新增；**禁止改成 oneOf/const 形态**（会破坏读 `enum` 数组的实现）。校验行为零变化——
  现有 test_tender_pending_reason.py 11 条零修改全绿即证。
- 前端 `types.ts` 的枚举保留手写，但在类型定义上方加注释
  `// 权威定义: .claude/contracts/common/audit-result.schema.json (修改先改 schema)`。
- SKILL.md 的 tag 段落改为引用 criteria.schema.json + 保留 G5 例外一句话。

### KD3 · 提示词预算门禁（P2）

新增 `tests/test_prompt_budget.py`：

- 上界表（字节，含 15% 余量原则，基线 2026-08-12 实测）：
  `tender-evaluate.md ≤ 15_000`（重构后目标）、`tender-compare.md ≤ 8_200`（现 7,132）、
  `tender-extract-info.md ≤ 6_800`（现 5,871）、`audit.md ≤ 5_300`（现 4,584）、
  `CLAUDE.md ≤ 9_600`（现 8,323，KD4 改后按实测重取）；references/ 单文件 ≤ 10_240（与 KD1 上界一致）。
- 断言超界即红，失败消息写明"超界须下沉 references/，流程见本测试头注"。
- 上界调整须走 PR 显式改常量（棘轮机械化，不靠自觉）。
- **实施顺序：KD4 改完 CLAUDE.md 后再取 KD3 上界数值**（critic R1-P2，防 KD4 的调度表修正
  使 CLAUDE.md 字节数变化后上界表落笔即错）。

### KD4 · 占位 skill 处置（P2）

- 先盘点两个 skill 正文与全仓引用（`grep -rn "skills/common\|skills/system\|system-rule-init\|
  system-memory-distill\|common-skills\|system-skills"`——含 frontmatter 注册名变体，
  critic R1-P2；范围含 CLAUDE.md 调度表与 server 侧）。
- `common/`（406B"通用审核能力分组"）：无实际内容且无代码引用 → 删除目录；CLAUDE.md 若有
  提及改为直述。
- `system/`（273B"制度与规则管理分组"）：CLAUDE.md 的 system 域调度入口写的是
  `system-rule-init` / `system-memory-distill`（实体是 init-rules / distill-memory 两个
  command）→ 把 CLAUDE.md 调度表改为直接引用两个 command 名，删除 system skill 空壳。
- 若盘点发现实际消费者（如 server 侧按 skill 名注入），改为保留但充实一段真实路由内容——
  以盘点结果为准，二选一，不留空壳。
- AC 判据：`grep` 悬空引用 = 0；生产 agent 系统提示注入面（CLAUDE.md）语义不变。

## T0 · 收益基线（推荐，环境允许时）

impl 开工前在可调模型的环境（部署机/本机）跑一次 D1 eval 回归闸 golden 集，锁三个数：
score_consistency 跨次极差、manual 项占比、契约重试率。重构合并后同集复跑对比。
**本 sprint 的 AC 不依赖该对比结果**（纯搬家不承诺行为提升），数据用于决定是否推广到
expense 域。环境不允许时显式记 defer，不阻塞。

## 影响范围

```text
.claude/commands/tender-evaluate.md          KD1 瘦身（38,754B → ≤15,000B）
.claude/skills/tender-eval/references/       KD1 新建 5 文件
.claude/contracts/common/audit-result.schema.json   KD2 pending_reason descriptions
.claude/contracts/tender/criteria.schema.json       KD2 tag descriptions
.claude/skills/tender-eval/SKILL.md          KD2 tag 段引用化
server/tender/output.py                      KD2 枚举改读 schema（行为不变；708 行基线越线，
                                             豁免沿用 H1 上界 720，本次净增 ≤5）
agent-front/.../types.ts                     KD2 权威指向注释（1 行）
tests/test_prompt_budget.py                  KD3 新建
.claude/CLAUDE.md                            KD4 调度表引用修正（若盘点需要）
.claude/skills/{common,system}/              KD4 删除或充实（盘点定）
tests/test_tender_pending_reason.py 等       行为锁定回归（预期零修改；如枚举读取路径需要
                                             fixture 调整，仅限测试装置不动断言）
```

## 已验证基线（2026-08-12 主 agent 实测）

- 文件字节：tender-evaluate.md 38,754 / tender-compare.md 7,132 / tender-extract-info.md 5,871 /
  audit.md 4,584 / CLAUDE.md 8,323（`wc -c`）。
- 全量测试收集 1,363；NO_NEW_FAILURES 口径（critic R1-F5 补自足性）：**开工第一步在自己的
  worktree 环境跑 `uv run pytest -q -p no:randomly 2>&1 | grep -E "^(FAILED|ERROR)" | sort >
  /tmp/baseline.txt` 存基线清单**（先例：H2/H3 同法；本机完整 venv 实测 16 条，均为
  Pillow/python-pptx 缺失的环境失败；worktree venv 未 sync 时会放大到 33，以**自己环境实测
  清单**为准），收尾同命令生成对比、diff 为空即过。
- output.py = 711 行实测（critic R1-P2 更正，H1 豁免上界 720 内，本 sprint 净增 ≤5）；
  worker.py=430 已用尽上界，**本 sprint 不得触碰 worker.py**（H1 pass2-N4 前置条件）。
- 确定性 Read 先例：tender-evaluate.md S1 行（`Read .claude/skills/tender-eval/references/
  s1-locate-criteria.md`）。

## 风险与缓解

- **搬家丢语义**是本 sprint 唯一大风险 → 附录 A 去向对账表 + reviewer 逐段核对 + AC2 的
  "全文内容 diff 守恒"检查（拼接骨架+references 后与原文逐规则比对，允许措辞衔接改动、
  禁止规则增删）。
- Read 增加时延 → 4 次 Read 约 +10-20s/单，已向用户说明并接受；契约重试率下降预计净正
  （T0/复跑验证）。
- 生产容器 `.claude/` 同步缺文件 → KD1 的 fail-visible 语义 + 部署 smoke 清单加一条
  "references 四文件存在性"。
- output.py 读 schema 引入启动时文件依赖 → schema 本就是部署必备物（同目录契约），启动即读
  失败=部署残缺，fail-fast 合理。

## 验收标准

- [ ] AC1 瘦身：`wc -c tender-evaluate.md` ≤ 15,000（逐节不超预算表）；S0-S4 骨架、决断总纲、
  输出契约核心、页锚简版、Read 指令齐全；**5** 个新 references 存在且各 ≤10,240B。
- [ ] AC2 零语义删改（critic R1-F2 换机械判据）：**containment 脚本核对**——把原
  tender-evaluate.md（eac2a16 版）非结构行归一化（去行首列表符/空白）后逐行 `grep -F` 到
  "新骨架+5 references 并集"；未命中行必须落在**显式白名单**（页锚简版替换行、pending_reason
  枚举语义迁 schema 行、纯衔接句），白名单随 evidence 提交供 review 核。附录 A 对账表降为
  辅助（bullet 级），不作唯一凭据。2026-08-12 三轮判分纪律修订（报价拆层/主观直接给分/
  一致性二分/留余地限定）逐条在新位置 grep 可命中。
- [ ] AC3 单源：两个 schema 的枚举带 description；output.py 枚举来自 schema（单测：篡改临时
  schema 副本枚举 → 校验行为随之变化）；prompt/SKILL.md 不再复述完整枚举语义；
  test_tender_pending_reason.py 11 条零修改全绿。
- [ ] AC4 预算门禁：test_prompt_budget.py 按上界表断言全绿；红证据 = 用临时超界文件（或
  对界前的 38KB 原文件路径）实测会红。
- [ ] AC5 skill 处置：盘点记录（引用清单）落 evidence；处置后 grep 悬空引用 = 0（含
  frontmatter 名变体）；CLAUDE.md 调度语义不变（system 域两个入口仍可路由）；**机械核对：
  CLAUDE.md 调度表提及的每个实体名都存在于 `.claude/commands/` 或 `.claude/skills/`**
  （critic R1-P2——现状 system-rule-init/system-memory-distill 即悬空名，此检查防复发，
  建议并入 test_prompt_budget.py 同文件）。
- [ ] AC6 质量门：完整环境 NO_NEW_FAILURES（16 条基线逐条 diff 为空）；ruff 净；前端仅
  types.ts 注释行、bun test 全绿；tdd-evidence 八字段（本 sprint 多为 backfill 形态——搬家
  无独立 red，按 doc-style backfill 记法写真实缺口证据；KD3 预算测试有真红绿）。
- [ ] AC7（可选，不阻塞）：T0 eval 基线已跑则记录三数字对比；未跑记 defer 与原因。

## 附录 A · 段落去向对账表（generator 开工首日先补全本表再动手）

以 2026-08-12 版 tender-evaluate.md（38,754B，commit eac2a16）为基准，逐段登记
`段落标识（行号+首句）→ 去向（骨架保留/references 文件名）`，作为 AC2 的核对底稿。
generator 补全后 review 按表核对。（设计阶段不预填——行号以实施时文件为准，防漂移。）

---

## Round 1 (initial draft by Fable 5)

四文件下沉 + schema 单源 + pytest 预算门禁 + 占位 skill 处置。

## Round 1 · Critic Findings

VERDICT: NEEDS_REVISION

- F1 [P0] 字节账算不拢：S1(9,039B)/S2 无去向，骨架 ~19KB>15KB 且 s3 按定义 9,607B>8,192B
  上界，AC1 与 AC2 联立无解。
- F2 [P1] 段落级对账表抓不住段内子条款丢失（generator 自填自证）。
- F3 [P1] pending_reason 枚举运行时不可达（"可保留简表"是漏洞），会推高重试率与动机相反。
- F4 [P1] output.py 模块加载期读 schema 与既有惰性 import 纪律冲突；tamper 测试机制未钉死；
  schema enum+description 已存在(6c766a5)应核对齐而非新增。
- F5 [P1] "16 条基线"对新会话 generator 不自足（无清单/命令/环境限定）。
- P2×6：单次 Read 回指 / output.py 711 / frontmatter 名变体 / CLAUDE.md 实体存在性机械核对 /
  KD3 取值次序 / 页锚双份权威标注。

## Round 2 (revised by Fable 5)

- F1 CLOSED：增第 5 个 reference s1-criteria-structuring.md；单文件上界放宽 ≤10,240B；
  新增逐节字节预算表（合计 ≤13,700，实测数支撑）。
- F2 CLOSED：AC2 换 containment 脚本机械核对 + 显式白名单，附录 A 降辅助。
- F3 CLOSED：s3 必须含枚举简表（权威=schema）；manual_review_reason 全文入 output-json.md。
- F4 CLOSED：钉死惰性首用+缓存、独立 loader 函数供 tamper 直测、路径走
  resolve_output_schema_path、禁 oneOf 重构；引 lazy-import learning。
- F5 CLOSED：基线改"generator 开工自测存清单"+完整命令+两种环境口径说明。
- P2 全部落实（Read 一次回指 / 711 / 变体 grep / 实体存在性核对并入预算测试 / KD4 先于
  KD3 取值 / 页锚权威标注）。
- 按用户 standing 偏好（2026-08-11"设计review不要反复"）不跑 Round 2 复核，修订均为对
  findings 的直接响应且字节账有实测支撑；实施期由 review 三件套兜底。
