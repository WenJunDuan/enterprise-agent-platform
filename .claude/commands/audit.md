---
description: 审核单个输入文件或目录
allowed-tools: Read, Write, Glob, Skill, Task
---

读取指定输入路径，路径既可以是单个文件，也可以是一个目录。

执行要求：

1. 如果输入是单个文件，直接读取该文件，调度 `expense-extractor` → `expense-auditor`，高风险时再调度 `expense-reviewer`。
2. 如果输入是目录，先枚举目录下相关材料，再综合目录内申请单、报销单、发票、行程单、酒店单据等文件一起审核，不要只看第一个文件。
3. 最终审核结论必须符合 `.claude/contracts/common/audit-result.schema.json`，同时包含完整结构化字段以及 `result`、`conclusion`、`explanation`。
4. `conclusion` 和 `explanation` 必须使用中文；`manual_review` 时，`conclusion` 必须固定为 `待人工复核`，且 `explanation` 必须明确写出不能自动放行的原因。
5. 优先直接返回完整审核结果给调用方，不要手工再包装一层新的 envelope。

参数: $ARGUMENTS
用法: /audit data/claims/CLAIM-001.json
目录示例: /audit data/case1
