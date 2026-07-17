# Decision: F6(schema 分家) + F5(evidence 拆分) 拆出 D2，转独立 sprint

- date: 2026-07-16
- type: decision
- sprint: 2026-07-16-tender-feature-package (D2)
- 关系：不推翻 [[2026-07-16-decision-schema-split-tender]]（方案 A 仍有效），仅改执行分期

## 背景
D2 原范围 = tender 纯移动 + F6 schema 分家（方案 A，已拍板）+ F5 evidence 拆分。
Round-1 修订应答把 F6 定性为"含 contract 机制**向后兼容小改**"。

## 触发
Round-2 critic（主 agent 独立核验属实）G1[P0]：F6=A 并非小改——
`output_contracts.py:462-470` 单处理器把 `normalize_audit_result`/`_validate_audit_result`/
`enrich_audit_decision` 挂在 `DEFAULT_OUTPUT_SCHEMA_NAME`，三函数直接内嵌 6 个 tender-only helper
（tender_output.py，@:30-37/193/309-311/409/443）。要 audit/expense "不再跑 tender 校验"，
必须把这三函数一分为二 + 迁移 `test_contract_registry.py` 38 处 tender 行为断言。
= 共享 contract 层的行为重构，回归面显著。G2[P1]：cli 路径零 `server.tender` import → 自注册静默失效。

## 决策（用户 2026-07-16 拍板）
F6（schema 分家）+ F5（evidence 拆分）拆出 D2，转独立 sprint `tender-schema-split`（depends_on D2）。
D2 收窄为**已核实干净的纯移动**（worker/compare_worker/doc_pipeline 迁 server/tender/ + tender.py 分节）。
方案 A 本身不变，只改执行分期。

## 理由
1. 不把共享 contract 行为重构 bolt 到"移动" sprint，红区回归定位更清晰（each step isolatable）。
2. D2 纯移动 rg 实证无 layering 开口（3 文件仅下行 import），可较快 ready→impl，先交付 tender 归位价值。
3. F6/F5 拿到独立 design+critic+impl 周期，Round-2 G1/G2 作其 design 输入（不丢）。

## 后果
- D2 验收清单重写（去 F6/F5 项 + T3-harness 项）；design.md 加「Round 2 后 · D2 范围定稿」权威节。
- 新 sprint `tender-schema-split` 待立；Round-2 G1（三函数拆分 + 38 测试迁移）/G2（cli import 纪律 +
  隔离子进程注册测试）/F5 边界（已验 RESOLVED）= 其 design 骨架。
- depends_on：worker 归位（D2）后再动 output/evidence/schema，避免二次搬迁。

## 链接
- design: sprints/2026-07-16-tender-feature-package/design.md（Round 2 findings + 范围定稿）
- 前置决策: [[2026-07-16-decision-schema-split-tender]]
