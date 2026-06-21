# DESIGN · 第 2 轮：招标人侧招标文件合规审查（MVP）

> 对应 goal.md 三轮规划「第 2 轮」。基于 Explore 调研（招标人侧空白，基础设施可复用）。

## 一、背景
当前 tender 全部能力是**投标人侧评分**（/tender-evaluate、evaluator、extractor、compare）。招标人侧（审查招标文件本身是否合规）**完全空白**——`.claude/CLAUDE.md:42` "v1 仅评分评审；资格审查/程序合规留 v2"。用户决策"两侧并重"，本轮补招标人侧。

## 二、MVP scope（4 类 LLM 直读可做，对照法条）
| 审查项 | 法定依据 | 现状 |
|---|---|---|
| ① 隐蔽性排他条款识别（不合理资质/业绩/品牌/地域门槛）| 实施条例**第三十二条** | **规则缺失**，需新建 `tender_regulation_032` |
| ② 评标标准量化核查（因素量化、权重载明）| `tender_evalmethod_003/004` | ✅ 规则已有 |
| ③ 废标条款清单完整性（是否明列法定废标情形）| `tender_evalmethod_005/006` | ✅ 规则已有 |
| ④ 关键时限合规（公告期/投标截止距发售/投标有效期）| 实施条例第一/四章 | **规则缺失**，需新建时限 rule |

**划界（v3，需外部数据，不在本轮）**：三重一大集体决策、书面评标报告审查、倾向性打分识别（需 OA 系统 / 全部评标记录横比）。

## 三、方案（复用优先）
### 1. 新契约 `.claude/contracts/tender/doc-review-result.schema.json`（嵌 audit-result.extracted_data）
- `exclusionary_clauses[]`：`{id, clause_type(qualification|performance|brand|area|other), source_quote, source_ref, applicable_rule_id, severity(high|medium|low)}`
- `scoring_method_check`：`{method_legal, quantified, weights_specified, basis}`
- `rejection_clause_completeness`：`{listed[], missing[], basis}`
- `time_limit_checks[]`：`{item, required, actual, compliant, source_ref}`
- `qualification_conditions[]`：`{condition, is_proportionate, basis}`

### 2. 新命令 `/tender-doc-review`（招标人视角，~50 行）
Read 招标文件 → 对照通则层规则（评分量化/废标/保证金）+ 新建排他/时限规则 → 逐项核查 → 输出合规问题清单（符合 `audit-result` + `extracted_data.tender_doc_review`）。verdict：approved(合规) / rejected(实质违规如硬性排他) / manual_review(疑似/规则缺口)。排他条款一律"疑似"+引法条+人工复核，不下终局。

### 3. 后端 `POST /tender/projects/{id}/doc-review` + worker
抄 `tender_worker.py` 骨架（信号量/准入/超时/重试/OCR 注入全复用），换命令名 + 新 `DOC_REVIEW_OCR_PURPOSE`（重点还原资格要求/技术商务要求/评标量化规定/废标清单/关键时限）。挂 project_id，结论落 results。

### 4. 规则补充（本地 `knowledge/tender/`，gitignore 不入库）
- `tender_regulation_032`（排他条款）：源文件 `knowledge/external/招标投标法实施条例…md:18` 已有原文 → `/init-rules` 生成。
- 时限规则：条例第四章时限条款，需先补源文件再 `/init-rules`。

### 5. 复用清单（Explore 确认）
OCR purpose 链 ✅ / `tender_project_store`(挂 project_id) ✅ / `audit-result.schema` ✅ / `evidence_chain` ✅ / 任务状态机 ✅ / `SUBMISSION_DOMAINS["tender"]` ✅。

## 四、影响范围
- 新增：doc-review 契约、`/tender-doc-review` 命令、`tender_doc_review_worker.py`、端点、本地规则、测试。
- 改：`.claude/CLAUDE.md`（注册招标人侧 doc-review 入口段）。
- 角色分离 + 反馈深化 + 回归测试集 → 移第 3 轮（避免本轮 scope 爆炸）。

## 五、风险
- R1 规则 gitignore 不入库 → 提示词引 `tender_regulation_032` 但本地缺规则会被真伪闸拒。缓解：规则补充列为部署前置；缺规则降级 `manual_review(rule_gap)`，不编造。
- R2 排他条款识别主观 → 一律"疑似"+引法条+人工复核，不下终局（对齐 absence-is-not-zero 教训）。
- R3 scope 偏大 → 本轮只做 4 类直读项，外部数据项明确划 v3。

## 六、验收
1. `/tender-doc-review` 对一份招标文件输出 4 类核查；排他条款带 source_quote+rule_id+severity；时限核对表。
2. doc-review 契约校验单测 + 端点测试（含挂 project_id、跨租户）+ 命令冒烟。
3. codex design + impl review 无 P0。
