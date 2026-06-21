# R2 设计 · 扣分项准确 + 上下文定位与显示（核心）

> Sprint 2026-06-22 · Round 2/6 · Path: System（prompt/契约 + 后端 + 前端）
> 用户核心诉求原话：「最核心还是招投标审核的数据准确和扣分项的准确，上下文的定位和显示」

## 背景（WHY）
R1 解决了「招标侧」评分标准抽取与展示。R2 解决「投标侧」评判质量：
1. **扣分项准确**：每个 deduction-mode 项的 `deduction_hits` 逐条命中 + `points` + `basis`，不笼统"扣X分"。
2. **上下文定位准确**：`evidence_chain` / 每条 `basis` 引用的 `【第N页】` 必须**真的**含所述内容（治"凭印象写页码"）；投标人/报价/业绩/资质对应到正确出处页。
3. **一致性风险**：拟派项目负责人 vs 业绩项目经理不一致 → data_conflict，证据链同引两处。
4. **显示**：分析中心区3「证据与底稿」点评分项跳对应出处；扣分明细（deduction_hits）可见。

## 现状（待基线评估确认）
- 评判逻辑在 `.claude/commands/tender-evaluate.md` S2/S3（已较完整，含 absence-not-zero、formula G5、独立废标 gate、证据定位硬要求）。
- 前端 `model.ts`：scoringItems ← `extracted_data.scoring`（item.basis/max/score）；paragraphs ← `evidence_chain`；scoring[].loc → paragraphs（点评分项跳证据）。deduction_hits **是否在前端展示待查**。
- **R2 先跑全量评标基线（3 模型）量化现状**，再定准改什么——避免凭空改 prompt。

## 方案（HOW）— 待基线后细化
1. **基线评估**（本设计先行动作）：dogfood 案（华为南通 + 烛照投标）全量评标，3 模型各一遍，量化：
   scoring 项数 / 有 deduction_hits 的项数 / 有 evidence.source 出处的项数 / manual_review 项数 / verdict / 证据页码可核验率（抽样核对引用页是否真含所述内容）。
2. 据基线找最弱环节，按以下候选改（择优）：
   - prompt：强化 deduction_hits 逐条 + evidence quote 摘原文 + 页码自检（命令已有，看是否需加硬化/示例）。
   - 契约：scoring[].deduction_hits / evidence 结构是否需更严（让前端能稳定展示）。
   - 前端：区3 扣分明细展示（deduction_hits 列表 + 命中 quote + 出处页）、点评分项精确定位证据段。
3. **不可判定绝不判 0** 回归（absence-not-zero）保持。

## 影响范围（预估，基线后定）
- `.claude/commands/tender-evaluate.md`（S2/S3 强化）、可能 `.claude/contracts/tender/extract-result.schema.json`。
- 前端 `model.ts` + `analysis-workbench-view.tsx`（区3 扣分/证据展示）。

## 风险与缓解
- 全量评标慢（225-537s/模型）+ opus 429 → 基线用 deepseek/qwen 为主，opus 尽力。
- prompt 改动可能回归其他案 → 改后同案 3 模型回归对比 verdict/scoring 不劣化。

## 验收标准（基线后锁定具体数值目标）
1. 扣分项：deduction-mode 项的 deduction_hits 非空率↑、每条带 points+evidence.quote。
2. 证据定位：抽样核对引用 `【第N页】` 真含所述内容（人工/脚本抽查）。
3. 前端：区3 能看到逐条扣分 + 命中原文 + 出处页。
4. 3 模型回归：verdict 稳定（投错标仍 rejected）、scoring 不劣化、tests+lint+build 绿。

## 基线发现（2026-06-22，进行中）

**三个关键发现：**
1. **前端丢弃 deduction_hits/evidence**（`model.ts buildScoringItems` 只取 `{item,max,score,status,basis}`；`buildCategories` 建 ReviewItem 也不带逐条扣分）→ 分析中心只能显单个"扣X分"数，看不到"哪条命中/扣几分/原文 quote/出处页"。**确认的展示缺口**。
2. **存量评标结果的 scoring 项只有 `{item,max,score,status}`** —— 无 deduction_hits / basis / evidence / score_mode（近 30 条一致）。已排除 normalize 剥离（`enrich_audit_decision` 不碰 scoring，仅动 reasons/policy_refs/risk_dimensions）→ 说明**模型未稳定产出逐项扣分细则**（或存量为旧 prompt 数据）。**这正是用户"扣分项准确/上下文定位"的核心缺口**。⚠ 待当前 qwen 全量评标确认现行命令是否产出 deduction_hits（不可据旧数据下结论）。
3. **deepseek 全量评标不可靠**：输出漏 audit-result 必填 `reasons` → 契约重试 3 次 → ~15min 仍未过，已 kill。（对比 R1：deepseek 抽 criteria 最佳——任务不同：全量 audit-result 字段多，deepseek 丢 reasons。）qwen 历史可靠（goal 记 20 项 scoring）。

**R2 改进方向（待 qwen 确认后定）：**
- 若现行命令仍不稳定产 deduction_hits → 硬化 `tender-evaluate.md` S3/输出契约：deduction-mode 项**必须**逐条 deduction_hits（condition/points/evidence.quote/出处页），加输出自检/示例；可能给 scoring 项补轻量结构校验（产出率↑）。
- 前端：model.ts 透传 deduction_hits + evidence → 区3 ReviewItemCard 展开显逐条扣分 + 命中原文 + 出处页（治"上下文定位与显示"）。
- deepseek reasons 缺失：评估是否在 audit-result normalize 兜底（explanation→reasons 派生）或仅命令侧强化（不弱化承重闸）。

## 基线结果（3 模型）
- qwen：_running（确认 deduction_hits 产出 + 扣分/evidence 质量）_
- deepseek：❌ 全量评标 3 次契约重试(漏 reasons)，不可靠，已 kill
- opus：_pending（anyrouter 429 风险）_
