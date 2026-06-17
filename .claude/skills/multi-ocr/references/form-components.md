# 表单组件与子表映射细则

目标：把 `extract-result` 内容映射成 `.claude/contracts/ocr/form-fill.schema.json` 的 `fields[]` / `sub_tables[]`。

## 6 类组件

| component | 取值规则 | 置信度处理 |
|---|---|---|
| `single_line` | 取最高置信的命名实体值；去换行/首尾空白 | < 阈值 → low_confidence |
| `multi_line` | 拼接相关段落/条款，保留换行 | 缺关键段落 → low_confidence |
| `select` | **必须命中目标字段 `options` 之一**；做同义归一后仍命不中 → 不填、标 low_confidence | 命不中即 low_confidence |
| `number` | 去千分位逗号、全角转半角、保留小数精度；不臆测单位 | OCR 来源一律带置信 |
| `date` | 归一 ISO `YYYY-MM-DD`；中文"二〇二四年三月"等先转换；区间/模糊不臆测 | 歧义 → low_confidence |
| `sub_table` | 见下「付款节点」 | 任一行关键列缺失 → 整表 needs_review |

## 合同付款节点 → 预测付款子表

每个付款节点抽成一行，建议列：

| 列 key | 含义 | 来源 | 校验 |
|---|---|---|---|
| `node_name` | 节点名（如"预付款/进度款/质保金"） | 条款标题/付款表行 | 必填 |
| `trigger` | 触发条件（如"合同签订后/竣工验收后"） | 条款文字 | 可空但建议有 |
| `ratio` | 比例（%） | 条款/表 | Σ ≈ 100% |
| `amount` | 金额 | 条款/表 | Σ ≈ 合同总额 |
| `plan_date` | 计划付款日期 | 条款/表 | ISO；相对日期(如"30 个工作日内")保留原文于 evidence |
| `currency` | 币种 | 全局/行 | 默认 CNY，冲突标记 |

抽取要点：
- 付款节点常**散落在条款文字**而非整齐表格——用语义抽取，不只依赖表格识别结果。
- 比例和金额做**自洽校验**：Σ比例≈100%、Σ金额≈合同总额；不自洽 → 该子表 `needs_review=true`。
- 每行每个数值字段带 `confidence`；金额/日期是高风险位，低置信即触发人工。

## low_confidence / needs_review 策略

- 字段置信度低于阈值（建议金额/日期 0.9、文本 0.75，按 POC 调）→ 写入 `low_confidence[]`。
- `low_confidence[]` 非空，或任一关键字段缺失/冲突 → `needs_review=true`。
- 宁可标人工，不要回填一个看似确定但可能错的金额（沿用平台保守原则）。
