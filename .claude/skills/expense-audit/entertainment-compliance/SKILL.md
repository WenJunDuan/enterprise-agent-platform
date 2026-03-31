---
name: expense-audit-entertainment-compliance
description: Use when 需要审核业务招待、礼品或客户陪同费用是否符合本地招待制度与差旅联动规则
---

# 招待合规

## 读取规则

- `knowledge/expense/entertainment.rules.json`
- `knowledge/expense/travel.rules.json`
- 制度追溯源：`knowledge/external/数睿员工手册.pdf` 第 `6.5`、`6.6` 节

## 检查步骤

1. 核对招待事项是否与公司收入或业务开展直接相关，并确认有公司员工出席。
2. 检查预计金额是否达到事前申请门槛，以及申请是否在招待发生前完成。
3. 检查报销摘要是否包含事由、地点、参与者、商务内容等必要信息。
4. 对礼品、购物卡类支出，检查是否应由行政部统一采购。
5. 招待中包含住宿、差旅或市内交通费用时，继续套用 `travel.rules.json` 与相关差旅标准，不要单独放宽。

## 输出要求

- 输出 `matched_rules`、`entertainment_findings`、`missing_docs`、`policy_refs_candidates`
- 缺少参与人信息、商务目的、事前申请或费用边界不清时，输出 `manual_review`
