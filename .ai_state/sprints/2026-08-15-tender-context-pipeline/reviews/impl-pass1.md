# Impl Review Pass 1 — 2026-08-15-tender-context-pipeline

- 日期: 2026-08-15 · 评审: critic (Fable 5) · 范围: `f55cdf34..HEAD`（8 commits）

## VERDICT: REWORK

测试 89 passed、召回脚本可复现、S1/AC3/双通道本体扎实——但**本 sprint 的主承重墙（S3c 接线 + 降级归宿）没有交付**，且被死函数上的绿测试掩盖。这正是本仓最忌的「静默假过」形态。

## F1 [P0] 降级归宿未接线：`load_evidence_context` / `enforce_manual_review` 是死代码

`doc_layer._build_doc_context`(114-126) 只取 `evidence.context`，**`warnings` 与 `force_manual_review` 落地即丢**。全仓 grep 证实：`load_evidence_context`（专为带出这两个信号而建）**零调用方**；`enforce_manual_review` 只被自己的单测调用（主 agent 已独立复核确认）。

反例（critic 实跑）：两层 ready + 投标底稿空白 → `force_manual_review=True` → `_build_doc_context` 返 None → 记 `doc_layer_fallback`（"预热底稿不可用"，误导）→ **runner 走 inline_ocr 重跑整目录**（F7 明令禁止的"凑合评一个"），`evidence_index_unavailable` warning 蒸发。`evidence_unresolved` / `evidence_all_unresolved` / `evidence_budget_exhausted` 四类信号同样不达结论与前端——**AC2 在接线层不成立**。

commit `accd634` 标题「降级归宿改为不出分」与交付物相反；`test_强制人工复核会落到结论上` 测的是死函数，制造已接线的假象。

**改**：runner/`_resolve_doc_layer` 消费 `EvidenceContext` 结构；evidence warnings 并入 `_inject_ocr_warnings` 落结论；`force_manual_review` 时调 `enforce_manual_review` 而非回落 inline。补**穿透 runner** 的测试，断言 warnings 出现在 payload。

## F2 [P0] 回落闸收编成「整窗」，比收编前松 2.3 倍

`fallback_max_bytes()` = tokens_to_bytes(200,000) = **600,000B**（旧 256,000）；`_preextract_char_budget()` = **200,000 字符**——两者**都未扣 scaffold(90K)+margin(50K)**。按 injection_budget 自己的账，回落注入 >~110K token 时 CLI 一次性硬拒。

反例：inline 回落底稿 400KB → 旧默认截到 256KB≈85K token+脚手架≈150K（CLI 收）；新默认截到 600KB≈200K+90K≈**290K → 必拒，整单无结论**。「闸形同虚设」在单点化模块内重演；与 F1 组合 = `force_manual_review` 的大单被送进必死回落。

**改**：回落/preextract 预算 = `effective − scaffold − margin`（与 `plan_injection` 同构造）；AC5 补「最终 prompt 计 token ≤ 上限」断言。

## F3 [P1] AC0b 的 100% 是构造保证的，应改判 blocked

`measure_tender_recall.py:49-57` 把 20 个查询词**逐字埋进正文**（含"价格-最后报价以投标函为准"），≥3 字通道 verbatim 必中；ground truth 用子串匹配又把"措辞不同"类漏检排除出分母。**该度量结构上抓不住 S0-B 真实数据暴露的那类失败**（真实项 verbatim 缺失 → 38%）；对照组只证明 2 字通道有效。

另：**KD2「多词拆 OR」未实现**（`_escape_match_query` 仍单 phrase），是真实底稿复测的最大风险点。

**改**：AC0b 改申报 **blocked on 部署机真实底稿**（脚本已支持 argv 传底稿），不得计 PASS；复测前先补多词拆 OR。

## F4 [P1] 「全部零命中不接管」归宿= 回落旧路径，复演 08-15

`evidence_context.py:124-139` 全空时回落整份注入。判断前半（空证据不接管）对，但对超预算大标书，回落 = 截断错评（F7 原文）或撞 F2 必死；且该档 warning 也被 F1 丢弃。**索引建成而检索全空是结构性异常**，归宿应为 `manual_review`——至少对底稿体量超回落预算的单子必须如此。

## F5 [P1] 预算耗尽后逐项静默饿死

`evidence_index.py:220-224`：额度用尽后有命中的项其块被丢，既不进 `unresolved` 也无 warning。默认参数下可达（evidence≈40K token，20 项×4K chunk=80K）。排序靠前的项有证据、靠后的无且无痕——违反 AC2「无静默路径」。**改**：记 `evidence_truncated` 进 warnings。

## F6 [P1] `except ValueError` 归因面未收窄

`evidence_chunks.py:112-121` 修复靠一行 `row_factory` + 注释，except 仍罩住 `index_document`+`dict(row)` 全段——未来任何 ValueError 会再次被误当"structure/body 不匹配"静默退化。行为级回归（3 章→3 chunk）已有，好；但应给 `_chunk_spans` 的 mismatch 抛专用异常并只捕它。

## P2

scan 通道 `ORDER BY chunk_id` 是字典序非文档序（"#10"<"#2"，limit 截断时选块任意，应改 rowid）；`chunks_per_query_budget`(÷3,453) 与 `retrieve_evidence` 自算 per_item_chunks(÷4,000) 同概念双推导；`doc_pipeline.py` 债 490→539（既有越线再 +49）；`_SCAFFOLD_RESERVE_TOKENS=90,000` 中 57,988 可复跑、余 32K 属估算应在标定档注明待实测（方向保守，可接受）；`cca15e7` docs commit 顺带改 runner 行数（轻微混装）。

## 申报诚实度

AC6/AC7 blocked 申报**属实**且解锁路径在档；前端竞态修复方案正确、无 hook 单测的申报属实；tdd-evidence 基线 34/34 diff empty 可信。唯 **AC0b 计 PASS 偏乐观**（F3）、**S3c 计「接入主链路」不实**（F1）。

## 返工重点（≤3）

1. **F1 接线 + 穿透测试**（核心）
2. **F2 回落预算扣脚手架**
3. **F4 归宿改 manual_review**，并与 F1 一并让信号落结论
