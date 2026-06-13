# Golden-case 审核回归评测

改 `AUDIT_INSTRUCTIONS`、换网关模型（qwen ↔ 云）、或调 `AUDIT_*` 开关前后，
跑这套评测看审核决策是否漂移，作为安全网。

## 运行（在部署机，需要可用的模型网关）

```bash
uv run python -m server.audit_eval --manifest tests/eval_fixtures/golden_manifest.json
```

- 全部 case 的 `verdict`（及可选的 `manual_review_reason` / `risk_score` 区间）
  匹配期望则退出码 0；任一不匹配或网关报错退出码非 0。
- 评分逻辑是纯函数、已被 `tests/test_audit_eval.py` 单测覆盖；CI 不跑真实网关，
  本评测需手动在部署机执行。

## manifest 格式

```json
{
  "cases": [
    {
      "case_dir": "data/cases/2026-06-travel-001",
      "expected_verdict": "approved",
      "expected_manual_review_reason": null,
      "min_risk_score": null,
      "max_risk_score": 40,
      "note": "标准差旅，金额在限额内"
    }
  ]
}
```

- `case_dir`：相对项目根的案件目录（含 `audit-request.json`），必须在项目根内。
- `expected_verdict`：`approved` / `rejected` / `manual_review`（必填）。
- `expected_manual_review_reason`：可选，填了才比对。
- `min_risk_score` / `max_risk_score`：可选风险分区间，填了才比对。

## 用真实案例校准

`data/` 被 gitignore，真实案例不入库。建立自己的评测集：

1. 在部署机新建一个 manifest，`case_dir` 指向 `data/` 下跑过、人工确认过结论的案例。
2. 先以当前已知良好的配置跑一次，把输出的 `verdict` / `manual_review_reason` /
   `risk_score` 回填为 `expected_*`，作为基线（golden）。
3. 此后每次改提示词 / 换模型，重跑比对基线。决策漂移会以 `[FAIL]` 标出。

本目录的 `placeholder-invoice` 是合成模板，仅用于演示布局，不要当真实基线。
