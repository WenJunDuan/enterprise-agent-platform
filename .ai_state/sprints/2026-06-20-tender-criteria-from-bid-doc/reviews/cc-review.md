# CC (Claude) 交叉 Review — tender 评标改造（招标文件第三章直读出 criteria）

> Reviewer: Claude (主实现方自审，独立维度核对) · 区间: `13d58a7..d32a64c`（feat 21facde + docs d32a64c）
> 日期: 2026-06-20 · Path: System · 配套 codex-review.md（外部第二意见）

## VERDICT: **PASS（带 3 项 CONCERNS，均非阻塞）**

8 文件 /+321-46。pytest 309 passed、ruff clean、validate-assets ok。design §验收逐条满足；真伪闸对齐正确；statute/项目层清零。下列 CONCERNS 建议记 backlog 或随后续迭代消化，不构成 REWORK。

## 一、design 验收逐条核对

| 验收项 | 结论 | 证据 |
|---|---|---|
| ① S1 从招标文件第三章产出 `extracted_data.criteria` | ✅ 提示词层 | `tender-evaluate.md` S1 重写 + `criteria.schema.json` 新建 |
| ② 按 criteria 逐项 `scoring{item,max,score,status,basis}` | ✅ | S3 "对照 extracted_data.criteria 每一项…item/max 须与 criteria 一致" |
| ③ 不可判定项 `score:null` 不判 0 | ✅ | criteria `tag` 枚举 + S3 三类标签 + 测试 `test_unjudgeable_item_null_score_passes` |
| ④ policy_refs 引通则层真实 rule_id、criteria 命中在 evidence_chain | ✅ 已测 | S4 + evaluator + `test_audit_with_criteria_passes...` / `test_fabricated_project_layer_ref_rejected` |
| ⑤ verdict + 每项丢/得分原因 | ✅ | S4 verdict 合成 + scoring.basis |
| 无招标文件 → manual_review(rule_gap) 兜底 | ✅ 提示词层 | S1 护栏 + tender-eval SKILL 降级规则 |
| knowledge/tender 不再需 {招标编号}.rules.json；statute 清零 | ✅ 已验 | `grep statute .claude` = 0；通则层两法规未动 |
| pytest 全绿 + ruff + validate-assets | ✅ | 309 passed / clean / ok（5 规则文件） |

## 二、正确性 / 设计一致性

- **真伪闸对齐（最关键风险点）正确**：`output_contracts.py:203-218` 对 approved/rejected 强制 `policy_refs ⊆ known rule_id`。新流程 criteria 无 rule_id → 提示词明确"承重 policy_refs 只引通则层（tender_evalmethod_001/003/004 等真实 rule_id），criteria 命中走 evidence_chain"。`test_fabricated_project_layer_ref_rejected` 实证编造 `tender_r2024007_004` 被拒，守住 H1 反幻觉价值。✅
- **criteria 持久化路径正确**：`extracted_data` 为 `additionalProperties:true`，criteria 不被出口 schema 拒；随 `archive_result_payload` 落 SQLite `results.payload`（按 tenant+request_id，复用 H4 隔离）。零新 store/写权限。✅
- **口径一致**：CLAUDE.md / command / evaluator / tender-eval SKILL / rule-init SKILL 五处指向"通则层法规 + 招标文件第三章直读 criteria"，evalmethod/regulation 引用统一。✅

## 三、CONCERNS（非阻塞，建议 backlog）

1. **[C1·测试性质] 提示词行为未经实模型验证（本质局限，须诚实披露）**
   - 新测试验证的是**平台侧不变量**（criteria 契约形、出口闸/真伪闸接受拒绝逻辑），用的是合成 payload。
   - "S1 真的读招标文件、产出结构正确的 criteria、S3 真按 criteria 评分" 属**提示词行为**，无实模型（本会话无可用模型）无法单测。→ 上线前须用真实招标文件 + 一份投标跑一次 `/tender-evaluate` 端到端冒烟，确认 criteria 真被产出且 policy_refs 不踩真伪闸。记 backlog。
2. **[C2·软约束] scoring 项与 criteria 项的对应仅靠提示词，无机器校验**
   - 现 `_verify_scoring_consistency` 只查 `0≤score≤max`，不校验 `scoring[].item` 是否对应某个 `criteria[].item`、是否漏项。模型可能少评/错配某项而不被拦。
   - v1 可接受（criteria 是辅助、承重在 verdict+policy_refs）；若要更强，可加可选闸：criteria 存在时校验 scoring 的 item 集 ⊆ criteria 的 item 集（仿 `_verify_plan_shape` 的可选校验）。记 backlog。
3. **[C3·产品语义] 价格分恒为 manual_review → 单公司结论几乎必然 manual_review**
   - `requires_cross_bid_comparison`（价格分，常占大比重）单公司无法判 → 该项 manual_review → 整体 verdict 至少 manual_review。
   - 即"单公司评标"在 v1 下**几乎不可能 approved**。这是诚实的（没有竞品报价无法算价格分），但产品上需明确：单公司跑的是"技术/商务/资格的可判定项 + 标记待横比项"，approved/rejected 留到多公司横比阶段。与用户"多家由前端/server 追加、每次只判一家"的模型一致，但该语义应在提示词/产品文案里讲透，避免使用者误以为"系统总是不下结论"。→ 见对用户追问的优化建议。

## 四、未发现的问题（明确排除）

- 无硬编码密钥 / 注入风险（纯提示词 + 测试，无新 server 代码、无新工具权限）。
- 无 statute / {招标编号} 死引用残留（grep 实证）。
- 测试无明显假绿：拒绝类用例 `pytest.raises` 真实触发出口闸/真伪闸/jsonschema。
- DRY/SRP：criteria.schema 复用既有 contract loader；测试 fixture 分 `_scored_criteria`(approved 自洽) / `_mixed_criteria`(含不可判定，schema 用)，未硬塞矛盾 fixture。
