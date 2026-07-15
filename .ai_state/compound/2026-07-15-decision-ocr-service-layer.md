# Decision · OCR 降为 feature 域之下服务层（分层教义修订）

- **日期**: 2026-07-15
- **拍板人**: 用户（AskUserQuestion，方案 i vs ii）
- **范围**: program 级（2026-07-doc-intelligence），一次拍板管 D1 + D2
- **触发**: D1 design Round 2 F5 [P0] —— T2 拟下沉的 `_run_evaluation` 内嵌
  `ocr_preprocess_block`（routes/tender_worker.py:19/:198 → server.ocr.pipeline）与
  `TENDER_OCR_PURPOSE`（routes/tender_doc_pipeline.py:33），整体迁入 server/tender/ 会
  同时产生 tender→ocr（撞 T5 拟加的 tender↔ocr 互斥守卫）与 tender→routes（逆向依赖）。

## 决策

**方案 i**：ocr 从 tender/audit 的平级 sibling 降为 feature 域之下的**服务层**。

```
app (api/cli) → routes → ops → features(audit|tender) → ocr(服务层) → core → common → stores → platform
```

- 允许 tender/audit → ocr；**禁止 ocr → tender/audit**（守卫由互斥改单向）。
- `_run_evaluation` 连 OCR 回落一起下沉 server/tender/runner.py，不做注入。
- `TENDER_OCR_PURPOSE` 挪家 server/tender/，tender_doc_pipeline 改从 feature 层 import。
- eval CLI 保持 `python -m server.tender.eval`，与 audit 入口对称。

## 依据

1. **承认既成事实**：audit_worker / tender_worker / tender_doc_pipeline 三处已按服务消费
   ocr——"sibling 互斥"教义与现实不符，守卫从未真正约束住这条边（routes 层绕行）。
2. **改动最小**：方案 ii（坚持 sibling、routes 注入）需 eval CLI 上浮 app 层
   （`python -m server.cli eval-tender`），破坏与 audit 的入口对称，且 D2 迁
   tender_doc_pipeline 时还要再造一条注入缝。
3. tender 与 audit 不同：真实标书是扫描件，eval 回归闸必须打含 OCR 的生产同路径，
   OCR 依赖绕不开。

## 放弃的备选

- **方案 ii**（routes 注入 + CLI 上浮）：教义纯洁但代价双倍（入口不对称 + D2 二次注入缝）。

## 后续义务

- D1 T5：layering 守卫落地单向规则（含既有 audit↔ocr 互斥断言改单向）。
- architecture/ARCHITECTURE.md 分层节已加拍板注记；守卫落地后改正式分层图。
- audit feature 层现无 ocr 依赖，本次不改 audit 现状。
