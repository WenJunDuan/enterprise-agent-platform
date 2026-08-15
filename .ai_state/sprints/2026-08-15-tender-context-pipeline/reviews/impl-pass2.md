# Impl Review Pass 2 — 2026-08-15-tender-context-pipeline

- 日期: 2026-08-15 · 评审: critic (Fable 5) · 范围: `e4d9d96..HEAD`（9 commits）

## VERDICT: PASS

两 P0 + 四 P1 全部实质闭合，无夹带，无新增静默降级主路径。逐项核验均自查代码，未依赖 commit message。

## 逐条闭合核验

**F1 [闭合]** `load_evidence_context` 有真实生产调用方（`doc_context.py:123`，`_resolve_doc_layer` 内）；`enforce_manual_review` 被 `build_manual_review_result`(`evidence_context.py:249`) 消费，后者被 `runner.py:158` 在 `force_manual_review` 短路分支调用**且归档结论**（不归档 = completed 却无结论可看，该新静默路径被预先堵上）。穿透测试 `tests/test_tender_evidence_wiring.py` 从 `run_tender_evaluation` 一端断言 payload 的 `extracted_data.ocr_warnings` 含四类信号、`model==0 且 inline==0`、scoring 清空——**不再是死函数上的绿测试**。

**F2 [闭合，未反向翻车]** `fallback_injection_tokens() = 200,000 − 90,000 − 50,000 = 60,000 token` → `fallback_max_bytes() = 180,000 B`，preextract 同源转发（`context_slim.py:53`）。闭合由 `test_fallback_injection_plus_scaffold_and_margin_fits_the_ceiling` 与 **AC5 最终 prompt 计 token 穿透断言**（400KB 底稿实测）锁住；`test_fallback_gate_is_not_looser_than_before_the_single_point_refactor` 直接防 2.3 倍复发。180KB 比旧 256KB 紧 30%，是闭式账必然结果，且截断走内容优先 + 可见标记而非硬失败——方向保守，不算矫枉过正。

**F4 [闭合，取了比 findings 更严的归宿]** 全零命中**无条件** `force_manual_review`（`evidence_context.py:129-148`），未实现"超回落预算才强制"的条件分支。pass1 原文是"至少对超预算单子"，无条件版满足下界且理由在档（小标书回落 = 把结构性异常消化成照常出分）。小标书误判风险低：2 字项名走子串通道，合法对版的投标全项零命中本身即异常（错传文件/criteria 串项），停下来是对的。真实误判率由 AC0b 部署复测实证。

**F3 [两半都闭合]** 多词拆 OR 在 `rag.py:96-110`（短词剔除防空表达式，全短词回落单 phrase），4 条测试覆盖。AC0b：脚本无真实底稿时硬打 `AC0b: BLOCKED` + exit 2（`measure_tender_recall.py:154-163`），`test_synthetic_corpus_can_never_report_ac0b_pass` 锁死；tdd-evidence `measurements` 节 status=BLOCKED，why_blocked 与 unblock 俱全。**结构上不可能再自证**。

**F5/F6/P2 [闭合]** `EvidenceResult.truncated` + `evidence_truncated` warning（跨项去重命中不算饿死，语义正确）；`StructureBodyMismatchError` 专用类型 + 调用方只捕它，"无关 ValueError 上抛"有专测；scan 通道 `ORDER BY rowid`（`rag_store.py:126`）有文档序专测；chunks_per_item 收敛到 `InjectionPlan.chunks_per_item` 单点。

**夹带审查**：19 个改动文件全部映射到 findings；`doc_layer.py` −1 行是删失效 import。`runner.py` 压行 diff 逐段核过：裁掉的全是"从哪搬来/哪年拆分"类历史叙述（doc-style 明令合规），预算闸不搬的 why、单向层级守卫、截断标记超限外附加等承重注释全保留。

## 残留（P2，不阻断）

- **P2a** `load_evidence_context` 的 `except Exception → None`（`doc_context.py:236-242`）：证据层意外崩溃时静默（仅日志）回落 slim 全文注入，结论无痕——第五类信号。缓解：信任边界（SQLite/存储 criteria）、带栈日志、回落路径自带预算闸与可见截断标记；读层整体坏时 `doc_layer_fallback` warning 仍发。**建议下轮给该分支补结论级 warning**。
- **P2b** 全部命中项均因"首块即超额度"被 truncated 时，`blocks` 空 → 走 `evidence_all_unresolved` 分支，文案报"0 项全空"错归因（verdict 仍 manual_review，方向安全）；仅在 env 误标定到 ~12 万 token 窄带才可达。
- **P2c** `describe_context_rejection` 与标定注释都指向"按标定档附录复跑二分测法"，但 design.md 附录 B **没有写二分测法本身**（待查实项 #2 仍开）——悬空指针，AC6 部署标定前应补。
- **P2d** `runner.py` 恰 300 行零余量（下次任何改动即触发拆分）；`doc_pipeline.py` 539 行既有债未动（pass1 P2 原样残留，本轮未加重）。

## Blocked 项与部署建议

三项 blocked 申报诚实、解锁路径可执行：**AC0b** 最清晰（命令 + 88% 门槛 + 跌破则升级 map-reduce 的预案 + 结构性防自证）；**AC7** 测量口径与计时起点在 AC 文本中；**AC6** 剩余部分（200K 二分实测精确化）路径有声明但缺测法文稿（P2c）。三项全依赖部署机资产（真实底稿 163,170 字 / bundled CLI / 最小窗口模型），本地无法解锁。

**先部署到服务器做真实验证是正确下一步**：本地零新增失败（1 failed = main 基线环境项）、ruff 净、前端三件套绿；且本轮改造后所有降级形态都是**可见的 manual_review 而非静默错评**——部署最坏情形是 manual_review 偏多，不是错分，爆炸半径已收住。部署后按 **AC0b → AC6 二分 → AC7** 顺序解锁，AC0b 结果同时回答 F4 无条件归宿的误判率问题。
