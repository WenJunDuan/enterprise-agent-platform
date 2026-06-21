# Codex 评审 · 第2轮 prompt A+G5（r2）

> reviewer: codex exec (read-only)。对象:tender-evaluate.md S3 的 A 条 + G5 改动。148k tokens。
> **VERDICT: REWORK → 已修**

## P1（已修）
- **[P1-1] A 条与 G3(a) 边界混,硬降级误伤客观 0**:additive「提供才加分」确认没加分内容=合理 0,被硬降级 manual_review 误伤。codex:0 vs manual_review 要回到招标规则+证据。**修**:校验硬降级**仅在整单 disqualification_hits 非空(投错标/实质性不响应)时触发**(此时该项确无可评事实);正常案例仅 warning 不强改。+单测(降级/不降级两路)。
- **[P1-3] evaluator.md 没同步**(formula 统归 manual_review,无 A/G5)。**修**:标注「S3 以 /tender-evaluate 命令为权威,本 agent 摘录可能滞后」。

## P2（已修）
- **[P2-4] G5 示例矛盾**(L24「每高10%得1分」vs L55「扣1分」)。**修**:统一为「以招标明示为准」+ 补判别条件(群体变量→横比;招标常量+本家→单家算)+「最高限价本身不是评分公式,只规定超限价废标则走 gate」。

## Backlog
- **[P1-2] G5 输入不够结构化**:S2 只抽 bid_price 总额,限价类需分项单价/单位/限价来源页。codex 建议 S1/S2 加「公式变量清单」(limit_value/bid_component/formula_variables)。**较大,留第3轮**(prompt 已补判别条件作为过渡)。
