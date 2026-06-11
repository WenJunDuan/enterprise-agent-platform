---
name: common-rule-query
description: Use when 任意业务域需要从本地结构化规则文件检索适用规则，并返回可引用的 rule id 与来源路径
---

# 通用规则查询

## 使用方法

1. 根据业务域和类别定位结构化规则文件，例如 expense 域的：
   - `knowledge/expense/travel.rules.json`
   - `knowledge/expense/meal.rules.json`
   - `knowledge/expense/entertainment.rules.json`
2. 读取规则文件顶层 `source`，把它当作追溯信息，而不是现场自由造规则的依据。
3. 按角色、金额、日期、附件、场景和优先级筛选匹配项。
4. 返回结果至少包含：
   - `rule_id`
   - `action`
   - `priority`
   - `rule_file`
   - `source_path`
   - `source_title`
   - `original_text`

## 冲突处理

- `priority` 数字越小优先级越高。
- 同优先级时，`reject` 优先于 `approve`。
- 如果结构化 rules 与制度摘录不能一致解释，返回冲突说明并输出 `manual_review`。
- 如果制度源存在相关章节但结构化 rules 未覆盖，不要自行补全规则，提示后续使用 `system-rule-init` 更新规则库。
