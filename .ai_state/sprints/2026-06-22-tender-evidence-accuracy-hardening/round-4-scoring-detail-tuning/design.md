# R4 设计 · 扣分明细完整性 + 调优（R7-a / G5 reconciliation）

> Sprint `2026-06-22-...` · Round 4 · 路径 **Feature（小增量）**
> 行号 2026-06-22 实测。

## 一、grounding 纠偏（先读，重要）

用现有缓存 dogfood 结果（R2 跑的二建 qwen+deepseek 全量 scoring）实测分析，发现 R4 原计划与素材不匹配：

1. **R2024-007 评标办法无 deduction-mode 项**：实测 scoring 全是 `banded`（技术档次）/ `formula`（价格=基准价横比、信用=外部数据，均 cross-bid/external→manual_review）/ `pass_fail`(业绩) / `additive` / `manual`(deepseek 把技术拆 6 子项)。**deduction_hits=0 across the board** → 「扣分项命中/明细准确度」(R7-a) **在本标无法实测/调优**（本标不是满分扣减制）。
2. **G5 限价类 formula 本标也没有**：价格分是综合评估法基准价（需横比），非「低于控制价按 %扣分」的单家可算限价类 → 两 formula 项正确判 manual_review，无 formula_spec（正确）。**G5 限价类在本标无素材**。
3. **G5 校验层兜底其实已存在**（上轮）：`_verify_score_mode_consistency`（`output_contracts.py:464-499`）已对 formula 判 scored 缺 spec/含横比变量/缺 value 发 warning（`formula_scored_no_spec` 等）。**G5 backstop 已完成**，缺的只是 S2 抽取（prompt 已要求 `tender-evaluate.md:24,47`）。
4. **一致性风险已工作**：deepseek 实测 evidence_chain 抓到「业绩项目经理顾海曙 ≠ 拟派负责人牛亚犇」→ 业绩判 0（两模型一致），符合 CLAUDE.md data_conflict 规则。

**结论**：R4 原定「扣分准确度 + G5」大部分**已完成或无素材可调**。诚实保留的**真实可做增量** = 堵一个现存明细完整性漏洞（下）。

## 二、真实增量：scoring 明细完整性校验（治"笼统扣X分无明细"）

**漏洞**：`_verify_score_mode_consistency` 用 `_sum_hit_field`（`:365`），deduction_hits **为空时返 None → 整项跳过**。于是 deduction 项 `status:scored, score<max` 却**无任何 deduction_hits 明细**（笼统"扣2分"不给逐条依据）**静默通过**——违命令「已识别的每个问题点都要落成 deduction_hits，禁止笼统扣X分」（`tender-evaluate.md:53`）。additive 同理（score>base 无 award_hits）。

**修法**（warning，不 raise/不降级，对齐既有 `validation_warnings` 软提示风格，尊重区间打分 + 不打回重评 R4-D）：在 `_verify_score_mode_consistency` 加：
- `deduction` + `status=scored` + `score < max` + `deduction_hits` 空 → warning `deduction_scored_no_hits`（"扣分但无逐条明细，疑笼统扣分，请人工核验扣分依据"）。
- `additive` + `status=scored` + `score > base` + `award_hits` 空 → warning `additive_scored_no_awards`。
- 边界：score==max（deduction 满分不扣，无 hits 合法）/ score==base（additive 无加分合法）→ 不告警。null/manual_review/banded/formula/pass_fail → 不适用。

## 三、影响范围
| 文件 | 改动 |
|---|---|
| `server/common/output_contracts.py` | `_verify_score_mode_consistency` 加 2 个明细完整性 warning 分支 |
| `tests/test_tender_*` 或 `test_contract_registry.py` | 加：deduction score<max 无 hits→warning；满分无 hits 不告警；additive 加分无 awards→warning；有 hits 正常不告警 |

**不改**：G5 formula backstop（已存在）；评分判定（仍模型职责）；不 raise（不触发 290s 重评）。

## 四、风险与缓解
| 风险 | 缓解 |
|---|---|
| 误告警（满分项无 hits 合法） | 仅 `score < max`(deduction)/`score > base`(additive) 才告警；满分/无加分不告警 |
| warning 无人消费 | 进 `extracted_data.validation_warnings`（既有通道，前端/人工可见，与现有 warnings 一致） |
| 影响 audit | audit 无 scoring → 该函数对 audit no-op（已有保护） |

## 五、验收
1. 单测：deduction scored score<max 无 hits→`deduction_scored_no_hits`；deduction 满分无 hits→无告警；additive score>base 无 awards→`additive_scored_no_awards`；有完整 hits 且算术自洽→无新告警；manual_review/banded 不触发。
2. 回归 `pytest -q` 全绿 + ruff。
3. R2024-007 回归：现有 dogfood 行为不变（本标无 deduction 项 → 不新增告警）。

## 六、实施（TDD）：测试红 → 实现 2 分支 → 回归 → commit。

## 七、设计审查记录
小增量（warning-only，2 分支），低风险；跨轮最终自查（bug-hunt）统一覆盖，未单跑 critic+codex。

## 八、自测结果（2026-06-22）
- 单测 +5（test_contract_registry.py）：deduction 部分扣分无 hits→`deduction_scored_no_hits`；满分无 hits 不告警；有 hits 自洽不告警；additive score>base 无 awards→`additive_scored_no_awards`；manual_review 不触发。全绿。
- 回归 `pytest -q` **677 全绿** + ruff clean。
- score==0 不重复告警（由既有 absence `scored_zero_suspect` 覆盖，本增量限 `0<score<max`）。
- R2024-007 回归：本标无 deduction 项 → 不新增告警，dogfood 行为不变。

## 九、进度回写（2026-06-22）
- **grounding 关键发现**：R2024-007 评标办法是 banded/formula(cross-bid)/pass_fail/manual，**无 deduction-mode、无限价类 formula** → 「扣分命中准确度」(R7-a) 与 G5 限价**在本标无素材可实测/调优**；G5 formula 校验层兜底 + 一致性风险(业绩经理≠拟派PM)**上轮已具备且实测工作**。
- **真实增量**：堵 `_verify_score_mode_consistency` 的明细完整性漏洞（笼统扣X分/加分无明细 → warning）。
- **Followup**：扣分命中/限价 formula 的真实调优需「满分扣减制 + 限价价格分」的标作素材（R2024-007 不是）→ backlog。
