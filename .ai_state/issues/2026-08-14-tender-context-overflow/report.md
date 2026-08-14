---
date: 2026-08-14
type: issue-report
slug: tender-context-overflow
path: Bugfix
---

# 现象：评标整单无结论，模型侧报 Prompt is too long

## 用户可见现象

内网部署（DeepSeek Flash）跑评标，四单全部**没有结论**：任务分析十几分钟后失败，
错误面板显示契约异常，重试三次在 700ms 内全部打完，仍无结论输出。

## 日志摘录（事故当天，节选）

```
INFO  tender_ocr_source  request_id=... source=inline_ocr bid_id=...
WARN  tender attempt failed (JSONContractError, 1/3), retrying: API Error: 400 ... 'Prompt is too long' ...
WARN  tender attempt failed (JSONContractError, 2/3), retrying: API Error: 400 ... 'Prompt is too long' ...
ERROR JSONContractError: API Error: 400 ... 'Prompt is too long' ...
```

两个可直接读出的事实：

1. `source=inline_ocr` —— 本单**没有**复用预热底稿，走的是云 OCR 写超时后的降级路径。
2. 三次重试的错误消息**逐字相同**，间隔 700ms 量级 —— 重发的是同一个过长 prompt。

## 影响面

- 触发条件：云 OCR 超时 / 预热底稿不可用 → `inline_ocr` 降级；案卷越大越必然。
- 结果：整单无结论（不是降级结论，是失败），且失败原因被三条一样的重试日志淹没。
- 与 2026-08-13 prompt-architecture 重构的关系：见 `analyze.md`，重构是放大器不是唯一元凶；
  本次两处修复独立于该重构的回滚，回滚后仍需修。

## 相关档案

`.ai_state/compound/2026-08-14-learning-prompt-budget-must-be-per-session.md`（事故全貌与预算实测数字）
