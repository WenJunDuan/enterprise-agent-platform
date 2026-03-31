# 报销规则 Schema 定义 v2.0

## 目的

规则文件（默认或自定义）遵循此 schema，确保审计引擎正确解析和执行全部 20 类检查。

## v2.0 新增

相对 v1.0，新增了以下字段：
- `transportation.flight.class_hierarchy` — 舱位等级排序表
- `transportation.train.class_hierarchy` — 座次等级排序表
- `meals.per_diem.half_day_ratio` — 首末日半天系数
- `general.company_name` / `company_name_aliases` — 发票抬头校验
- `general.reimbursement_deadline_days` — 报销时效
- `general.approval_thresholds` — 分级审批阈值
- `holidays` — 节假日定义（周末/假日费用标记）
- `communication.requires_invoice` — 通讯费是否需要发票

## 顶层结构

```yaml
schema_version: "2.0"
last_updated: "YYYY-MM-DD"
currency: "CNY"

rank_tiers: [...]              # 职级定义
city_tiers: {...}              # 城市分级
accommodation: {...}           # 住宿规则
transportation: {...}          # 交通规则（含 flight/train/taxi 子模块）
meals: {...}                   # 餐饮规则（含 per_diem/business_meal）
communication: {...}           # 通讯规则
miscellaneous: {...}           # 其他费用
general: {...}                 # 通用规则（含公司名、审批阈值、时效）
thresholds: {...}              # 审计阈值
holidays: {...}                # 节假日定义
```

## 单条规则格式

```yaml
- id: "XXX-NNN"                # 唯一编号
  description: "规则描述"
  severity: "HIGH|MEDIUM|LOW"
  condition: "..."             # 可选: 触发条件描述
  exception: "..."             # 可选: 例外情况
  reference: "..."             # 可选: 制度原文引用
```

severity: HIGH=必须修正 / MEDIUM=建议修正 / LOW=提醒

## 等级层级表 (class_hierarchy)

用于舱位/座次对比，数组索引越大等级越高：

```yaml
flight:
  class_hierarchy: ["economy", "premium_economy", "business", "first"]
train:
  class_hierarchy: ["second", "first", "business"]
```

引擎用 `class_rank()` 比较实际等级与职级允许最高等级的索引位置。

## 审批阈值 (approval_thresholds)

```yaml
approval_thresholds:
  - amount: 5000
    approver: "部门负责人"
  - amount: 20000
    approver: "分管领导"
```

引擎从高到低匹配，命中第一个即触发 WARNING。

## 自定义规则合并逻辑

1. **字段级覆盖**: 自定义文件中出现的字段覆盖默认值
2. **规则追加**: 自定义 rules 中 ID 不在默认集的追加
3. **规则替换**: ID 重复的替换默认
4. **缺失回退**: 未定义模块使用默认

**关键**: `general.company_name` **必须**替换为企业全称，否则发票抬头检查会标记为 UNKNOWN。

## 从制度文档提取规则的指引

优先级:
1. **金额上限** → 各模块 daily_limit / per_person_limit
2. **职级差异** → rank_tiers + 限额矩阵
3. **舱位/座次限制** → class_limit + class_hierarchy
4. **审批层级** → approval_thresholds
5. **票据要求** → requires_invoice / rules
6. **报销时效** → reimbursement_deadline_days
7. **公司名称** → company_name + aliases
8. **特殊条款** → 追加为新 rules

标注置信度: 制度有明确数字=HIGH / 有描述无数字=MEDIUM / 未提及=使用默认
