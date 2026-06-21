# DESIGN · 第 1 轮（v2 · codex REWORK 后重构）

> v1 被 codex 评为 REWORK（见 reviews/codex-design-r1.md）：核心缺陷=评分模型只有"扣减制"，无法覆盖档次/加分/公式/通过否/主观分，且废标应独立 gate。v2 据此重构。
> 用户决策：审核视角两侧并重（第1轮先投标人侧）；扣分校验软校验+标记复核。

## 一、背景与根因

用户痛点"扣分没正常执行"的**真正根因**不止"扣分非结构化"，更深一层是 **评分模型单一**：现状把所有 `scored` 项当"从满分扣减"，但真实评标办法里——
- 技术/服务方案：**档次给分**（优10/良7/中4），那个 7 分不是"扣 3 分"；
- 价格分：**公式分**（最低价/本价×权重），需横比；
- 资质/业绩：**加分累计**（每项+X 封顶）或**客观通过/不得分**；
- 废标/资格不符：**投标有效性 gate**，不是某评分项的扣分。

只有把"评分模式"分清，扣减项才会被正常扣、档次项才不会被伪扣分。这是第1轮地基。

## 二、核心模型：评分多模式 `score_mode`

`criteria.items[]` 每项显式声明 `score_mode` + `evaluator_type`，并带对应规则容器：

| score_mode | 适用 | 规则容器（criteria 侧） | 判分明细（scoring 侧） |
|---|---|---|---|
| `deduction` | 满分扣减（响应度/瑕疵） | `deductions[]` | `deduction_hits[]`，score=max−Σdeducted |
| `banded` | 档次给分（优良中） | `bands[]`={level,points,criteria,source_quote} | `selected_band`={level,points,reason} |
| `additive` | 基础分+加分累计 | `base` + `awards[]`={id,condition,points,cap} | `award_hits[]`，score=base+Σawarded |
| `formula` | 公式分（价格等） | `formula`(原文) | `formula_inputs`（本家钉 bid_price）+ 多为 manual 待横比 |
| `pass_fail` | 客观通过/不得分 | `scoring_rule` | score=max 或 0，basis 写命中 |
| `manual` | 主观/现场/外部/横比不可判定 | `scoring_rule` | score=null, status=manual_review |

`evaluator_type`: `objective` | `subjective` | `mixed`——**主观档次项默认 `review_required`**（输出建议分+依据，但带低置信 warning，提示人工复核）。

### deductions 增强（吸收 codex P1.5，第1轮做基础字段，高级留余量）
`deductions[]` 每条：`{id, condition, source_quote, points, unit(per_item|per_occurrence|per_percent), max_times|null, max_deduct|null, source_ref}`。
`deduction_hits[]` 每条：`{deduction_id(回链), condition, points_each, times, deducted, evidence{source(文件+第N页+章节), quote(触发扣分的投标原文片段)}}`。
（互斥组 `mutual_exclusion_group` / `severity_levels` / `min_score` 标注为"第2轮深化"，第1轮 schema 预留可选位但不强制。）

**加分项 max 语义（critic F3）**：`additive` 项的 `max` 必须是**含加分封顶的该项最高分**，确保 `score=base+Σawarded ≤ max` 恒成立，不触发既有 `score>max` 硬闸（output_contracts.py:265）；每个 award 带 `cap`。

## 三、废标 / 资格 独立 gate（吸收 codex P0-3）

`extracted_data` 增加（与逐项 scoring **解耦**）：
- `rejection_rules[]`：从招标文件提取的废标/否决条款 `{id, condition, source_quote, source_ref}`。
- `eligibility_checks[]`：资格审查项 `{check, basis, status(pass|fail|manual), evidence}`。
- `disqualification_hits[]`：命中的废标 `{rule_id, finding, evidence{source,quote}}`。
- **verdict 逻辑**：任一 `disqualification_hit` 或 `eligibility` fail → `rejected`（gate 决定）；**但逐项 `scoring` 仍保留有扣有得的明细**（延续既有解耦原则）。串通/异常低价澄清失败等 v1 仅标注，结构化识别留第2轮。

## 四、OCR 目的性（显式 purpose 参数链 · 吸收 codex P2-8）

- **完整透传链**（critic F2 核实实际调用栈，每层加 `purpose: str|None=None`）：`tender_worker` → `pipeline.ocr_preprocess_block` → `extract_dir` → `extract_one` → `_recognize_with_seal` → `engine.recognize` → `_recognize_via_openai_compatible`/`_call_openai_compatible_vlm`；**cloud 路径**（`OCR_CLOUD=1` 的 `_recognize_via_paddle_cloud`）接受 purpose 参数以统一调用链，但 **aistudio job API 服务端固定版面 OCR、不接受自定义 prompt → purpose 对 cloud 暂不生效（已知限制，docstring 标注）**；生产若依赖 cloud 还原评分表，需待云服务支持识别提示或评估改用 OpenAI-compatible 路径。
- purpose 拼进逐页 prompt（在 `"Extract all visible document text..."` 后追加）。
- `tender_worker` 评标传 `TENDER_OCR_PURPOSE`="本批为招投标评标材料，请完整、结构化地还原评分标准/评标办法/扣分细则/废标条款等表格，保留表格行列与分值数字，勿合并或省略行"。
- **audit / `/ocr/extract` / `/ocr/fill` / CLI 默认 `purpose=None`**，保持通用提取；加回归测试断言 audit 链路 prompt **不含** tender 文案（防污染）。

## 五、反馈校验（按 mode 软校验 + warning 路径 · 吸收 codex P0-2/P1-7）

- 新增 `extracted_data.validation_warnings[]`（`{code, item, detail}`），**不抛错、不阻断**，经 result 端点可读（反馈闭环可观测）。
- **挂载点（critic F4，对齐 compound/decision-verification-gate）**：新校验函数 `_verify_score_mode_consistency` 放 `output_contracts._validate_audit_result` 内、**紧跟 `_verify_scoring_consistency`**（第 222 行后），不在 `normalize_audit_result` 前，避免 schema 硬校验前误拦。
- 按 `score_mode` 分别一致性校验（不一致→warning，不打回）：
  - `deduction`: |score−(max−Σdeducted)|≤0.01
  - `banded`: score==selected_band.points
  - `additive`: |score−(base+Σawarded)|≤0.01
  - `formula`/`manual`/横比: 仅范围校验 0≤score≤max
- 保留既有硬闸 `0≤score≤max`（抛错，防量纲错乱）。
- criteria 完整性软校验：items 非空、各 mode 容器与 score_mode 匹配（如 deduction 项有 deductions）。

## 六、契约 schema 显式加字段 + hash 兼容（吸收 codex P1-6）

- `criteria.schema.json` item 是 `additionalProperties:false` → **必须显式加** score_mode/evaluator_type/deductions/bands/awards/base/formula 等（否则模型输出被契约拒）。新字段除 score_mode 外尽量可选，向后兼容旧 criteria。
- `audit-result.schema.json` 的 scoring/extracted_data 是 `additionalProperties:true`，新明细字段无需改 schema，靠 prompt 约定。
- `compute_criteria_hash(crit)` 前**规范化**：缺失的可选字段补默认（deductions→[]、evaluator_type→objective 等），防新旧投标人 criteria 因字段有无导致 hash 漂移、破坏横比。

## 七、提示词改动

- `tender-evaluate.md` **S1**：识别每个评分项的 `score_mode`（扣减/档次/加分/公式/通过否/主观）+ `evaluator_type`，按 mode 提取对应容器（扣减项提 `deductions` 含每条扣几分/几次/出处原文；档次项提 `bands`；加分项提 `awards`；公式项提 `formula`）；并把废标/资格条款提进 `rejection_rules`/`eligibility_checks`。这是"第一次读标书把扣分项/评分规则全摘出来"的落点。
- **S3**：按 `score_mode` 判分（扣减→deduction_hits 摘上下文；档次→selected_band；加分→award_hits；公式→manual 待横比）；废标走 gate（disqualification_hits / eligibility）。
- **命令第 6 行**同步 OCR 语义（"若服务端注入 OCR/直读底稿则优先使用，必要时回读原文件核验"，治 codex P2-9 矛盾）。
- `agents/tender/evaluator.md` 同步对齐（消除 D3 滞后）。

## 八、影响范围
- 契约：`criteria.schema.json`（显式加字段）。
- 提示词：`tender-evaluate.md`、`agents/tender/evaluator.md`。
- 后端：`ocr/engine.py`、`ocr/pipeline.py`、`routes/tender_worker.py`、`common/output_contracts.py`、`stores/tender_compare_store.py`(compute_criteria_hash 规范化)。
- 测试：criteria 各 mode 契约、废标 gate、OCR purpose 透传+audit 隔离、按 mode 软校验、criteria_hash 兼容。

## 九、风险与缓解
- R1 scope 偏大 → 第1轮只做 5 个 mode 框架 + gate 基础；additive 互斥组/severity/串通识别留第2轮（design 已标注）。
- R2 schema 改动破坏旧回看 → 除 score_mode 外新字段可选；旧 criteria 缺 score_mode 时校验层按 deduction 兜底+warning。
- R3 criteria_hash 漂移破坏横比 → 规范化后再 hash（专项单测）。
- R4 OCR purpose 污染 audit → 显式参数默认 None + audit 隔离回归测试。
- R5 prompt 变长 → S1/S3 用 mode 表格精炼表达，不逐 mode 堆叙述。

## 十、验收标准
1. 含多种评分形态的真实标：每项 `score_mode` 识别正确；扣减项 deduction_hits 带 quote+页且 score=max−Σ扣；档次项 selected_band 不被伪扣分；废标走 gate 而非清零各项。
2. 按 mode 软校验单测（一致/不一致）+ **skip 路径不误报（critic F5）**：① score=null/manual_review 不触发；② scored 但无 deduction_hits 不触发；③ banded/additive 一致不报；OCR purpose 透传（OpenAI-compatible 路径）+audit 隔离单测（cloud purpose 为已知 API 限制，不在第1轮验收）；criteria_hash 兼容单测（含默认值归一）；各 mode criteria 契约单测——全绿。
3. `evaluator.md` ≡ `tender-evaluate.md`（无评分逻辑分叉）。
4. codex 复审 design v2 + impl 无 P0；CC critic 无 P0。
