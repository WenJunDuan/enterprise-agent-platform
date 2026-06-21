# GOAL · 招投标审核 Harness 化重构（提示词工程 + 后端代码工程）

> 立项 2026-06-21。Path: System。
> 用户："把这个设为 goal，按 PACE 认真执行至少三轮，不执行完成不要结束，每次都要和 codex 配合执行。"
> 方法论：**Harness Engineering**（Agent = Model + Harness）—— 把"AI 怎么评标"固化成可执行、可约束、可评测的工程框架；模型供智商，Harness 供纪律。
> 本 goal 是既有 [评标扣分 G1/G2 goal](../2026-06-21-tender-scoring-goal/goal.md) 的**超集与深化**（G1 满分扣减 / G2 证据定位 已部分达成，本 goal 把"扣分"从 prompt 软约束升级为结构化 checklist + 反馈校验）。

## 一、用户诉求（本次原话提炼）

1. **扣分项没正常执行扣分** → 要求：**第一次看到标书就把招标内部的扣分项全部摘出来**（每项有几次扣分、一次扣多少分，这个数据必须找出来），再去应标书（投标文件）中**逐个核查命中、挨个扣分**，**扣分的地方要把上下文标记摘出来用于定位**。按满分 100 执行扣减。
2. **OCR 没目的性** → 评标时 OCR 只是单纯把文档转文本，没把"招投标评分要求/扣分项"带进去识别。
3. **.claude 提示词和后端代码"问题很多"** → 认真重构解析（提示词工程 + 后端代码工程）。
4. 参考用户提供的《招投标审核核心注意事项》（招标人/投标人双视角）+《Harness 思维方法论》。

**用户决策（2026-06-21 确认）**：审核视角 = **两侧并重**（投标人评分 + 招标人合规，分轮推进，见三轮规划）；扣分一致性校验 = **软校验 + 标记复核**（`score≠max−Σ扣` 仅警告并标 `manual_review` 候选，不打回重评，尊重区间打分制与"靠大模型判断"）。

## 二、现状诊断（实证 · 文件:行号）

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| D1 | 扣分**非结构化** | `criteria.schema.json` items 仅 `scoring_rule` 字符串，无扣分细则字段；`tender-evaluate.md:40` 靠 S3 临场从字符串解析扣分 | S3 易漏扣/扣不全 = 用户痛点 |
| D2 | OCR **无目的性** | `server/ocr/engine.py:212` prompt=`"Extract all visible document text"`，评标/报销共用通用提取 | 评分表/扣分细则表格行列易丢 |
| D3 | 提示词**不一致** | `agents/tender/evaluator.md:26` S3 仍是早期三态（无满分扣减/解耦/证据定位/结构化扣分），落后于 `tender-evaluate.md` | 走 agent 路径时退化 |
| D4 | **无反馈闭环** | `output_contracts` 仅校验 `0≤score≤max`，无 criteria 完整性 / 扣分覆盖 / score=max−Σ扣分 一致性校验 | 结论质量无机器把关 |
| D5 | 审核要点**未固化** | `knowledge/tender/` 仅 evalmethod+regulation 两通则；无负面清单/废标清单/双视角审核要点结构化规则 | 排他条款/废标项靠模型临场记忆 |
| D6 | 指令**非分层** | tender 走 command 加载**全** CLAUDE.md（含 expense/system）；`check-before-write.py` hook 默认关闭 | 上下文撑占、门禁形同虚设 |
| D7 | **缺招标人侧审核** | 系统只做投标人侧评分；无招标文件合规审查（排他/倾向条款、废标清单完整性、关键时限） | 双视角只覆盖一半（用户要两侧并重）|

## 三、Harness 五子系统 → tender 映射 + Gap

| 子系统 | 当前落点 | 本 goal 要补的 Gap |
|---|---|---|
| **指令 Instructions** | CLAUDE.md + tender-evaluate.md + 2 通则法规 | 扣分项结构化(D1) · evaluator 对齐(D3) · 负面/废标清单规则化(D5) · 分层加载(D6) |
| **工具 Tools** | Read/Glob/Skill/Task | 扣分核查 checklist · 分数加总校验 · (v2)外部资质核验 |
| **环境 Environment** | OCR_PREPROCESS/截断阈值 env | OCR 目的性注入(D2) · 法规/模型版本锁定追溯 |
| **状态 State** | results/tasks/projects + criteria 持久化 | 扣分项逐条核查状态 · 审核进度 checklist |
| **反馈 Feedback** | output_contracts(score≤max) | criteria 完整性 · 扣分覆盖 · score 一致性 · 回归测试集(D4) |

## 四、三轮 PACE 规划（每轮 design→impl→review→ship，每步 codex 配合）

- **第 1 轮（指令 + 反馈核心 · 直击用户最痛）**：
  1. 扣分结构化：`criteria.schema` 加 `deductions[]`（扣分情形/单次分/次数上限/出处）；S1 强制第一次读招标文件就提取全部扣分项；S3 `scoring[].deduction_hits[]` 逐条核查命中、摘上下文 quote + 页锚点；`score=max−Σ扣`。
  2. OCR 目的性：评标 OCR 注入"重点完整还原评分标准/评标办法/扣分细则表格"目的。
  3. evaluator.md 与 command 对齐（D3，DRY）。
  4. 反馈校验：扣分覆盖 + score=max−Σ扣 一致性（软校验/警告）。
- **第 2 轮（招标人侧合规 + 角色分离 + 反馈深化）**：**新增招标人侧能力（D7）**——招标文件合规审查（排他/倾向性条款识别、废标清单完整性、关键时限合规）+ 废标/负面清单结构化规则（D5）；角色分离（规划/执行/评估三权分立，"评估者≠执行者"）；一致性校验 + 回归测试集（golden 标）。
- **第 3 轮（环境 + 状态 + 收口）**：法规/模型版本锁定追溯；审核进度 checklist 持久化；绿/黄/红操作门禁；分层指令加载（D6）；architecture 更新 + polish。

## 五、验收标准（达标才收口）

- 用真实标：每个评分项的扣分项被**结构化列全**（S1 deductions），S3 命中处有 quote+页锚点，`score=max−Σ扣` 可核验，无漏扣。
- 反馈校验跑绿：扣分覆盖、score 一致性、criteria 完整性。
- 提示词无自相矛盾（evaluator≡command）。
- 三轮均有 codex 交叉 review 记录（reviews/codex-*.md）。
- 用户实测确认"扣分对了、定位对了"。

## 六、与 codex 配合方式

- **design 评审**：`codex exec "<审查指令>"` 读 design.md 出独立第二意见 → 写 `reviews/codex-design-r{N}.md`。
- **代码评审**：impl 后 `codex exec review` 跑 diff → 写 `reviews/codex-impl-r{N}.md`。
- codex 发现的 P0/P1 进 fix 清单，修完才进下一轮。

## 七、进度日志（每轮回写）

- **2026-06-21 前置即时修复（本会话，已完成验证）**：
  - ① 前端首页/标题跳转 `/`→`/contracts/tender-review`（app-title + header-breadcrumb）。
  - ② 删项目失效根因=前端"删除"只删投标任务不删项目+后端无删项目端点 → 补 `DELETE /tender/projects/{id}` 级联(store+route) + 前端 `deleteTenderProject` + 批量删除改删项目；空项目也能删。
  - ③ 清本地 256 测试项目（备份 logs/db-backups/，audit 113 行保留）。
  - 验证：后端 `test_tender_routes.py` 34 passed（+3 删项目测试）；前端 tsc exit 0。
- **2026-06-21 立 goal**：本文件 + 第 1 轮 design 起草。
- **2026-06-21 design 双评审（codex + CC critic）**：codex REWORK / critic NEEDS_REVISION，**核心一致**——评分不能只有扣减制，需多 `score_mode` + 废标独立 gate（否则档次分被伪扣分）。design 升级 v2 吸收全部 P0/P1（见 reviews/codex-design-r1.md、cc-critic-design-r1.md）。用户确认：两侧并重 + 软校验。
- **2026-06-21 第 1 轮 impl 完成（待 codex 代码 review）**：5 块全落地——①`criteria.schema` v2（score_mode 6 模式 + deductions/bands/awards + rejection_rules，向后兼容）②`output_contracts._verify_score_mode_consistency` 按 mode 软校验 + validation_warnings（不阻断）③OCR purpose 全链透传（engine/pipeline/tender_worker）+ audit 隔离 ④`compute_criteria_hash` 规范化防 v2 字段漂移 ⑤tender-evaluate.md S1 多模式提取 / S3 按 mode 判分 + 废标 gate / S4 verdict 由 gate + evaluator.md 对齐（消 D3）。**全量 435 passed + ruff 通过**。
- **2026-06-21 codex 代码 review（REWORK→全修）**：codex 抓 5 P1 + 3 P2——删项目漏 guard `accepted`/active compare（孤儿竞态）、cloud purpose 与 design 不一致、score_mode 缺失无兜底、缺 criteria 完整性校验、hash 未补默认、evaluator 输出形状滞后。**全部修复 + 补 7 测试**（accepted/compare 删除守卫、缺 score_mode/容器告警、默认值 hash 兼容）。见 reviews/codex-impl-r1.md。**440 passed/ruff**。**第 1 轮 ship**（commit 06bad53 + 即时修复 455e7a7）。
- **2026-06-21 第 2 轮 design 就绪（design-r2.md）**：招标人侧招标文件合规审查 MVP（隐蔽性排他条款/评分量化/废标清单完整性/关键时限，对照法条 LLM 直读）；外部数据项（三重一大/书面评标报告/倾向打分）划 v3。复用 OCR purpose/project_store/audit-result/evidence_chain。**用户选「先实测第 1 轮再开第 2 轮 impl」**——第 2 轮待实测反馈启动。
