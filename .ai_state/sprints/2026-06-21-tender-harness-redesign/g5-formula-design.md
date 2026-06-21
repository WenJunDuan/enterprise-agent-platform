# 第3轮 design · G5 完整：formula 公式变量结构化

> 承 codex 第2轮 review 的 **backlog P1-2**：S2 只抽 `bid_price` 总额，限价类 formula 要"代入算"
> 却没有结构化的限价值 / 本家分项报价喂给 S3，S3 的"代入算"只能靠模型临场从底稿翻找 = 不可靠。

## 背景（WHY）

第2轮在 S1 把价格 formula 分了两类 tag（限价类 `scored` vs 群体变量 `requires_cross_bid_comparison`），
S3 也分了两路（限价类代入算 / 横比 manual_review）。但**中间断了一节**：

- S1 只抽了 `formula` **公式原文字符串**（如「每低于最高限价 1% 得 1 分，最多 10 分」）。
- S2 只抽了 `bid_price` **总额**。
- S3 要"用本家报价 + 招标限价代入算分"，但**限价值（limit_value）藏在招标文件、本家分项报价（bid_component）藏在投标文件**，
  两者都没被结构化抽出 → S3 只能让模型临场再翻底稿找数、心算，命中率低、随机性大（正是这轮要治的 deepseek 随机）。

一句话：**公式有了、两端的数没结构化 → 算不稳**。

## 方案（HOW）

把 formula 从"公式原文 + 模型临场算"升级为"**结构化变量清单 + 确定性代入**"。

### 1. criteria.schema.json — formula 项加 `formula_spec`（可选对象）

```jsonc
"formula_spec": {
  "expression": "score = min(10, floor((limit - bid) / limit * 100 / 1))",  // 公式原文/可读形
  "variables": [
    {"name": "limit", "source": "tender_constant", "value": 300, "unit": "元/用户·月", "ref": "招标文件 第N页 最高限价表"},
    {"name": "bid",   "source": "bid_component",   "value": null,  "unit": "元/用户·月", "ref": null}  // S2 回填
  ],
  "cap": 10  // 该项满分/封顶（与 max 一致或更细）
}
```

- `source` 枚举：`tender_constant`（招标常量：限价/预算/基准系数，**S1 当场填 value**）/
  `bid_component`（本家报价分项，**S2 回填 value**）/ `cross_bid`（群体变量：最低价/均价/投标人数，**算不了**）。
- **tag 自然派生、不再靠模型主观判**：`variables[].source` 全 ∈ {tender_constant, bid_component} → `tag:scored`；
  任一 `cross_bid` → `tag:requires_cross_bid_comparison`。这把第2轮"判别条件"从散文升级为**可判定的结构规则**。

### 2. S1（取标准）：formula 项多抽一个 `formula_spec`

拆公式为变量清单，标每个变量 `source`，**招标常量当场填 `value`**（限价表就在招标文件里，S1 正在读它）。

### 3. S2（事实抽取）：回填 `bid_component` 变量的 `value`

对 `tag:scored` 的 formula 项，从投标文件抽对应分项报价填进 `formula_spec.variables[source=bid_component].value`
（+ 来源页）。`cross_bid` 项不回填（本就算不了），仍只钉 `bid_price` 总额备横比。

### 4. S3（评判）：变量齐全就代入算

- `tag:scored` 且 `formula_spec.variables` 全部有 `value` → 代入 `expression` 算分，`status:scored`，
  `basis` 写「limit=300、bid=270、按公式得 N 分」+ 两处出处页。
- 缺任一 `bid_component` value（投标没报这项）→ 不臆造，`manual_review`（`insufficient_evidence`），写明缺哪个变量。
- 任一 `cross_bid` → `manual_review`（横比），钉 `bid_price`，与第2轮一致。

## 影响范围

- `.claude/contracts/tender/criteria.schema.json`（formula 项加 `formula_spec`；`additionalProperties:false` 故须声明，设 optional 不破旧数据）
- `.claude/commands/tender-evaluate.md`（S1 line24 / S2 line53-56 区 / S3 的 formula 段）
- `tests/test_tender_criteria_flow.py`（formula_spec：scored 代入 / 缺 bid_component / cross_bid 三路 + schema 校验）
- evaluator.md formula 摘录同步一句（仍标命令 S3 权威）

## 风险与缓解

- **风险**：Python 不验算，模型代入仍可能算错。**缓解**：结构化变量让算式清晰（变量名+值+来源全列好），
  `basis` 写清每个变量值供人工二核；不追求 Python 重算（撞既有 gotcha「evidence_chain 算术重算」backlog）。
- **风险**：`formula_spec` 与既有 `formula` 字符串字段冗余。**缓解**：`formula` 保留为人读原文，`formula_spec` 为机读结构，
  二者并存（formula=出处原文，formula_spec=结构化抽取），不删 formula 防破坏旧结论。
- **风险**：schema `additionalProperties:false` 拒未声明字段。**缓解**：formula_spec 整体 optional，variables 项内字段全声明。

## 验收

- 单测：formula_spec 三路（scored 全变量齐→代入；缺 bid_component→manual_review；含 cross_bid→manual_review）+ schema 接受/拒绝漂移。
- dogfood：若华为南通标含限价类价格项，S1 抽出 formula_spec（limit 填值）、S2 回填 bid、S3 代入算出分（不再全 manual_review）。
- 回归：451 passed 不破 + ruff。

## Round 3 · Critic Findings (critic, 2026-06-21T08:30:00Z)

### VERDICT: APPROVE-WITH-CHANGES

### 评分

| 维度 | 评分 (1-5) | 关键 finding |
|---|---|---|
| 边界条件 | 3 | 分段阶梯价（多段限价）、复合 formula（cross_bid + 限价变量混用）未覆盖 |
| 错误处理 | 3 | formula_spec 与 formula 字段不一致时无校验路径；expression 执行语义模糊 |
| 测试覆盖 | 4 | 三路测试清晰，但缺复合 formula 混用反例；缺阶梯价路径 |
| 历史决策对齐 | 4 | 与 verification-gate 决策（验证非判断）一致；与 absence-is-not-zero 一致 |
| 复杂度 | 3 | source 三枚举对复合公式覆盖有缺口；S1→S2 多步变量状态同步无文档说明 |
| 历史教训 | 4 | 正确复用 absence-is-not-zero 模式；未见与已沉淀教训的冲突 |

### CC critic + codex 共识 findings（双 APPROVE-WITH-CHANGES）

| # | finding（来源） | 严重度 |
|---|---|---|
| 1 | tag 派生太松：复合 formula(cross_bid+限价混用)/不可闭合变量被误判可单家算（CC F1 + codex P1-2） | P1 |
| 2 | source 三枚举不够，漏 external_data/live_event/derived（codex P1-2） | P1 |
| 3 | 缺 formula_spec 时 S3 回退临场心算，schema optional 不成门禁（codex P1-3） | P1 |
| 4 | S3 仍是模型心算，"确定性"偏强，需逐步列计算供人工验算（CC F2 + codex P1-1） | P1 |
| 5 | formula vs formula_spec 双来源优先级未声明（CC F3 + codex P2-4） | P1/P2 |
| 6 | 复合/阶梯价应拆子项 / 走 banded，不硬塞 expression（CC F1 + codex P2-5） | P2 |
| 7 | MVP 可更窄(只固定限价类)（codex P2-6） | P2 |
| 8 | schema 缺 formula_spec 定义，source enum 无约束（CC F4） | P2 |

### Round 3 采纳决议 → impl 落实（全部采纳，impl 时处理，不再过一轮 critic）

| finding | 落实位置 |
|---|---|
| 1 tag 白名单派生 | tender-evaluate.md S1：「变量全 ∈ {tender_constant, bid_component} 才 scored；任一不可闭合 → manual」 |
| 2 source 扩枚举 | criteria.schema.json formula_spec.variables.source enum 加 external_data/live_event/derived |
| 3 缺 spec 不 fallback | S3「缺 formula_spec/语义不一致/变量缺值 → manual_review」+ output_contracts `formula_scored_no_spec` 兜底 warning |
| 4 逐步列计算 | S3「basis 必须逐步列出代入过程(limit=300、bid=270、…)供人工验算无需重算」 |
| 5 formula 唯一权威+spec 优先 | schema formula desc「唯一权威」；S3「以 formula_spec 为准代入」 |
| 6 拆子项+阶梯 banded | S1「拆子项优先」+「阶梯分段走 banded 不走 formula」 |
| 7 MVP 窄化 | S1「本轮只对固定限价比例差/多限价分项求和自动算」 |
| 8 schema 定义+enum | criteria.schema.json formula_spec object，variables required[name,source]+source enum；测试 rejects_bad_source/missing_required |

**额外正确性**：formula_spec 含本家报价 `value` → 必须排除出 criteria 横比指纹（tender_compare_store `_HASH_SKIP_FIELDS`），否则同标各家报价不同 → hash 漂移误判 stale。
**impl 验证**：461 passed（11 新 formula 测试：schema×3 + 闭合无警/无spec警/含横比警/缺值警/manual不警 + hash 剥本家value同标/标准变漂移）+ ruff。codex impl review **REWORK→全修**：P1-1 formula 兜底补 `formula_scored_missing_value`（source 全可闭合但变量未填值也拦）；P1-2 criteria 横比指纹改「精准剥 formula_spec.variables[].value/ref，保留 expression/cap 标准侧」（不再排整个 spec，防漏判 stale）；P2-3 tender-eval SKILL.md 旧「价格分须所有投标统一计算」补固定限价类例外。
