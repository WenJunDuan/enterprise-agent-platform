---
name: common-evidence-chain
description: 将规则依据、业务事实和异常发现整理成完整证据链
---

# 通用证据链构建

用于把多个业务域、多个规则来源和多个判断过程整理成一条完整结论链。

每条证据应包含：

- `source`
- `finding`
- `conclusion`

输出有序数组，按推理顺序排列。
