---
name: common-evidence-chain
description: Use when 需要把规则依据、业务事实和异常发现压缩成符合 audit-result schema 的证据链
---

# 通用证据链构建

用于把多个业务域、多个规则来源和多个判断过程整理成符合 `.claude/contracts/common/audit-result.schema.json` 的证据链。

每条证据应包含：

- `source`
- `finding`
- `conclusion`

## `source` 写法

`source` 必须是单个字符串，不要输出数组或对象。推荐格式：

- `rule:expense.travel.004 @ knowledge/expense/travel.rules.json <- knowledge/external/数睿员工手册.pdf`
- `field:claim.total_amount`
- `doc:invoice-001.pdf`

## 组织顺序

1. 先放规则依据
2. 再放业务事实
3. 最后放结论性证据

## 约束

- 每条证据只描述一个判断点
- 不要把多个结论塞进同一条 `finding`
- 证据不足时写 `conclusion: inconclusive`，并让上层输出 `manual_review`
