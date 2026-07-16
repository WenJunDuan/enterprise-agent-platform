# Golden-case 评标回归评测

改评标 prompt（`/tender-evaluate` 命令）、换网关模型、或调 `TENDER_*` 开关前后，
跑这套评测看评标决策与 `scoring[]` 一致性是否漂移，作为安全网。核心方法论
（S7 学到的）：评标评测**不能只看 verdict/完成率**——同一份标书 3 次实得合计可以
相差数倍（compound/2026-07-01-learning-flash-tender-eval-inconsistency.md），所以
本评测除了单次 verdict/eligibility/scoring 校验，还看 **repeat-N 跨次一致性**
（出分项数极差 + 实得合计极差）。

## 运行（在部署机，需要可用的模型网关）

```bash
uv run python -m server.tender.eval \
  --manifest tests/eval_fixtures/tender/golden_manifest.json \
  [--repeat 3] [--model deepseek-v4-pro]
```

- `--repeat`：覆盖 manifest 里每个 case 的 `repeat` 字段（默认 3）。
- `--model`：环境无关的 A/B——同一 manifest 分别跑两个模型出两份报告，人工对比
  （不做双模型自动对比逻辑，KISS：S7 的对比是一次性分析，闸只需单模型回归）。
- 每 case 的 repeat-N **串行**跑（评标 ~3-5 min/次且打真实网关，不并发，防限流/
  互相干扰计时）；单 case 异常记 ERROR 不中断全局。
- 全部 case 通过（含单次 verdict/eligibility/scoring/policy_refs 硬校验）则退出码
  0；任一不匹配或网关报错退出码非 0。**跨次一致性极差首版是警告模式**——超标只
  打印 `[WARN]`，不影响退出码（见下方"基线收紧 checklist"）。
- 评分/一致性逻辑是纯函数、已被 `tests/test_tender_eval.py` 单测覆盖（含全 null
  run 极差边界、`repeat<2` 边界）；CI 不跑真实网关，本评测需手动在部署机执行。

## CC 内跑必须清空的 env（否则触发 offline_guard）

```bash
env -u ANTHROPIC_BASE_URL -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_MODEL \
  uv run python -m server.tender.eval --manifest tests/eval_fixtures/tender/golden_manifest.json
```

CC 会话内 CC 自己注入的 `ANTHROPIC_BASE_URL` 等会压过 `.env` 里配置的内网网关地址，
触发 `offline_guard_error`（内网部署禁止连接 `api.anthropic.com`）。这是
compound 学习 #3 记录过的坑，部署机在非 CC 终端里跑通常不受影响，但若在 CC
内部起子进程跑本评测，必须先 `env -u` 清空这四个变量。

## 大标书 / 小上下文窗口模型：MODEL_CONTEXT_WINDOW

切到小窗口模型（如 Flash）前，务必在 `.env` 设置 `MODEL_CONTEXT_WINDOW`（触发
`server.common.agent_bridge.warn_if_context_may_truncate` 的截断预警 guard）。
S7 的原始案例是"run3 崩塌"——怀疑与大标书底稿在小窗口模型下被截断有关；填真实
窗口值后，重跑本评测观察"run3 崩塌"（`item_spread`/`total_spread` 骤增）是否
随之消失。**这是用户侧待办**：本脚手架只提供复测手段，不能替用户填这个值。

## manifest 格式

```json
{
  "cases": [
    {
      "case_dir": "data/bids/2026-project-x/bidder-a",
      "expected_verdict": "manual_review",
      "expected_manual_review_reason": "rule_gap",
      "eligibility_expectations": [
        {"check": "营业执照", "expected_status": "pass"}
      ],
      "scoring_expectations": [
        {"item": "技术方案", "expected_statuses": ["scored"]}
      ],
      "min_total_score": 60,
      "max_total_score": 90,
      "require_policy_refs": true,
      "max_item_spread": 1,
      "max_total_spread": 5,
      "repeat": 3,
      "note": "标准投标，技术方案应稳定判分"
    }
  ]
}
```

- `case_dir`：相对项目根的投标案例目录（内含该家投标文件原件），必须在项目根内。
- `expected_verdict`：`approved` / `rejected` / `manual_review`（必填）。
- `expected_manual_review_reason` / `eligibility_expectations` / `scoring_expectations` /
  `min_total_score` / `max_total_score`：可选，填了才比对。
- `require_policy_refs`：默认 `true`（承重结论 `policy_refs` 非空率=100%硬规则）；
  合成占位/无制度可依据的 case 需显式设 `false`。
- `max_item_spread` / `max_total_spread`：repeat-N 跨次一致性阈值（出分项数极差 /
  实得合计极差），**首版警告模式**——未配置或未超标不影响退出码，配置后超标只
  打印 `[WARN]`（见下方 checklist，硬门收紧前不会 fail）。
- `repeat`：本 case 的 repeat-N 次数，默认 3；`--repeat` CLI 可整体覆盖。

## 用真实案例校准

`data/` 被 gitignore，真实案例不入库。建立自己的评测集：

1. 在部署机新建一个 manifest，`case_dir` 指向 `data/` 下跑过、人工确认过结论的
   投标案例目录。
2. 先以当前已知良好的配置跑 `--repeat 3`，把输出的 `verdict` /
   `manual_review_reason` / `eligibility_checks` / `scoring[]` 状态回填为
   `expected_*`，作为基线（golden）。
3. 此后每次改提示词 / 换模型 / 调 `TENDER_*` 开关，重跑比对基线。决策漂移会以
   `[FAIL]` 标出，跨次一致性漂移会以 `[WARN]` 标出。

本目录的 `placeholder-bid` 是合成模板，仅用于演示布局（占位文本，非真实标书），
不要当真实基线——它没有真实招标文件可依据，预期结论恒为 `manual_review` /
`rule_gap`。

## 基线收紧 checklist（round1 F4 止损，防警告模式无限漂移）

跨次一致性阈值（`max_item_spread` / `max_total_spread`）首版是**警告模式**：无
基线时锁死数字 = 拍脑袋，会把闸做成摆设或路障。但警告模式**不得长期化**——
**硬门锁定是 D4（L2 多模型路由）开工的前置条件**（见 roadmap
`2026-07-doc-intelligence/items.yaml` D1/D4 note）。锁门步骤：

1. 在部署机用当前生产模型（如 deepseek-v4-pro）对 manifest 里每个 case 跑
   `--repeat 5`（比常规 3 次多几次样本更稳）。
2. 记录每个 case 观测到的 `item_spread` / `total_spread` 实际分布，取一个略宽于
   观测最大值的阈值（例如观测极差 2，阈值设 3），填回 manifest 的
   `max_item_spread` / `max_total_spread`。
3. 改 `server/tender/eval.py` 的 `score_consistency`：超标时把 `ConsistencyOutcome`
   计入 `CaseReport.passed`（当前只影响 `warnings`，不影响 `passed`），**二次
   commit**，并在 commit message 里注明"锁硬门，基线来自 <日期> <模型> <repeat 次数>
   跑"。
4. 更新 roadmap `items.yaml` D1 note，标记硬门已锁定，解除 D4 开工前置阻塞。
