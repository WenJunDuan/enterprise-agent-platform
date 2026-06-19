---
doc_type: decision
date: 2026-06-19
slug: ops-below-routes-layering
sprint: 2026-06-19-tender-ingestion-workflow
task: T2.5
supersedes: "2026-06-18-server-layering design.md 的 app→ops→routes 顺序"
---

# 决策：ops 是 routes 之下的 service 层（修正层序）+ 补 ops/stores 守卫

## 背景

item0 后端重构复核（R2）把「ops 相对 routes 层序」决策延后，并标了「3 处上向 import」
（`routes/health.py:12`→ops、`ops/diagnostics.py:9`→core、`routes/audit.py:17`→core）+
「守卫网有洞：实测 4 条、ops/stores 零守卫」。Phase 1 tender 路由是后重构第一个新路由，
在 T2.5 一并定。

## 关键事实（调研 import 真相，非文档散文）

- `ops/`（diagnostics/maintenance）只 import `platform` / `stores` / `core`，**从不 import routes/app/features**。
- `ops/` 被 **app(cli maintenance) 和 routes(health) 共同消费**。
- `server.core` 只 import `common/*`，是 common 之上的 facade；被 routes/ops/app **下行**消费。
- `tests/test_layering.py` 实际只强制 4 条守卫，**无一检查 routes→ops**——所谓「上向 import」是
  对照**错误的文档顺序**（`app→ops→routes`）算出来的，不是测试失败。

## 决策

1. **ops 下沉到 routes 之下**。修正层序为：
   `app → routes → ops → features(audit|ocr) → core → common → stores → platform`。
   一个被 app+routes 共同消费、且只向下依赖的东西本就是 service 层，应在 routes 之下。
   → `health→ops` 是合法下行；**修正文档后真实违规数 = 0，零生产代码改动**。
2. **补 2 条守卫**（关掉 ops/stores 零守卫的洞，lock 当前良态）：
   - `test_ops_does_not_import_routes_app_or_features`
   - `test_stores_only_import_platform`（只许 platform + 同层 stores）
3. **core facade 清理（门禁#5「改直连源模块」）跳过**：routes/ops→core 是合法下行非真违规；
   且改 `routes/audit.py` 撞 roadmap 硬约束「audit.py 零改」。列为可选 polish backlog。

## 备选（未选）

- 保持 ops 在 routes 之上、解耦 health→ops（搬 diagnostics 聚合或 app 注入）——逆真实依赖、徒增 churn。

## 影响 / 复用

- contract-audit-api（Phase 2b）新增 `routes/contract.py` 时，层序已定、守卫已补，直接复用，无需再决策。
- 任何新 route 合法地依赖 ops service（diagnostics/maintenance）不再被误判为上向 import。
