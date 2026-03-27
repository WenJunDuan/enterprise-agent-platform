---
description: 审核单个输入文件
allowed-tools: Read, Write, Glob, Skill, Task
---

读取指定输入文件，调度 `expense-extractor` → `expense-auditor`，高风险时再调度 `expense-reviewer`。
最终结果写入 `logs/results/`。

参数: $ARGUMENTS
用法: /audit data/claims/CLAIM-001.json

