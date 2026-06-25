# Issue Analysis — Tender Score Summary

## 结论

评分项数量本身没有漏。问题在最终说明层：

- 模型结构化输出里的 `scoring[]` 是可计算的权威明细。
- `explanation` 是模型自由文本，可能再次手算小结并算错。
- `explanation` 没有服务端清洗，内部字段名会直接暴露给用户。

## 相关代码

- `.claude/commands/tender-evaluate.md`
  - 已要求口头总分等于 `scoring[]` 非空分数之和，但模型仍可在自由文本里漂移。
- `server/common/output_contracts.py`
  - 只校验每项 `0 <= score <= max`。
  - 校验 score_mode 内部明细时只记录 warning。
  - 之前没有重写用户可见的最终小结。
- `server/stores/tender_doc_store.py`
  - 评标完成后回填 criteria 时只写 `criteria`，没有把 `criteria_status` 置为 `ready`。
  - Mac mini 出现 `criteria` 已有 10 项但 `criteria_status=running` 的状态不一致。

## 修复策略

- 不改模型判断，不在服务端重算每项得分。
- 服务端只做展示兜底：
  - 去掉模型最后自写的“综上合计”段。
  - 清理内部字段名。
  - 按 `scoring[]` 追加服务端计算的简短得分小结。
- 评标回填 criteria 时同步把 `criteria_status` 置为 `ready`。

