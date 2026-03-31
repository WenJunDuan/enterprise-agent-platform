---
name: expense-audit-travel-compliance
description: Use when 需要审核差旅、住宿、城际交通、市内交通或出差补助是否符合本地差旅制度
---

# 差旅合规

## 读取规则

- `knowledge/expense/travel.rules.json`
- `knowledge/expense/transport.rules.json`
- `knowledge/expense/thresholds.json`
- 制度追溯源：`knowledge/external/数睿员工手册.pdf` 第 `6.6`、`6.7` 节

## 本地制度要点

- 一类地区仅包含北京、上海、广州、深圳
- 二类地区包含重庆、天津及省会城市
- 其他城市按三类地区处理
- 如果申请人属于客户渠道部或代理商渠道部销售人员，而结构化 rules 未完整覆盖其包干制度，直接 `manual_review`

## 检查步骤

1. 核对出差申请、完整行程、出发地/目的地、交通工具、住宿日期、补助天数。
2. 检查城际交通是否满足职级与飞机使用条件。
3. 检查住宿是否命中城市等级上限，并确认是否属于常驻地住宿等特殊场景。
4. 检查其他交通与补助：
   - 出差往返机场/车站的市内交通是否合规
   - 周末/节假日是否错误计入补助
   - 出差补助是否与其他差旅费同步报销
5. 核对差旅附件是否完整，包括出差申请单、明细表、原始发票及必要的交通/住宿凭据。

## 输出要求

- 输出 `matched_rules`、`travel_findings`、`missing_docs`、`policy_refs_candidates`
- 关键字段缺失、城市等级无法确定、行程链条不闭合时，输出 `manual_review`
