# CC Critic 设计评审 · 第 1 轮 design（r1）

> reviewer: CC critic subagent (ultrathink, 6 维度)。对象：design.md v1。73k tokens。
> **VERDICT: NEEDS_REVISION**（与 codex REWORK 同向，核心一致）

| 维度 | 分 | 关键 |
|---|---|---|
| 边界条件 | 3 | 区间/档次、加分、一票否决/废标 四形态覆盖不足 |
| 错误处理 | 4 | OCR cloud 路径未说明；软校验边界基本清晰 |
| 测试覆盖 | 3 | AC2 缺区间/加分/skip 路径测试 |
| 历史对齐 | 4 | 软校验须进 `_validate_audit_result`，对表 decision-verification-gate |
| 复杂度 | 4 | 5 改动点恰当 |
| 历史教训 | 4 | absence-is-not-zero 保留；区间分与"不判0"冲突未解 |

## Findings
- **F1 [P0]** deductions 不覆盖档次评分（优10良7中4 不是扣减）→ 加 `scoring_mode`(deduction/tiered/subjective)，`score=max−Σ扣` 仅 deduction 模式成立。**→ v2 已用 `score_mode`(6 模式) 解决，更全。**
- **F2 [P1]** OCR purpose 透传断层：实际链 `tender_worker→ocr_preprocess_block→extract_dir→extract_one→_recognize_with_seal→engine.recognize→_recognize_via_openai_compatible`，每层改签名；**cloud 路径 `_recognize_via_paddle_cloud`(OCR_CLOUD=1) 漏**；audit 不传 purpose 无回归。**→ 并入 v2 §4。**
- **F3 [P1]** 加分项封顶 `score>max` 撞现有硬闸（output_contracts.py:265）→ 明确 additive 的 `max`=含加分上限，确保 score≤max。**→ 并入 v2 §2。**
- **F4 [P1]** 软校验挂载点：进 `_validate_audit_result` 紧跟 `_verify_scoring_consistency`(第222行后)，命名 `_verify_*_consistency`，勿放 normalize 前。对齐 [[decision-verification-gate]]。**→ 并入 v2 §5。**
- **F5 [P2]** AC2 补 skip 路径单测：① null/manual_review 不触发 ② scored 无 hits 不触发 ③ 一致不报。**→ 并入 v2 §10。**
