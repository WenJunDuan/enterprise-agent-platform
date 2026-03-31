---
name: system-rule-init
description: Use when 需要把本地制度源文件初始化为结构化规则文档，并补齐可追溯的来源元数据
---

# 规则初始化

## 执行步骤

1. 读取输入制度文件，并确认目标业务域。
2. 读取 `knowledge/_schema/rule.schema.json`，严格按照该结构组织结果。
3. 只提取与目标业务域直接相关、可执行、可审计的规则、标准、门槛和必备材料。
4. 将规则按类别整理；若一个制度覆盖多个类别，应拆分为多个 `knowledge/{domain}/{category}.rules.json` 文件。
5. 生成稳定的 `rule_id`，格式为 `{domain}.{category}.{序号}`，并确保同一文件内顺序连续。
6. 每个规则文档都必须填写顶层 `source.path`、`source.title`、`source.excerpt`：
   - `source.path` 是真实本地文件路径，例如 `knowledge/external/数睿员工手册.pdf`
   - `source.title` 是制度标题与章节
   - `source.excerpt` 是该规则文档覆盖的章节摘要
7. 对每条规则尽量保留 `original_text`，并在 `notes` 中记录限制条件、上下文或歧义说明。
8. 对模糊、例外过多或无法唯一结构化的条款标记 `confidence: low`，并加入人工确认说明。
9. 若需要额外生成阈值聚合文件，例如 `knowledge/{domain}/thresholds.json`，则将其视为派生文件，使用 `_meta` 记录来源，而不是混入 `rule.schema.json` 文档结构。
10. 完成后返回初始化报告，至少包含：来源文件、目标业务域、写入文件列表、提取规则总数、待人工确认事项。

## 输出要求

输出结果必须保持统一字段结构，便于后续业务域直接引用。

- 输出文件写入 `knowledge/{domain}/`，不要写到其他目录。
- 如果现有文件已存在，应在保留可追溯性的前提下更新，而不是随意新增重复文件。
- 不要输出业务审批结论；该技能只负责制度初始化和规则结构化。
- `source_path` 必须填写为真实源文件路径，不能留空。
- 只有在 `written_files` 非空、`categories` 非空、`extracted_rule_count > 0` 时，才允许返回 `status: initialized`。
- 如果没有实际写入规则文件，或只读了制度却未产出任何规则，必须返回 `status: manual_review`，并明确说明未写入原因；禁止返回空的 `initialized` 结果。
- 如果存在同名文本代理文件 `logs/service/init-rules/<basename>.txt`，优先读取文本代理，而不是反复直接读取 PDF；但最终 `source_path` 仍写原始文件路径。
- 如果输入源是 `knowledge/external/数睿员工手册.pdf` 且目标域为 `expense`，应优先映射到：
  - `6.3` → `general` / `invoice`
  - `6.4` → `loan`
  - `6.5` → `entertainment`
  - `6.6` → `travel`
  - `6.7` → `transport`
- 如果 `expense` 域来源是整本员工手册，不要试图在一个大上下文里同时完成全部类别。应按类别拆分，并且每个子任务只负责一个目标文件：
  - `general` → `knowledge/expense/general.rules.json`
  - `invoice` → `knowledge/expense/invoice.rules.json`
  - `loan` → `knowledge/expense/loan.rules.json`
  - `entertainment` → `knowledge/expense/entertainment.rules.json`
  - `travel` → `knowledge/expense/travel.rules.json`
  - `transport` → `knowledge/expense/transport.rules.json`
