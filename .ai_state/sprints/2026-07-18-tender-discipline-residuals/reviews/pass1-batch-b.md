# D11 Batch B · Review pass1 (落盘记录)

- **分支/merge**: `d11-batch-b` (5 commit) → main merge `79b44a1`（本地；push 仍 ship-gated）
- **分派**: codex 实现（de78184 F04 / 2677c64 reviewed_by / 009f105 config 警告）；主 agent review 补（e0b0dac F4 幂等测试 / eb839cc INFRA-02 doc）
- **日期**: 2026-07-19

## 三件套结论

| 环节 | 结论 | 要点 |
|---|---|---|
| reviewer | **CLEAN**（无阻塞 P0/P1） | F04 派生正确 + 页锚保真无 bug；F4 幂等成立（`_is_empty_evidence_chain` 守卫 + 整体覆写双保证，手工全链路复现 len==1）；reviewed_by 不波及 expense（共享 `_DEFAULT_REVIEWED_BY` 未改）；config env 名/默认值对。2 条非阻塞：[P2] `_hit_moves_score` 跨模块私有 import（既有模式延伸、design 要求复用、不修）；[INFO] evidence_chain/scoring 同 quote 双计 unresolved 1→2（预期副作用非 bug，polish 补 docstring） |
| spec-compliance | **全 COVERED**（原 2 缺口已闭合） | TB1 五断言全 COVERED；TB2a/b/c COVERED；INFRA-01 COVERED。① F4 追加断言（此前 PARTIAL 系快照早于 commit）→ e0b0dac 已 commit + 独立跑 1 passed；② INFRA-02 注记（此前 MISSING）→ eb839cc 补 enterprise-agent.env.example。全量 907 passed / 5 fitz-env（与 main 同集，非回归） |
| evaluator | **PASS 4.55/5**（Func 4.7 / Spec 4.6 / Craft 4.4 / Robust 4.5） | Evidence Cross-Check：5 checklist 项全有 commit diff + 可复跑测试；done_without_evidence=0；unresolved_over_engineering=0 |

## 主 agent 独立验

- 触及模块 136 passed（含 F4 test 真触发 downgrade→verdict 翻 manual_review→二次 enrich，断言 len==1）
- 全量 907 passed / 5 failed（`ModuleNotFoundError: fitz`，test_ocr_engine/pipeline，与 main 一致=环境缺 pymupdf，非回归）
- ruff 净

## 遗留（非阻塞）

- polish：evidence_chain/scoring 双计副作用补 docstring（reviewer INFO）
- D1 golden 网关级回归：部署机窗口验（历史惯例，需真网关）
- 本 sprint checklist.yaml / evidence.yaml 待补（sprint 收尾）

## Sisyphus

- [x] Batch B 五项 design 验收全绿 + 独立复跑核实
- [x] 无 P0/P1、无 done_without_evidence
- [x] merge 79b44a1（本地）；push 待 ship 窗口
