---
description: 将原始制度文件解析为结构化 JSON 规则
allowed-tools: Read, Write, Glob, Skill, Task
---

读取用户提供的制度文件，调用 `system-rule-init` skill，将制度内容整理成对应业务域可直接使用的结构化规则。

执行要求：

1. 输入源材料优先来自 `knowledge/external/`。
2. 必须先读取 `knowledge/_schema/rule.schema.json`，所有输出都要遵守该结构。
3. 只提炼当前目标业务域相关的规则，不要把无关领域条款混入结果。
4. 如制度中覆盖多个类别，应按类别拆分写入 `knowledge/{domain}/<category>.rules.json`。
5. 写入时保留可追溯信息，包括来源文件、原文片段、版本或生效日期线索。
6. 对模糊、无法唯一结构化的条款标记 `confidence: low`，并写入 `notes`。
7. 只有在**实际写入了规则文件**、`written_files` 非空、`extracted_rule_count > 0`、`source_path` 非空时，才允许返回 `status: initialized`。
8. 如果未写入任何文件、未提取出规则、制度内容无法稳定结构化，必须返回 `status: manual_review`，并在 `manual_review_items` 与 `notes` 中写清原因，禁止返回空的“成功初始化”结果。
9. 如果输入源文件是 PDF，且存在同名文本代理文件 `logs/service/init-rules/<basename>.txt`，优先读取文本代理；但最终 `source_path` 必须仍然填写原始文件路径。
10. 如果目标域是 `expense` 且源文件是大制度手册，按类别分批处理，不要在一次上下文里完成整个 expense 域：
   - `general` → `knowledge/expense/general.rules.json`
   - `invoice` → `knowledge/expense/invoice.rules.json`
   - `loan` → `knowledge/expense/loan.rules.json`
   - `entertainment` → `knowledge/expense/entertainment.rules.json`
   - `travel` → `knowledge/expense/travel.rules.json`
   - `transport` → `knowledge/expense/transport.rules.json`
11. 对 `expense` 大域初始化，允许使用 `Task` 将单个类别拆成独立子任务；每个子任务只负责一个类别和一个目标文件，最后再汇总为单个初始化报告。
12. 完成写入后，返回一份初始化报告，说明写入了哪些文件、提取了多少规则、有哪些待人工确认项。

参数: $ARGUMENTS
用法: /init-rules knowledge/external/数睿员工手册.pdf hr
