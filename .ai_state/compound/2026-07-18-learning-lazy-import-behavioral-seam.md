# Learning: 瘦身共享函数时,惰性 import 会静默继承新行为——"import 路径没变"不等于"行为没变"

- date: 2026-07-18
- type: learning
- sprint: 2026-07-18-tender-schema-split（F6 schema 分家）

## 场景
tender-schema-split 把共享的 `enrich_audit_decision` 瘦身（删 `_finalize_user_explanation`，tender 专属逻辑挪进
`enrich_tender_result`）。设计（fable5）判断：`evidence_resolution.resolve_audit_evidence` 里那处**惰性**
`from server.common.output_contracts import enrich_audit_decision`（evidence 降级触发 verdict 翻转后二次 enrich 用）
"import 路径字符串没变 → 不用改"。

## 坑
被 import 的**函数体行为已被本 sprint 改瘦**了。结果：拆分后 verdict 已翻 `manual_review`、评分已降 `null`，但呈现给
人工复核的 `explanation` 仍是陈旧"…合计 40 分"——**production 级静默失真**。全量 pytest 绿也测不出:唯一走这条翻转路径
的测试不断言 `explanation`；单测 `_finalize_user_explanation` 的用例直调 helper、不经这条二次 enrich 路径。

## 抓到它的是什么
**独立模型 critic**（设计是 fable5，critic 用 opus），而非同模型自审。opus 还**实测 monkeypatch** 复刻瘦身版 enrich
跑同一输入，坐实 explanation 保持陈旧,不是纸面推测。同模型自审大概率复制同一盲点。

## 教训（How to apply）
1. **瘦身/拆分一个函数时,审计它的所有调用点——包括惰性/延迟 import**,看的是**行为**不是 import 路径字符串。grep 出所有
   `import <该函数>`（含函数内惰性 import），逐个问"这个调用方要的是瘦身前还是瘦身后的行为"。
2. **行为保真型重构必须有断言"那个具体交互"的测试**,不能只靠"全量绿"——绿只证明既有断言没崩,证明不了从未被断言过的交互。
   TDD 守卫要能:错误接线→红,正确接线→绿。
3. **红区共享层重构用不同模型做 critic**,吃掉自模型盲点(见 [[2026-07-16-decision-carve-f6-schema-split-from-d2]])。

## 链接
- design: sprints/2026-07-18-tender-schema-split/design.md「Round 1 · Critic 修订应答」F1
- 修复:server/tender/evidence.py resolve_audit_evidence 二次 enrich 用 enrich_tender_result
- 守卫:tests/test_evidence_resolution.py::test_pipeline_evidence_downgrade_refreshes_score_summary_in_explanation
