---
description: 价格横比：一个招标项目下多家投标人评标完成后，按招标价格公式统一算价格分、合成总分、排名、（条件满足时）推荐中标人
allowed-tools: Read
---

对一个招标项目下**已评标完成的多家投标人**做横向比较：按招标文件的价格评分公式统一算各家价格分，合成总分，排名，并在终局条件满足时给出推荐中标人。**输入已由服务端组装好内联在参数里**（各家已落库的评分事实），你**不需要重读投标文件**。

## 输入（服务端内联 JSON，$ARGUMENTS）

```jsonc
{
  "project_id": "...",
  "method": "综合评估法 | 经评审的最低投标价法 | 其他",
  "funding_type": "state_funded | other | unknown",   // 是否国有资金/国家融资项目
  "control_price": "标底/控制价（可空）",
  "criteria_price_item": { "item": "价格分", "max": 40, "scoring_rule": "招标文件价格评分公式原文" },
  "bidders": [
    { "claim_id": "...", "bid_price": {"amount": 1234.5, "currency": "CNY"},
      "scoring": [ {"item","max","score","status"} … ],   // 该家已评的非价格项
      "verdict": "approved | rejected | manual_review" }
  ]
}
```

## 任务（Claude 侧判断与计算，逐步）

### 1. 认定有效投标
- `verdict: "rejected"`（废标）的投标人**不参与价格评分与排名**，在输出里 `status: "rejected"`、`rank: null`、`note` 写明废标不参与。
- 其余进入横比。

### 2. 算各家价格分（依招标价格公式）
- 严格按 `criteria_price_item.scoring_rule`（招标文件原文公式，如"价格分 = 评标基准价/本投标报价 × 满分"，基准价定义各招标不同：最低有效报价 / 均价 / 标底下浮等，**以公式原文为准**）计算每家 `price_score`（上限 `criteria_price_item.max`）。
- **异常低价护栏（`tender_evalmethod_010`）**：某家报价明显低于其他报价或低于 `control_price`、可能低于成本 → 该家 `price_score: null`、`status: "manual_review"`、`note` 写"报价异常偏低，需书面说明并提供证明（暂不计价格分）"，并加 `warnings`。**不强行算、不直接判废标**。

### 3. 合成总分 + 排名
- `other_score` = 该家 `scoring[]` 中**可判定项**（`status:"scored"`）的 `score` 合计（`manual_review`/`null` 项不计入）。
- `total_score` = `other_score` + `price_score`；任一为 null（价格待澄清 / 非价格项有未判定）→ `total_score: null`、该家不参与确定排名（`rank: null`）。
- 对 `total_score` 非空的有效投标按降序给 `rank`（1 起）。

### 4. 推荐中标人（终局护栏，**不无条件等于排名第一**）
仅当**同时满足**才给 `recommended`（排名第一的 claim_id）、`provisional: false`：
- 有明确排名第一（`total_score` 可比且唯一最高）；
- 无任何投标人价格分 `manual_review`（异常低价待澄清）；
- 有效投标 **≥ 3**（`tender_evalmethod_012`：不足三个使投标明显缺乏竞争可否决全部，需人工）；
- `funding_type == "state_funded"`（`tender_evalmethod_013`：国有资金/国家融资项目才"应确定排名第一为中标人"）。

否则：`recommended: null`、`provisional: true`，并在 `warnings` / `explanation` 写明原因（如"非国有资金项目，定标由招标人依法确定，本横比仅供参考""有效投标不足三家，需人工核定是否重新招标""存在异常低价待澄清"）。

## 输出契约

1. 只返回一个 JSON 对象，符合 `.claude/contracts/tender/compare-result.schema.json`，不要输出 JSON 之外的任何文字。
2. `bidders` 与输入一一对应，逐家 `{claim_id, bid_price, price_score, other_score, total_score, rank, status, note}`。
3. **承重 `policy_refs` 只引通则层真实 `rule_id`**（如 `tender_evalmethod_004` 加权、`tender_evalmethod_010` 异常低价、`tender_evalmethod_012` 有效投标数、`tender_evalmethod_013` 国有资金定标）；价格公式原文与各家命中写入 `evidence_chain`（引 `criteria_price_item` 出处 + 各家报价），**不要塞进 `policy_refs`**（会被真伪闸拒）。
4. `explanation` / `note` / `warnings` 用中文，平实、专业、克制；定性留余地（"建议 / 需人工核定 / 供参考"），不越权替招标人定标。
5. 只用输入数据 + 通则层规则，不重读投标文件、不使用训练记忆中的规则、不编造报价或公式。

参数: $ARGUMENTS
