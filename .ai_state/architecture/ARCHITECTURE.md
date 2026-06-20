# 架构现状档 · 总入口

> 项目长效架构档索引。每个子系统一档 `{type}-{slug}.md`。Refactor/System 路径 ship 前强制更新。

## 子系统档

| 档 | 子系统 | 摘要 |
|---|---|---|
| `system-tender-data-model.md` | tender 招标数据模型 | 招标项目实体 owns N 家投标评标 + 多投标人追加 + 回看 + 价格横比（Phase 1+2，2026-06-20） |
| （已删） | contract/legal | 2026-06-20 agent-capability-redesign G0 删除（死域，无 knowledge/legal 规则） |

## 真实业务域（round4 校准）

- **expense**（报销审核）· **tender**（招投标评标）· **ocr**（文档识别能力，喂其它域）。
- system 是制度→规则工具域，不出审批结论。
- **已删死域**：legal/contract（无规则、纯增攻击面）+ HR（仅孤儿 agent stub）——见 round4 F8。

## 全局分层（server/）

```
app (api/cli) → routes → ops → features(audit|ocr) → core → common → stores → platform
```

- `ops` 是 routes 之下的 service 层（diagnostics/maintenance），被 app+routes 共同消费——
  见 `compound/2026-06-19-decision-ops-below-routes-layering.md`（T2.5 修正）。
- feature 域（audit/ocr）互不 import；tender 走内联命令，未建 feature 模块。
- 守卫：`tests/test_layering.py`（6 条：routes 不 import api、platform 叶子、common 不依赖上层、
  feature 互斥、ops 不 import routes/app/features、stores 只 import platform）。

## 存储

- 统一单库 `data/db/platform.sqlite3`（多表）：results/requests/sessions/review_deltas/
  memory_assets/audit_tasks/tender_tasks + **tender_projects/tender_compare_tasks/tender_compare_results**（招标数据模型）。
- 大 blob 留文件：会话 event 流、上传原件。
- 详见 `sprints/2026-06-19-logging-and-storage/design-data-storage.md` + `architecture/system-tender-data-model.md`。
