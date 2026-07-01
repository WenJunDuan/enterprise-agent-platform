---
doc_type: learning
slug: flash-tender-eval-inconsistency
date: 2026-07-01
sprint: 2026-06-tender-program
tags: [tender, model-eval, flash, deepseek, reliability, s7]
---

# DeepSeek Flash 评标：完成率高但同标书评分严重不一致，成本反而高

## 背景

S7 用 `logs/s7-flash-stress/run_stress.py`（复用生产 `tender_worker._run_evaluation`，DB 底稿注入 +
xhigh + 契约重试×3）对 `deepseek-v4-flash` 跑 2 真实标书 × 3 次 = 6 次评标压测。

## 教训

**"完成率 100%" 是假象，真问题在一致性。** 6/6 都产出了合法结论，但同一标书跑 3 次，
Flash 实际评分的项数与总分漂移巨大：案例B 实得合计 `[40, 66, 9]`（7 倍落差）、案例A `[7.1, 7.2, 2.0]`。
Flash 把"本可评"的项**随机 punt 成 manual**，导致评分深度每次不同——**评标不可复现**，
这对招投标是致命的（同一投标人不同次评出不同分）。单看 verdict（都 manual_review）会漏掉这个问题，
必须看结构化 `scoring[]` 的**项数与合计的方差**才暴露。

配套问题：① `policy_refs` 6 次里 4 次为空（违反"不得为空"硬规则）；② 大案例上偶发漏必填字段 /
吐非法 JSON，靠 3 次重试兜住（代价 2.5× 时延，461s vs 185s）；③ 两案例的 run3 都"崩塌"到只评
1–2 项，与超窗后底稿尾部被静默截断的表现一致（`MODEL_CONTEXT_WINDOW` 未设 → S7 guard 未触发）。

**成本也不省**：均值 $2.9/次，贵在超大底稿（40–49 万字）× xhigh，Flash 的"便宜"被 input token 吃掉。
对照早前 V4Pro(1M)：`8/1 manual_review、技术参数 21 出真分、零重试`——明显更稳。

## 如何应用

1. **评测模型别只看完成率/verdict**——评标要看 `scoring[]` 项数 + 实得合计的**跨次方差**，方差大 = 不可复现 = 不合格。多跑几次同输入是必需的。
2. **小窗口模型 + 超大底稿 = 截断风险带电**：切 Flash 这类窗口远小于 V4Pro[1M] 的模型时，务必先设 `MODEL_CONTEXT_WINDOW`（[[adversarial-empirical-review-catches-text-leaks]] 的 guard），并重跑看"崩塌"是否消失。
3. **CC 内跑评标 harness 的 env 坑**：Claude Code 会注入 `ANTHROPIC_BASE_URL=api.anthropic.com`，压过 `.env` 的 deepseek 配置触发内网 offline_guard；须 `env -u ANTHROPIC_BASE_URL -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_MODEL uv run ...`。
4. Flash 一致性不达标前，评标关键路径继续用 V4Pro；Flash 仅低风险/预筛。S7 完整评测还差 V4Pro 对照（同 harness 改 MODEL_NAME 重跑）。
