---
doc_type: learning
date: 2026-06-26
slug: cross-review-catches-latent-bugs
sprint: 2026-06-tender-program (S1-S6)
---

# 学习：双向交叉 review 抓到全绿测试漏掉的潜伏 bug

## 背景

tender 域重构 S1-S6 由 CC 与 Codex 分工并行（各自 worktree、文件不重叠），完成后**互相**做
只读 headless code review（CC 审 Codex 的 S1/S2/S5/S6；Codex 审 CC 的 S3/S4）。每个 sprint 交付时
`uv run pytest -q` + ruff/前端 build **本就全绿**。

## 关键事实

对抗式交叉 review **各抓到 1 个 CC 侧潜伏 bug——全绿测试套没暴露**：

- **S3**：`is_ocr_text_valid` 只判文本**开头**是否 `[识别失败]` 前缀；但 `build_extraction_block`
  会在正文前加 `### 文件:` 头 → 整块全失败时不以前缀开头 → 漏判为"有效"。这是**先于 S3 就存在**
  的潜伏 bug，迁移把它照搬过来；Codex review 发现 → 改为逐行剔除文件头后再判 + 回归用例
  （commit `11c3426`）。
- **S4**：`output_contracts → tender_output → server.common.contract`，而 `contract` 末尾又
  import `output_contracts` → **module-load 时序**循环 import 风险。测试因 import 顺序恰好没触发，
  但结构脆弱；Codex review 指出 → 打破环（commit `38efb67`）。

两者都是"测试没覆盖到的边界"（rendered-all-error 块）与"import 时序"——**单跑测试套 + 自审都
测不出**。

## 如何应用

- **重构/迁移类改动即使全绿，也要过一次独立交叉 review**（另一方 headless、只读、对抗式找茬），
  重点盯：① 测试没覆盖的边界/组合；② import 时序 / 循环依赖；③ 迁移时"照搬了原有潜伏 bug"。
- 交叉 review 用 `codex exec -s read-only`（只输出 findings/VERDICT，不改文件），CC 与 Codex 互审。
- 与 [[2026-06-17-learning-cross-review-and-soft-timeout]] 一致：绿测试 ≠ 正确，独立视角是补充。
