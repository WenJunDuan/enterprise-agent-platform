# Review Pass 2 — 2026-08-11-page-provenance (H2)

审对象：返工 7 commits（81643a2..8988f01，rebase 后基于 main=c4689fc）+ 主 agent 补账
commit（pass2-N4 证据数字更正）。reviewer 实跑：worktree 全量 33f/1250p/3s（缺依赖环境），
`uv run --with pymupdf --with python-pptx` 补齐后 7 个 OCR 测试文件 192 passed 全绿——pass1
"关键路径本机跑不了"的验证缺口已由 reviewer 实测补上；ruff 净；前端 179 pass/build ✓/eslint 净。

## pass1 核验结果：八项全 CLOSED

F1（11 条证据，抽查 2 真红与旧代码语义逐字吻合、2 backfill 合规未编造）、F2（source 点名文件内
命中 + 3 例测试）、F3（rag/docstructure/rag_store artifact 贯通 + 区间锚协议化 5 例）、F4（异常态
无条件留痕 + 反向回归锁开关未架空）、F5/M2/M3、M1（双入口接线 + 3 例）、F6/M4（部署预告 +
架构档，pass1 时间戳失实已消除）、D3（豁免表实测逐项吻合：corpus 543≤560 / evidence 473≤490 /
context_slim 300 / pipeline 812 / engine 891）。

## rebase 共存核验

audit-result.schema 三契约（criteria_ref/pending_reason/page_kind）并存无覆盖；model.ts 单点定义
三处调用；tender-evaluate.md 纯新增块，H1 段落逐字保留；rag_store 为 :memory: FTS5 虚表，
PRAGMA+ALTER 先例不适用且不需要（N2 记录约束）。

## 新增 findings 与处置（全为 P2/INFO，无 P0/P1）

- N1 [P2] design 两处上界措辞矛盾 → **已修**（主 agent，design 基线节澄清限定范围）。
- N4 [P2] 证据 collect 数陈旧（1275 vs 实测 1286）→ **已修**（主 agent 复测更正并 commit）。
- N2 [P2] rag_store 仅内存约束缺落档说明、N3 [P2] SKILL.md 新节插入位置切断原列表 → **留 polish**。
- N5/N6 [INFO] 记录不 action。

## 过度工程双向扫描（reviewer）

过度侧无；缺失侧本轮净加强（F2 收窄虚假出处路径、F4 fail-loud）。

## 结论

pass1 全闭合、共存干净、遗留仅 P2（polish 承接）。

## VERDICT (evaluator, 2026-08-12)

**PASS**。Evidence Cross-Check 16 项全 ✅（evaluator 独立复核：collect 1286、豁免表行数逐项吻合、
tdd-evidence 恰 11 条、14 commits 落于 c4689fc 之上）；done_without_evidence=0、
unresolved_over_engineering=0；遗留仅 P2/INFO 且承接明确（N2/N3/F7/F8/第二 golden → polish；
D2 LibreOffice 端到端 → runtime-verify 容器内复核）。已合 main（merge 1a34942）。
