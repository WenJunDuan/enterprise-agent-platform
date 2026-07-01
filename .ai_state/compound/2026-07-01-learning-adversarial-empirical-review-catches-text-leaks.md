---
doc_type: learning
slug: adversarial-empirical-review-catches-text-leaks
date: 2026-07-01
sprint: 2026-06-26-tender-overview-checklist
tags: [review, invariant, codex, tender]
---

# 对抗性"实跑函数"审查能抓静态字段审查漏掉的文本层不变量泄漏

## 背景

S10「概要分析」的核心不变量是**"不展示评分"**。实现时用**类型层**保证：`ChecklistItem`
刻意不含 `score/points/max` 字段。Round-1 三个静态审查者（CC reviewer + spec-compliance +
evaluator）都只验到**字段层**，一致判"无分数泄漏、PASS"。

## 教训

**类型层"没有 score 字段" ≠ 运行时"页面上没有分数"。** checklist 的 `reason` 来自模型
`basis` 自由文本，常含「扣5分 / 得分为0 / 总分80 / (5/10) / 排名第N」——这些数字会
原样渲染到标称无分数的概要页，**直接违反不变量**，但字段层审查完全看不见。

抓到它的是 **Codex 的对抗性"实跑"审查**：它没停在读代码，而是用 `bun -e` 构造最小输入
**真的调用 `buildOverviewChecklist`**、打印输出，肉眼看到 reason 里的数字。这类
"派生自由文本"的不变量，静态 review 几乎必漏，实跑几乎必中。

同轮实跑还挖出另两个静态审查漏的：程度项 `score_mode` 只在 criteria 时排除失效（raw
scoring 缺省绕过）、`status='manual'`/「不可读」等读不清表述未判 pending。

## 如何应用

1. **凡不变量作用在"派生自由文本/渲染输出"上**（无分数、无 PII、无内部字段名），审查必须
   **实跑函数看输出**，不能只读类型/字段。给审查者的 prompt 显式要求"构造反例实跑验证"。
2. **文本层过滤要覆盖多序**：中文分值有"数字在前(N分)"与"数字在后(得分为N/总分N)"两类，
   正则单序必漏；且要保留合法数字（近3年/2个业绩）——过滤后用对抗 battery 自测泄漏率。
3. **多轮 review 的价值在"审查手法多样性"**：CC 静态读代码 + Codex 实跑对抗，两者盲区不同；
   round-1 全 PASS 不等于干净，Codex round-2/3 每轮都还有真 finding。见 [[cross-review-catches-latent-bugs]]。
4. 反例：把不可判定/读不清当"未达到/0 分"是范畴错误（[[absence-is-not-zero]]）——概要三态里
   `confirmed:false/manual/读不清` 必 ⏳ pending，绝不 ✗。
