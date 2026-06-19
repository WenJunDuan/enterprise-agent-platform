# 架构现状档 · 总入口

> 项目长效架构档索引。每个子系统一档 `{type}-{slug}.md`。Refactor/System 路径 ship 前强制更新。

## 子系统档

| 档 | 子系统 | 摘要 |
|---|---|---|
| [system-contract-audit.md](system-contract-audit.md) | legal 合同审查 + 合同库 | /review-contract 内联审查产 audit-result + contract_store 落库（条款/付款节点），request_id 回链 |

## 全局分层（server/）

```
app (api/cli) → routes → ops → features(audit|ocr) → core → common → stores → platform
```

- `ops` 是 routes 之下的 service 层（diagnostics/maintenance），被 app+routes 共同消费——
  见 `compound/2026-06-19-decision-ops-below-routes-layering.md`（T2.5 修正）。
- feature 域（audit/ocr）互不 import；tender/legal 走内联命令，未建 feature 模块。
- 守卫：`tests/test_layering.py`（6 条：routes 不 import api、platform 叶子、common 不依赖上层、
  feature 互斥、ops 不 import routes/app/features、stores 只 import platform）。

## 存储

- 统一单库 `data/db/platform.sqlite3`（多表）：results/requests/sessions/review_deltas/
  memory_assets/audit_tasks/tender_tasks/contracts。
- 大 blob 留文件：会话 event 流、上传原件、合同原件 `data/contracts/<id>/source/`。
- 详见 `sprints/2026-06-19-logging-and-storage/design-data-storage.md`。
