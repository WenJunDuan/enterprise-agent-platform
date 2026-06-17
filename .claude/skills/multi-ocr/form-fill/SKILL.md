---
name: multi-ocr-form-fill
description: 把识别内容映射到目标表单字段(单行/多行/下拉/数字/日期/子表)，含合同付款节点→预测付款子表抽取
---

# 表单回填映射

把 `extract-result` 的内容映射到目标表单 schema，产出符合 `.claude/contracts/ocr/form-fill.schema.json` 的结果。组件细则见 `references/form-components.md`。

## 组件映射

| 组件 | 来源 | 规则 |
|---|---|---|
| 单行文本 single_line | 命名实体 / 字段值 | 取最高置信值，去换行 |
| 多行文本 multi_line | 段落 / 条款 | 保留换行 |
| 下拉选择 select | 枚举字段 | **必须命中 options**，命不中 → low_confidence |
| 数字 number | 金额 / 数量 | 去千分位、保留精度；OCR 数字必标置信 |
| 日期 date | 日期字段 | 归一 ISO `YYYY-MM-DD`；歧义不臆测 |
| 子表 sub_table | 重复行（付款节点） | 每节点一行，见下 |

## 合同付款节点 → 预测付款子表

从合同付款条款 / 付款计划表逐条抽取**每个付款节点**为一行：
`节点名 / 触发条件 / 比例 / 金额 / 计划日期 / 币种`，每字段带 `confidence`。

- 散落在条款（非整齐表格）时用**语义抽取**，不只依赖表格识别。
- 比例与金额应自洽（Σ比例≈100%、Σ金额≈合同总额）；不自洽 → 标 `low_confidence`。

## 输出

`fields[]` + `sub_tables[]` + `low_confidence[]` + `needs_review` + `evidence[]`。
任一关键字段低置信 → `needs_review=true`。
