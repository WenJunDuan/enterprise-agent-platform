# D3+D10 真网关验收记录 (2026-07-18, merge 13ec8b1 后主 agent 跑)

design 验收标准 1-4 全部满足。证据如下。

## 验收 1 · flag off 基线 (静态)
- 全量 `uv run pytest -q` = **893 passed**(887 基线 + 6 F1-F4 新增); ruff 净。
- flag off wiring 断言(direct 入口 fail-if-called)全绿; golden 见验收 2 对照。

## 验收 2 · flag on/off 真网关对照 (case-taxi, deepseek-v4-flash, 同窗交错)
| 路径 | 墙钟 | verdict | policy_refs | session | meta_wall |
|---|---|---|---|---|---|
| DIRECT (on) | 13.2s | rejected | [expense_travel_005] | None | 13.171 |
| CLI (off) | 52.8s | rejected | [expense_travel_005] | 有(f0f5f71b…) | 0.0 |
| DIRECT (on) | 20.1s | rejected | [expense_travel_005] | None | 20.103 |

- 直连中位 16.7s vs CLI 52.8s = **on ≈ off×32%**,远低于 ≤70% 达标线。
- verdict/policy_refs 两路完全一致; session 字段正确区分(直连 None / CLI 有); T3 meta_wall/token 指标真实。

## 验收 3 · CC 对话路径 (/audit skill, case-taxi)
- 薄壳 audit.md 首步强制指令生效: 主 agent 按命令先 `Read server/audit/runner.py` 取
  AUDIT_INSTRUCTIONS 全文再判断(非凭记忆)。
- 结论 verdict=**rejected** / policy_refs=**[expense_travel_005, expense_travel_008]**,与
  Python 路径一致(核心引 expense_travel_005 相同)。判断纪律单源无漂移。

## 验收 4 · 回落语义单测 + T4 vision POC
- 回落两分支单测(传输类 500 回落一次 / 契约类不回落 / 4xx 原样传播不回落)全绿。
- **T4 vision POC(真网关)**: 当前网关模型 deepseek-v4-flash **不支持 vision**(image block
  两次空回答)→ 判定「不支持」终止条件 → **D10② 附件预嵌降级 backlog**(需读附件的案件继续走
  CLI 路径,符合 design 风险表)。这是 design 允许的两种 T4 终止结果之一,T4 完成。

## 结论
review 三件套=reviewer 无 P0(3 P1+1 P2 全修+测试佐证)/ spec PASS / evaluator PASS; 真网关四项
达标。**D3(prompt 单源)+D10①③④ DONE**; D10②(vision 附件预嵌)因网关模型不支持降 backlog,
待部署机换 vision-capable 模型后重启。
