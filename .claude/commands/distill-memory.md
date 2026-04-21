---
description: 从已归档审核结果中提炼结构化业务记忆
allowed-tools: Read, Write, Glob, Skill, Task
---

读取已归档的审核结果文件，调用 `system-memory-distill`，将可复用的业务经验沉淀为结构化记忆资产。

执行要求：

1. 输入应优先指向 `logs/results/by-request/.../*.json` 这类已归档结果文件。
2. 必须先读取 `knowledge/_schema/case-memory.schema.json`，所有沉淀产物都要遵守该结构。
3. 只沉淀可复用的业务模式、异常模式、复核分歧模式；不要把一次性运维噪音、路径错误、网关失败等基础设施问题写成业务记忆。
4. 输出文件写入 `knowledge/memory/{domain}/`，并保留 `source_trace.request_id` 与 `source_trace.result_file` 回链。
5. 如果现有结果不足以形成稳定经验，应停止写入，并明确说明为什么不能沉淀。

参数: $ARGUMENTS
用法: /distill-memory logs/results/by-request/2026/04/21/example.json expense
