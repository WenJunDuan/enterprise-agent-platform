---
description: 将原始制度文件解析为结构化 JSON 规则
allowed-tools: Read, Write, Glob, Skill
---

读取用户提供的制度文件，调用 `system-rule-init` skill，将制度内容整理成对应业务域可直接使用的结构化规则。

执行要求：

1. 输入源材料优先来自 `knowledge/external/`。
2. 必须先读取 `knowledge/_schema/rule.schema.json`，所有输出都要遵守该结构。
3. 只提炼当前目标业务域相关的规则，不要把无关领域条款混入结果。
4. 如制度中覆盖多个类别，应按类别拆分写入 `knowledge/{domain}/<category>.rules.json`。
5. 写入时保留可追溯信息，包括来源文件、原文片段、版本或生效日期线索。
6. 对模糊、无法唯一结构化的条款标记 `confidence: low`，并写入 `notes`。
7. 完成写入后，返回一份初始化报告，说明写入了哪些文件、提取了多少规则、有哪些待人工确认项。

参数: $ARGUMENTS
用法: /init-rules knowledge/external/数睿员工手册.pdf hr
