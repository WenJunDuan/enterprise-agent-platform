# Phase 0 · 评标回归闸（先造尺子）— design

> 施工依据：`.ai_state/claude/tender评标链路改造设计-施工文档.md` 第二节（Phase 0）。
> 本 sprint 只做 Phase 0；纪律见施工文档第九节，逐条抄进 plan.md 头部。
> 改动范围白名单：**新增 `eval/`、新增 `scripts/eval_tender_regression.py`**；
> 白名单外唯一例外见「守卫扩面」节，需用户点头。**不触碰 `server/tender/` 任何文件。**

## 背景

三轮实测（2026-08-18）证明：链路改动的好坏一直靠感觉裁决，且感觉已被证伪过两次
（"OCR 闸从不触发"= awk 字节计数错误；"检索 unresolved=0 ⇒ 块为空"= 把命中当命中证据）。
现有验收量纲只有测试数与逐名回归，**没有任何一个指标衡量"评标准不准"**。
Phase 0 交付四指标评测闸，此后每一刀由数字裁决。

## 已调研的现成方案

| 候选 | 判定 |
|---|---|
| promptfoo / deepeval / ragas 等 LLM eval 框架 | **否决**。核心指标（跨文件缺陷召回、客观分逐项比对）是业务金标准逐项比对，不是 LLM-judge 语义评分；引入框架带 node/依赖面，与内网单机分发形态冲突；且四指标里两个（墙钟、manual_review 数）直接读任务表即可 |
| pytest 参数化跑评测 | **否决**。评测要打真模型（$1.1–2.5/单、3–14 分钟），进 pytest 会被当回归误跑；且输出是对比表不是断言 |
| **沿用仓库 `scripts/measure_*.py` 形态自研薄脚本** | **采用**。已有 `measure_tender_recall.py`/`measure_tender_evidence.py` 先例，零新依赖，单文件可拷到部署机 |

## 方案

### 1. 金标准案例库 `eval/golden/`

```
eval/golden/case-zj-live/          # ZJ直播间标（匿名代号，不含真名）
  ├── expected.yaml                # 匿名化期望（见下）
  └── corpus.pointer.yaml          # 语料指针：相对 knowledge/external/ 的路径 + sha256 + 页数
```

**匿名化方案（与 `tests/test_no_real_corpus.py` 机械守卫共存的唯一办法）**：

- 真实语料（招标 .doc + 投标 400 页 PDF）**留在 `knowledge/external/`**（已 gitignore，不入库）。
- `expected.yaml` 全部用**角色代号 + 页锚 + 缺陷类别枚举**表述，不含任何组织/人名真名：
  ```yaml
  defects:                          # 必须召回的缺陷（源自 2026-08-17 参照实跑）
    - id: D1
      class: cross_doc_contradiction   # 类别枚举，匹配键之一
      role: 投标人中小企业声明函 vs 制造商中小企业声明函
      anchors: ["【第N1页】", "【第N2页】"]   # 页锚为主匹配键
      severity: P0
    - id: D2
      class: spec_basis_mismatch       # 检测报告依据标准与参数错配
      ...
  objective_scores:                 # 客观分基线（企业实力 6/6、业绩 9/9、负责人 3/3）
    - {item_class: 企业实力, expected: 6, max: 6}
    ...
  price_check: {total: 1316033.66, expect: pass}
  ```
- `corpus.pointer.yaml` 记 sha256：语料被换/漂移时评测显式报错，不静默测错对象。
- 语料缺席（如 CI）→ 脚本**显式 SKIP 并打印原因**，不产出假通过。

### 2. 评测脚本 `scripts/eval_tender_regression.py`

- 入参：`--case case-zj-live --mode single[,itemized] --backend http://…:9999 [--repeat 3]`
- 执行：走现有 HTTP 面（建项目→传招标→等 criteria ready→传投标→评标→取结论），
  **不 import `server/tender/` 内部**——评测对象是端到端行为，绕过 HTTP 就测不到准入闸/超时这层。
- 四指标计算式（机械可复跑，无自由裁量）：
  | 指标 | 计算 |
  |---|---|
  | 墙钟 | `finished_at − submitted_at`（含重试；`--repeat 3` 取中位） |
  | manual_review 项数 | `scoring[] 中 score=null 计数`（按 pending_reason 分列，`cross_bid`/`live_event` 单列——它们是正确待人工，不该计入劣化） |
  | 跨文件缺陷召回率 | expected.defects 命中数/总数；命中 = 结论任一 finding 的页锚 ∩ defect.anchors ≠ ∅ **且** 类别枚举一致（双键都中才算，防蒙对） |
  | 客观分准确率 | expected.objective_scores 与 `scoring[]` 逐项比对（item 匹配用 item_class 关键词族，不用全名精确匹配——模型输出项名有措辞漂移） |
- 输出：单表（markdown），双模式并列 + 与附录 B 基线的差值列。

### 3. 基线回填

single 路径 `--repeat 3` 跑ZJ case，四指标中位数**写进施工文档附录 B**。
成本预算：~$1.4/跑 × 3 ≈ $4.2（deepseek flash，参照 08-18 实测单价 $1.1–2.5）。

### 守卫扩面（白名单外唯一例外，需用户点头）

`tests/test_no_real_corpus.py` 现扫描面不含 `eval/`。本 sprint 把 `eval/` 纳入扫描
（一行路径增补），否则匿名化纪律对新目录无机械保障——守卫覆盖不到的纪律等于没有。

## 影响范围

新增 `eval/golden/case-zj-live/`（2 个 yaml）、`scripts/eval_tender_regression.py`；
`tests/test_no_real_corpus.py` +1 行扫描路径（需点头）。**server/ 零改动，提示词零改动。**

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 单 case 过拟合（n=1） | 指标表头永久标注 n；每遇真实标沉淀新 case（施工文档已定此工作流）；**禁止**为让ZJ case 通过而调链路参数——那是本闸要终结的行为本身 |
| 墙钟受 API 波动 | `--repeat 3` 取中位；表中附极差 |
| 缺陷"命中"判定被钻空子 | 双键（页锚∩ + 类别枚举）皆中才算；匹配逻辑本身有单测（不打模型，纯函数） |
| 客观分项名措辞漂移 | item_class 关键词族匹配 + 匹配失败显式列"未匹配项"，不静默算 0 |
| 部署机没有ZJ语料 | pointer 的 sha256 校验先行；`--backend` 指向本地 `uv run python -m server.cli serve` 亦可（.env 已有 deepseek key） |

## 验收标准

1. `uv run python scripts/eval_tender_regression.py --case case-zj-live --mode single --backend …` 一键产出四指标表
2. `expected.yaml`/`corpus.pointer.yaml` 通过扩面后的 `test_no_real_corpus.py`
3. 缺陷/客观分匹配逻辑有纯函数单测（不打模型）；测试总数 ≥ 基线 1,672 + 新增数
4. 施工文档附录 B 四指标全部回填（single，n=3 中位 + 极差）
5. 本 sprint diff 仅落在白名单 + 守卫扩面一行

## 前置处置（本 design 之外、开工前完成）

- P0 worktree（五项护栏，已提交）：补 tdd-evidence + 全量回归后**先合入**——P0.5 的
  total_score 服务端汇总正是本脚本"客观分准确率"要读的字段；基线只测一次。
  此为对"Phase 0 前禁碰链路代码"的一次明示偏离，用户可否决改为挂起。
- P0.6 worktree（criteria 回显抑制，未提交）：**冻结不合入**，worktree 保留。
  Phase 2 小契约天然消解回显；旧路径是否单独抑制，Phase 0 出尺子后数字再议。

## 施工文档的三处前提更新（不改架构，改依据，随本 sprint 记档）

1. "OCR 闸从不触发"系错误测量（awk 字节计中文膨胀 3 倍）；实测闸会触发（59/107 空白页）。
   故 Phase 1 manifest 判定不变，但 **vision-page（公理 C）升权、"修 OCR 判据"降权**。
2. `bound_draft` 截断现为"转人工"非"出烂分"（08-18 (d) 修复），公理 B 违反点措辞更新。
3. criteria 回显占输出 60.4%（三份真实结论实测 61,828/102,443 字）——Phase 2 token 账的实证。

## 第八节两决策的落地形态（已按用户定调改写）

1. 模型路由 → **能力声明**：每 Phase 声明所需能力（agency/vision/输出量级/JSON 可靠性下限），
   部署侧映射模型；harness 不出现模型名（对齐 plan-2026-08-18-accuracy.md P2.5）。
2. 调用粒度：采纳文档建议，**先按 category 合批（≤30K/批）**，指标不达再拆细。
