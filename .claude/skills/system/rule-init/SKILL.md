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
6. 每个规则文档都必须填写顶层 `source_path`、`source_version`、`generated_at`（字段以 `knowledge/_schema/rule.schema.json` 为准）：
   - `source_path` 是真实本地文件路径，例如 `knowledge/external/南通高新区接待管理办法.docx`
   - `source_version` 是制度标题 / 文号 / 版本
   - `generated_at` 是规则文件生成时间（ISO 8601）
7. 对每条规则尽量保留 `original_text`，并在 `notes` 中记录限制条件、上下文或歧义说明。
8. 对模糊、例外过多或无法唯一结构化的条款标记 `confidence: low`，并加入人工确认说明。
9. 完成后返回初始化报告，至少包含：来源文件、目标业务域、写入文件列表、提取规则总数、待人工确认事项。

## 输出要求

输出结果必须保持统一字段结构，便于后续业务域直接引用。

- 输出文件写入 `knowledge/{domain}/`，不要写到其他目录。
- 如果现有文件已存在，应在保留可追溯性的前提下更新，而不是随意新增重复文件。
- 不要输出业务审批结论；该技能只负责制度初始化和规则结构化。
- `source_path` 必须填写为真实源文件路径，不能留空。
- 只有在 `written_files` 非空、`categories` 非空、`extracted_rule_count > 0` 时，才允许返回 `status: initialized`。
- 如果没有实际写入规则文件，或只读了制度却未产出任何规则，必须返回 `status: manual_review`，并明确说明未写入原因；禁止返回空的 `initialized` 结果。
- 如果存在同名文本代理文件 `logs/service/init-rules/<basename>.txt`，优先读取文本代理，而不是反复直接读取 PDF；但最终 `source_path` 仍写原始文件路径。
- `expense` 域现有制度源与目标文件（南通高新区）：
  - 差旅（`南通市市级机关国内差旅住宿费标准.pdf` / 高新区差旅须知，援引通州〔2015〕1 号）→ `travel` → `knowledge/expense/travel.rules.json`
  - 工作餐（`南通高新区工作餐管理制度.docx`）→ `meal` → `knowledge/expense/meal.rules.json`
  - 接待（`南通高新区接待管理办法.docx`）→ `entertainment` → `knowledge/expense/entertainment.rules.json`
- 若单个制度源覆盖多个类别，按类别拆分为多个目标文件，每个子任务只负责一个类别和一个目标文件。
- `tender`（招投标评标）域分两层，`category` 轴用法特殊：
  - 通则 / 法规（招标投标法、政府采购法、综合评分法通则等，置于 `knowledge/external/`）→ category 取 `statute` → `knowledge/tender/statute.rules.json`
  - 单个项目招标文件第三章《评标办法》→ category 取**招标编号**（如 `r2024007`）→ `knowledge/tender/{招标编号}.rules.json`
  - 评分项若属"单份投标文件无法判定"，须在该规则 `tags` 标注 `requires_live_event`（现场答辩）/ `requires_external_data`（外部信用等）/ `requires_cross_bid_comparison`（价格分需横向比较），并在 `notes` 说明所需外部输入。`rule_id` 用下划线，如 `tender_statute_001`、`tender_r2024007_004`。
