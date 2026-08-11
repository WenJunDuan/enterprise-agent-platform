---
description: 价格横比：一个招标项目下多家投标人评标完成后，按招标价格公式统一算价格分、合成总分、排名、（条件满足时）推荐中标人
allowed-tools: Read
---

对一个招标项目下**已评标完成的多家投标人**做横向比较：按招标文件的价格评分公式统一算各家价格分，合成总分，排名，并在终局条件满足时给出推荐中标人。**输入已由服务端组装好内联在参数里**（各家已落库的评分事实），你**不需要重读投标文件**。

## 输入（服务端内联 JSON，$ARGUMENTS）

```jsonc
{
  "project_id": "...",
  "method": "综合评估法 | 经评审的最低投标价法 | 其他",   // 取自项目权威 criteria，非各家转录副本
  "criteria_version": "a1b2c3d4e5f6...",              // 本次横比依据的项目规则版本（服务端算）
  "funding_type": "state_funded | other | unknown",   // 是否国有资金/国家融资项目
  "control_price": "标底/控制价（可空）",
  "criteria_price_item": { "item": "价格分", "max": 40, "scoring_rule": "招标文件价格评分公式原文" },
  "price_comparison_blocked": false,
  // 封锁原因（封锁时非空）：insufficient_comparable_bidders（可比家数 < 2）/
  // price_max_unknown（价格项满分未设）/ no_price_item（评标办法无横比价格项）/
  // bid_price_unit_mismatch（各家报价数量级差 ≥100 倍，疑似万元与元混用）
  "price_comparison_blocked_reason": null,
  "warnings": ["服务端护栏告警（已指名到具体投标人），须原样并入你的 warnings"],
  "bidders": [
    { "claim_id": "...", "bid_price": {"amount": 1234.5, "currency": "CNY"},
      "scoring": [ {"item","max","score","status"} … ],   // 该家已评的非价格项
      "verdict": "approved | rejected | manual_review",
      "comparable": true,          // false = 服务端判定该家不参与横比
      "exclusion_reason": null }   // criteria_stale（评标依据非当前规则版本）/ bid_price_invalid（报价缺失或非法）
  ]
}
```

## 任务（Claude 侧判断与计算，逐步）

### 0. 前置：服务端判据（不要自行推翻）
可比性、价格项、报价合法性**均已由服务端按项目权威 criteria（`criteria_version`）判定**，你只按判据算分：

- 若 `price_comparison_blocked: true` → **不做横比与排名**：所有 bidder `price_score/total_score/rank: null`、`status: "manual_review"`，`recommended: null`、`provisional: true`；`explanation` 与 `warnings` 按 `price_comparison_blocked_reason` 如实说明：
  - `insufficient_comparable_bidders`：可比投标人不足 2 家（有的评标依据不是当前规则版本、或报价无效），需人工处理后再横比；
  - `price_max_unknown`：招标评分标准里的价格项满分未设定，需人工确认；
  - `no_price_item`：评标办法中未找到需横向比较的价格项，需人工确认；
  - `bid_price_unit_mismatch`：各家报价数量级相差 100 倍以上，疑似万元/元口径不一致，**不得自行换算**，转人工。
  直接产出该结论，不进下面步骤。
- 若某家 `comparable: false`（`exclusion_reason` 为 `criteria_stale` 或 `bid_price_invalid`）→ **该家不参与价格分与排名**（`price_score/total_score/rank: null`、`status:"manual_review"`、`note` 写明原因与需要的人工动作），**其余可比家照常横比排名**——不要因为一家有问题就把整池判人工。
- 输入 `warnings` 里的服务端告警**原样并入**输出 `warnings`（它们已指名到具体投标人）。

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

1. 只返回一个 JSON 对象，符合 `.claude/contracts/tender/compare-result.schema.json`，不要输出 JSON 之外的任何文字。**必须显式给出 `recommended`（终局推荐 claim_id 或 null）、`provisional`（true/false）、`warnings`（数组，无则空数组）**——不可省略；`provisional: true` 时 `recommended` 必须为 null。
2. `bidders` 与输入一一对应，逐家 `{claim_id, bid_price, price_score, other_score, total_score, rank, status, note}`。
3. **承重 `policy_refs` 只引通则层真实 `rule_id`**（如 `tender_evalmethod_004` 加权、`tender_evalmethod_010` 异常低价、`tender_evalmethod_012` 有效投标数、`tender_evalmethod_013` 国有资金定标）；价格公式原文与各家命中写入 `evidence_chain`（引 `criteria_price_item` 出处 + 各家报价），**不要塞进 `policy_refs`**（会被真伪闸拒）。
4. `explanation` / `note` / `warnings` 用中文，平实、专业、克制；定性留余地（"建议 / 需人工核定 / 供参考"），不越权替招标人定标。
5. 只用输入数据 + 通则层规则，不重读投标文件、不使用训练记忆中的规则、不编造报价或公式。

参数: $ARGUMENTS
