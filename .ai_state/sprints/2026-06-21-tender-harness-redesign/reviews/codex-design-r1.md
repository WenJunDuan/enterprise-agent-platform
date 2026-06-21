# Codex 设计评审 · 第 1 轮 design（r1）

> reviewer: codex exec (gpt-5.5, xhigh, read-only)。对象：design.md v1。179k tokens。
> **VERDICT: REWORK**

## P0

- **[P0] 评分模型不能只有扣减制**（design.md:20/43/47/58）：`score=max−Σ扣` 覆盖不了加分累计、优/良/中档次给分、公式分、客观通过/不得分、主观区间分；法规要求按招标文件明确的量化因素/权重评审。**建议**：criteria.items 加 `score_mode`（deduction/additive/banded/formula/pass_fail/manual/gate），分别建 `deductions[]`/`awards[]`/`bands[]`/`formula`，按 mode 校验。依据：发改委《评标委员会和评标方法暂行规定》 https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=18516
- **[P0] 软校验误伤区间分**（design.md:32/43/58/71）：优10良7中4 的 7 分不是"扣3分"，强转扣分=伪扣分依据。**建议**：一致性校验只在 `score_mode=deduction` 启用；`banded` 校验 `score==selected_band.points`，`additive` 校验 `base+Σaward`，formula/横比/主观项只做范围+人工复核信号。
- **[P0] 废标/资格缺独立 gate**（tender-evaluate.md:45/51-55, CLAUDE.md:42, goal.md:23/43）：一票否决/资格不符/串通/异常低价澄清失败是"投标有效性"问题，不是某 scoring item 的扣分。**建议**：单建 `eligibility_checks[]`/`rejection_rules[]`/`disqualification_hits[]`，verdict 由 gate 命中决定，同时保留逐项评分。依据：实施条例 https://www.ndrc.gov.cn/xxgk/zcfb/qt/201511/t20151103_967423.html

## P1

- **[P1] tag 不分客观/主观分**（criteria.schema.json:52-60）：技术/服务方案主观档次评分若标 scored，模型会给伪客观分。**建议**：加 `evaluator_type: objective|subjective|mixed` + `review_required` + `rubric_basis`；主观项默认人工复核/低置信 warning。
- **[P1] deductions 表达力不足**（design.md:22-28）：缺稳定 `deduction_id`、`source_quote`、按项/按次/按比例(`unit`)、互斥组、项内总封顶(`max_deduct`)、最低得分、严重程度档。**建议**：补这些字段，`deduction_hits[].deduction_id` 回链。
- **[P1] 向后兼容不完整**（criteria.schema.json:29 additionalProperties:false, tender_compare_worker.py:78-82）：item 是 `additionalProperties:false`，不显式加字段则输出 deductions 被拒；新旧 criteria hash 不一致影响横比。**建议**：schema 显式加字段；算 criteria_hash 前把缺失 deductions 规范化为 []。
- **[P1] warning 无存放/返回路径**（design.md:57-59, output_contracts.py:246-268）：校验入口现在要么抛 JSONContractError 要么静默通过，warning 没地方放。**建议**：明确 `extracted_data.validation_warnings[]`，测试结果端点可读。

## P2

- **[P2] OCR purpose 函数签名/传播边界要显式**（pipeline.py:207-222, audit_worker/tender_worker）：`ocr_preprocess_block` 同时服务 audit/tender/OCR端点/CLI，全局默认拼 prompt 会污染 audit。**建议**：显式 `purpose: str|None` 从 tender_worker 传到 extract_dir/extract_one/recognize；audit/ocr/cli 默认 None，加回归测试断言 audit prompt 不含 tender 文案。
- **[P2] command 文档与实际 OCR 注入矛盾**（tender-evaluate.md:6）："直接 Read 不依赖 OCR 预处理" vs 服务端已注入底稿。**建议**：同步命令语义为"若服务端注入底稿则优先用，必要时回读原文件核验"。
