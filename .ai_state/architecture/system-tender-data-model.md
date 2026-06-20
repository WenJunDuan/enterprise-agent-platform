# 架构现状档 · tender 招标数据模型（Phase 1+2）

> 子系统：tender 招投标评标的数据模型与多投标人编排。
> 现状基线：2026-06-20 tender-data-model goal（Phase 1 项目实体+追加+回看；Phase 2 价格横比）。
> 交叉审查：codex 设计 APPROVE-WITH-CHANGES + 代码 REWORK→fixed；cc CONCERNS→fixed。

## 领域模型

**招标项目（tender_projects）owns N 家投标评标**。一个招标 → 多家投标人陆续追加上传 → 每次只评一家 →
已出不重审 → 多家到齐后横比排名。区别于"每次评一家的孤立任务"（旧模型）。

```
tender_projects (招标项目实体)
  ├─ owns N × 投标评标 (tender_tasks[group_id] + results[project_id])   ← Phase 1
  └─ 1 × 价格横比     (tender_compare_results[project_id])              ← Phase 2
```

## 存储（platform.sqlite3 多表）

| 表 | 角色 | 关键列 |
|---|---|---|
| `tender_projects` | 招标项目实体 | project_id PK / tenant / tender_no(UNIQUE 部分索引,幂等建) / title / method / control_price / funding_type / status(doing/review/done/archived) |
| `tender_tasks` | 单投标人评标任务态(泛型 TaskStore) | request_id PK / **group_id=project_id**(链接键,不外泄路由) / status / claim_id |
| `results` | 单投标人评标结论 payload | request_id PK / **project_id** / payload(含 criteria/scoring/bid_price/verdict) |
| `tender_compare_tasks` | 横比任务态(独立表,**不混 tender_tasks**) | request_id PK / group_id=project_id |
| `tender_compare_results` | 招标级横比结论 | project_id PK / payload / **input_result_ids + criteria_hash + input_signature**(stale 检测) / computed_at |

## 关键架构决策（交叉审查固化）

1. **横比在 Claude 侧**（`/tender-compare` 命令）：价格公式项目专属、有效投标认定+异常低价判断需判断，
   撞铁律[Python 不判断]。server 只收集 N 家评分事实+调命令+落库。
2. **compare 不污染 results**（codex P1.1）：`run_agent_json(archive_to_results=False)`——compare 结论
   不是单投标人 audit-result，自存 `tender_compare_results`，否则会被 `_project_bid_roster` 当伪投标人。
3. **task 分表**（codex P1.2）：`tender_compare_tasks` 独立，roster 只聚合 `tender_tasks`，compare 不入名册。
4. **名册 = results.project_id ∪ 活跃 tender_tasks**（codex P1.1 Phase1）：删任务后已完成投标人仍从
   results 显示（结论 durable，独立于任务删除）。
5. **回看独立于任务**：`GET /projects/{id}/results/{request_id}` 直读 results.payload，删任务后仍可取完整结论。
6. **criteria 一致性 + stale**（codex P1.4/P2.6）：收集**全量**各家 criteria hash；不一致标
   `criteria_inconsistent`→命令 manual_review；input_signature 覆盖参与集+全量 hash，追加/重评后旧 compare 标 stale。
7. **推荐终局护栏**（codex P1.5）：`recommended` 可 null + `provisional` + `warnings`；仅排名第一明确+无异常低价+
   有效投标≥3+国有资金(evalmethod_013) 才给终局推荐；详情联动须 `provisional is False and recommended` 才展示。

## API 面（/tender）

- 单投标人（向后兼容）：`POST /evaluate`（挂 NULL project）· `GET/POST /tasks/*`（list/get/result/retry/delete）。
- 招标项目（Phase 1）：`POST/GET /projects` · `GET /projects/{id}`(详情+名册+recommendedBidder 联动) ·
  `POST /projects/{id}/evaluate`(追加一家) · `GET /projects/{id}/results[/{request_id}]`(回看)。
- 价格横比（Phase 2）：`POST /projects/{id}/compare`(异步,防重 409) · `GET /projects/{id}/compare`(含 stale)。

## 数据流（评标→横比）

```
POST /projects/{id}/evaluate × N  →  tender_tasks(group_id) + results(project_id)  [各家独立,不重审]
POST /projects/{id}/compare       →  collect(results.project_id, criteria 全量 hash)
                                     → /tender-compare(Claude,archive=False) → tender_compare_results
GET  /projects/{id}               →  名册(results∪tasks) + recommendedBidder(compare 非 stale 非 provisional)
```

## 待办（Phase 2 backlog）
- compare 触发 TOCTOU 窗口（has_active_compare 非原子，双击窗口 microseconds 级，最坏多算一次覆盖）。
- 前端 `agent-front/.../tender-review/` 接真实 /tender/projects API（下 sprint 前后端对接）。
