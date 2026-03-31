---
name: expense-audit
description: "审计出差报销材料的完整工作流。用户上传出差记录、行程单、报销单、发票、水单、机票/酒店订单等任意组合的报销材料，本技能自动提取结构化数据、交叉比对各文档一致性、依据报销政策规则检查费用合理性，并生成审计报告。触发条件：用户提到报销、差旅审计、费用审核、出差报销检查、expense audit、reimbursement review，或上传了看起来像发票/行程单/报销单的文件。即使用户只上传了部分材料（比如只有几张发票），也应触发此技能进行可用范围内的审计。"
---

# 出差报销审计技能 (Expense Audit Skill)

## 设计哲学

这是一个**数据对账**问题，不是聊天问题。

核心：从 N 份异构文档提取结构化费用事件，构建时间线，用规则集逐项审查。引擎是确定性的——同输入同输出，不允许创造性发挥。

阶段：盘点 → 提取 → 审查 → 报告。不要跳步。

---

## Phase 0: 文件盘点

1. `view /mnt/user-data/uploads` 列出所有文件
2. 按扩展名分类，猜测文档类型：
   - **行程单/出差审批**: 日期范围、目的地、出差事由、出差人及职级
   - **报销单/费用汇总**: 费用明细清单、总金额、提交日期
   - **发票/水单/收据**: 单笔凭证（注意提取发票号码、抬头）
   - **机票/电子客票行程单**: 航班、舱位、乘机人
   - **火车票**: 车次、座次等级、乘车人
   - **酒店水单/发票**: 入住退房日期、房价、城市
   - **出租车/网约车行程单**: 起止地点、金额、日期
   - **餐饮发票**: 金额、用餐人数、事由
   - **其他**: 会议通知、邀请函等辅助材料
3. 向用户确认分类，询问遗漏材料
4. **关键**: 询问出差人职级（未提供时）——直接影响住宿/交通标准

---

## Phase 1: 结构化数据提取

对每份文件，按类型选正确的读取方式：

**PDF** → 先按 `/mnt/skills/public/pdf-reading/SKILL.md` 做 content inventory:
```bash
pdfinfo /mnt/user-data/uploads/xxx.pdf
pdftotext -f 1 -l 1 /mnt/user-data/uploads/xxx.pdf - | head -30
```
文本差（扫描件）→ rasterize: `pdftoppm -jpeg -r 200 -f 1 -l 1 xxx.pdf /tmp/page`

**图片** → context 中直接可见，视觉理解提取。

**Excel/CSV** → `pd.read_excel(..., nrows=50)` 或 `pd.read_csv(..., nrows=50)`

**Word** → `pandoc xxx.docx -t plain`

### 提取 Schema（完整字段表）

**所有字段都要尝试提取**，缺失标 null。字段缺失 = 检查跳过 = 审计盲区。

```python
expense_event = {
    # ─── 元信息 ───
    "source_file": "文件名",
    "doc_type": "itinerary|expense_report|invoice|receipt|ticket|hotel|taxi|meal|other",
    "confidence": "high|medium|low",

    # ─── 出差人信息 ───
    "travelers": ["姓名"],
    "rank_tier": "senior|middle|staff|null",  # 职级

    # ─── 时间信息 ───
    "date": "YYYY-MM-DD",                                         # 费用发生日
    "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},   # 行程/住宿
    "submission_date": "YYYY-MM-DD",                               # 报销提交日

    # ─── 费用信息 ───
    "category": "transportation|accommodation|meals|communication|miscellaneous",
    "subcategory": "flight|train|taxi|rideshare|local_transit|hotel|per_diem|business_meal|phone|other",
    "amount": 0.00,
    "currency": "CNY",
    "description": "费用描述",

    # ─── 票据信息 ───
    "has_invoice": true,
    "invoice_number": "",            # 发票号码
    "invoice_code": "",              # 发票代码
    "invoice_company_name": "",      # 发票抬头（购买方名称）
    "invoice_type": "electronic|paper|none",
    "tax_amount": 0.00,

    # ─── 地点信息 ───
    "location": {"city": "", "province": ""},
    "departure_city": "",            # 交通：出发城市
    "arrival_city": "",              # 交通：到达城市
    "vendor": "供应商/商家",

    # ─── 交通专属 ───
    "flight_class": "economy|premium_economy|business|first|null",
    "train_class": "second|first|business|null",
    "flight_number": "",
    "train_number": "",

    # ─── 餐饮专属 ───
    "guest_count": null,             # 用餐人数
    "meal_occasion": "",             # 用餐事由
    "meal_guests": [],               # 陪餐人员

    # ─── 住宿专属 ───
    "hotel_name": "",
    "check_in": "YYYY-MM-DD",
    "check_out": "YYYY-MM-DD",
    "nights": null,
    "daily_rate": null               # 每晚房价（发票明细）
}
```

### 提取质量自检

提取完成后对照：
- [ ] 每笔费用有 `date`？
- [ ] 行程单有 `date_range`？
- [ ] 机票有 `flight_class`？火车票有 `train_class`？
- [ ] 酒店有 `check_in`/`check_out`/`nights`？
- [ ] 商务餐有 `guest_count`？
- [ ] 发票有 `invoice_number` 和 `invoice_company_name`？
- [ ] `rank_tier` 已确认？

关键字段大面积缺失时，进 Phase 2 前向用户说明。

保存 JSON：
```python
import json
with open("/home/claude/extracted_expenses.json", "w") as f:
    json.dump(all_events, f, ensure_ascii=False, indent=2)
```

---

## Phase 2: 审查引擎

```bash
pip install pyyaml --break-system-packages -q
python /path/to/skill/scripts/audit_check.py \
    --expenses /home/claude/extracted_expenses.json \
    --rules /path/to/skill/references/default_rules.yaml \
    --output /home/claude/audit_results.json
```

引擎执行 **20 类检查**（分 5 个维度）：

**时间维度**: 费用日期范围、住宿天数vs出差天数、报销时效、周末/节假日异常

**金额维度**: 报销单vs票据合计、住宿超标、出租车日累计、商务餐人均、伙食补助天数

**职级合规**: 机票舱位、火车座次、总额审批阈值

**票据合规**: 发票完整性、抬头检查、发票号码去重、商务餐信息完整性

**逻辑一致性**: 地点匹配、交通路线、同日同类重复、疑似重复报销

---

## Phase 3: 审计报告

读 `audit_results.json`，生成 Markdown 报告结构：

```
# 出差报销审计报告
## 基本信息（出差人/职级/时间/目的地/总额/提交日期）
## 审计摘要（通过/警告/违规/待确认数量 + 审计结论）
## 费用明细对照表（每笔费用 × 金额 × 票据 × 职级标准 × 检查结果）
## 发现的问题
  ### ❌ 违规项（按严重程度，每项含：规则ID、描述、文件、建议）
  ### ⚠️ 警告项
  ### ❓ 信息不足项
## 审计规则适用说明（规则版本、职级、城市等级、关键标准数字）
```

保存 `/mnt/user-data/outputs/expense_audit_report.md` 并 present。
需要 Word → 读 `/mnt/skills/public/docx/SKILL.md` 生成 .docx。

---

## 规则管理

- 默认: `references/default_rules.yaml`（占位符基线）
- 自定义: 上传制度文档 → 提取 → 与 `references/rule_schema.md` 对照 → 合并覆盖
- 规则 schema 详见 `references/rule_schema.md`

---

## 边界情况

| 情况 | 处理 |
|------|------|
| 材料不完整 | 有什么审什么，标注信息不足项 |
| 职级未知 | 默认 staff（最严标准），报告标注 |
| 扫描件质量差 | confidence: low，提示人工核对 |
| 多人出差 | 按人分组，共同费用单独标注 |
| 外币费用 | 记录原币，不换算，标注需确认 |
| 缺少发票 | HIGH 问题，但市内公交/通讯补助除外 |
| 当天往返 | 0晚住宿正常，伙食按1天计 |

---

## 安全

- 不在报告中重复身份证号/银行账号等隐私
- 审计结果仅供参考，不构成财务/法律意见
- 告知用户最终判断由财务人员做出
