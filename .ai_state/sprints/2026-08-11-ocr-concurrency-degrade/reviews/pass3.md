# Review Pass 3 — 2026-08-11-ocr-concurrency-degrade (H3)

审对象：pass3 返工 2 commits（d87299e/2fecb12）+ 主 agent 修复 commit（e30d32b）。

## pass2 核验结果（reviewer）

N1-N7 **七项全 CLOSED**：N1 快照→补跑→结算语义正确（档位序/None 文本/无条件结算三点核实，
红测真实且有鉴别力）、N2 逐段结算、N3 spent_sec 真实 elapsed 透传、N4 双 234 行无自授豁免且
写侧真搬走、N5 净增恰 60 不开豁免、N6 spy 非 no-op、N7 文档。import 无环（collect 1237 无
collection error）。

## pass3 新增 findings 与处置

- F1 [P1] 取消绕过结算（CancelledError 不被 except Exception 捕获，评标整单超时的 wait_for
  取消是常态触发路径，行永久卡 running）→ **已修（e30d32b，主 agent 绿区直做）**：结算移入
  finally 并改同步调用（取消态下 await 必再抛，同步 sqlite 微秒级是取消安全的必要代价，
  与 compare_worker._schedule_if_idle 同权衡先例）；新增取消路径红测。
- F2 [P1] partial 与 degraded 判等（与 pipeline.summarize_ocr_results 既有序矛盾，
  degraded→partial 劣化被保留）→ **已修**：_STATUS_RANK partial 降为 1，新增红测。
- F3 [P1] 结算读操作裸奔（DB 故障冲出拖垮整单评标 + 段间牵连）→ **已修**：_settle_segment
  整段 try 自防护，段间独立成败。
- F4 [P1] pass2-F3 预算上限测试空转（lambda 签名未跟 N3 改，TypeError 被吞、协程未 await）→
  **已修**：签名改 **_k，`-W error::RuntimeWarning` 全套通过证实无未 await 协程。
- F5 [P2] blanket try 罩住预算计算 → **已修**：budget 提出 try，编程错误 fail-fast。
- F6 [P2] failed_files 解析二次实现且行为不一致 → **留 polish**（与 F7/F10/N8/F9 残留同批，
  polish 收敛为 store 侧公开 decode_failed_files）。
- F7 [INFO] 三点观察记录（bid 快照 ocr_clarity 冗余无害 / 1s 下界 / worktree venv 缺 fitz 致
  引擎级用例本环境未实跑——**ship 前须在装齐 ocr extra 的环境复跑一次**，记入 runtime-verify）。

修复验证：32 passed（含 -W error::RuntimeWarning）、ruff 净、doc_rerun.py 248 行 ≤300。

## 结论

pass2 七项全闭合 + pass3 四 P1 一 P2 全部闭合（一 P2 留 polish）。无未闭合 P0/P1。待 evaluator。

## VERDICT (evaluator, 2026-08-12)

**PASS**。Evidence Cross-Check 全对上（e30d32b 五项修复代码级抽验属实、行数账/collect 实测吻合、
done_without_evidence=0）；E1 证据 YAML 结构错 + E2 collect 陈旧已由主 agent 立即修复（365c994）。
显式表态：接受 doc_layer/doc_rerun 拆分与 case_path/run_info_extraction；pass3-F7"完整环境复跑"
列 runtime-verify 前置。合并：H3 分支先 merge main(H1+H2) 做共享契约复核（10ccf8c，runner 四冲突
手工合一 + G2 复核 compare 链路对 ocr_status 零耦合 + 四处测试 patch 目标随迁移对齐 35fc39e），
再合入 main（80e46a5）。main 终态：collect 1363, 完整环境 16 条既有失败基线不变, 前端 189 pass。
