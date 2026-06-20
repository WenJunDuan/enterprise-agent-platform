# Tender 数据模型优化 — 招标项目实体 + 多投标人追加 + 结果回看

> Sprint/Goal 2026-06-20 · Path: **System**（数据模型 + 存储 + 路由）· 设计先行，codex review 后设为 goal 实施。
> 驱动：用户运营模型「一个招标 → 多家投标人陆续上传追加 → 每次只评一家 → 已出不重审 → 存 data 做处理」。

## 1. 背景与问题（现状已查证）

当前 tender 存储（单库 `data/db/platform.sqlite3` 多表）：
- `tender_tasks`（泛型 `TaskStore`）：每次 `/tender/evaluate` = 一条任务，字段 `request_id/tenant/status/case_path/claim_id/...`，**无招标分组键**。
- `results`（`result_store`）：每次评标一条结论 payload，索引 `request_id/tenant/claim_id/verdict`，**无招标分组键**。
- `conversation_id` 每次提交都 `new_conversation_id()`，也不分组。

**三个缺口**：
1. **无"招标项目"概念**：三家投标 = 三条孤立任务，系统不知它们属于同一招标 → 无法"列出某招标下所有投标人"、无法为价格横比锚定。
2. **回看绑死任务生命周期**：删任务 → `results` 里结论成孤儿、从回看消失（回看走 `tender_tasks` 列表）。
3. **价格横比（v2）无落脚点**：`requires_cross_bid_comparison` 各家恒 `manual_review`，缺"全部投标到齐后按招标统一算价格分/排名"的锚。

现有可用锚点（extract-result 契约）：`tender.tender_no`（招标编号）/`tender.title`（项目名）/`tender.tenderee`（招标人）；`bidder.credit_code`（统一社会信用代码）/`bidder.name`；`bid_price.{amount,currency}`。

## 2. 方案对比

### 方案 A（轻量）：`group_id` 字符串列分组
- `tender_tasks` + `results` 各加一个 `group_id`(=招标编号) 列；提交时前端传；`GET /tender/tasks?project_id=X` 过滤。
- ✅ 改动小（2 列 + 1 过滤参数）。
- ❌ 招标无独立生命周期/元数据落点；价格横比仍无锚；回看仍绑任务列表；"招标项目"散落成字符串、易写法不一致。

### 方案 B（推荐）：`tender_projects` 一等实体
- 新建 `tender_projects` 表：招标项目是真实领域实体，**owns N 个投标评标**。每个 bid 评标（task+result）挂 `project_id`。
- ✅ 招标有生命周期（open→评标中→定标）、元数据（招标编号/项目名/招标人/标底）、bid 名册；价格横比天然 project 级；回看变 project 中心（看招标 X + 其 N 家结论）；分组键是稳定 project_id 而非易错字符串。
- ❌ 改动较大（+1 表 + project 端点 + 链路串 project_id）。

**推荐 B，分两期**：Phase 1 把实体 + 链接 + project 端点 + 回看做完（"追加多家/按招标查看/结果回看"全可用）；Phase 2（v2）做价格横比聚合。理由：A 终将长成 B（价格横比一来就需要 project 锚），现在直接建对的地基不返工。

## 3. 详细设计（方案 B）

### 3.1 新表 `tender_projects`（platform.sqlite3）
```
project_id   TEXT PRIMARY KEY     -- 服务端生成(uuid/前缀)
tenant       TEXT NOT NULL
tender_no    TEXT                 -- 招标编号(可空,前端传或评标后回填)
title        TEXT                 -- 项目名
tenderee     TEXT                 -- 招标人
status       TEXT NOT NULL        -- open(默认)/closed(定标后)；v1 仅 open
created_at   TEXT NOT NULL
updated_at   TEXT NOT NULL
-- 索引: (tenant, created_at DESC); (tenant, tender_no)
```
bid_count / 各家 verdict 汇总 **不冗余存**，按需 JOIN/聚合 `tender_tasks`（避免去同步）。

### 3.2 链接列（加在现有表，幂等 ALTER）
- `tender_tasks`：用**泛型 `TaskStore` 既有路子**——给通用 `TaskRecord` 加 nullable `group_id`，tender 层语义=`project_id`（不污染泛型 store 命名，audit 也可复用）。
- `results`：加 nullable `project_id` 列；由 worker 拿到结果后，把 project_id 透传进 `archive_result_payload`（加可选参数）落列 → 结果可独立于任务按招标查。

### 3.3 API 面（tender 项目中心）
| 端点 | 用途 |
|---|---|
| `POST /tender/projects` | 建招标项目(tender_no/title/tenderee)→ 返回 project_id |
| `GET /tender/projects` | 列招标项目(tenant,分页) |
| `GET /tender/projects/{id}` | 项目详情 + bid 汇总(数量/各家 status/verdict，聚合 tender_tasks) |
| `GET /tender/projects/{id}/bids` | 列该招标下所有投标评标(tasks) |
| `POST /tender/projects/{id}/evaluate` | **追加一家投标评标**(挂到该 project)；body 同现 evaluate(directory/upload) |
| `GET /tender/projects/{id}/results` | 该招标下所有结论回看(走 results.project_id，独立于任务删除) |
| `POST /tender/projects/{id}/compare` | **(v2 Phase 2)** 价格横比/排名聚合 |

- **向后兼容**：保留 `POST /tender/evaluate`（无 project → 自动建一个单投标人 project 或挂 NULL）；`GET /tender/tasks/*` 不动。
- 提交时 `tender_project_id`（=project_id）可由前端传；命令侧把招标项目标识钉进 `extracted_data.tender_project_id`（招标编号优先）供回填/结果分组。

### 3.4 命令侧（.claude）
- `tender-evaluate.md` 把"招标项目标识"钉成 `extracted_data.tender_project_id`（现为散文"留在 extracted_data"），与列名口径一致，供结果侧分组与回填。

## 4. 影响范围
- `server/stores/task_store.py`（泛型加 `group_id` 列 + 迁移 + 索引 + list 过滤）。
- `server/stores/tender_project_store.py`（**新**：tender_projects CRUD）。
- `server/stores/result_store.py`（加 `project_id` 列 + 迁移 + archive 透传 + 按 project 查询）。
- `server/routes/tender.py`（project 端点 + evaluate 挂 project + 回看）；`server/routes/tender_worker.py`（透传 project_id 到 archive）。
- `server/common/{command_adapter,json_bridge}.py`（archive 透传 project_id 可选参数）。
- `.claude/commands/tender-evaluate.md`（钉 `extracted_data.tender_project_id`）。
- `tests/`（project store + 路由 + 迁移 + 分组查询 + 回看）。
- `architecture/`（System ≥5 文件，ship 前更新现状档）。

## 5. 迁移与风险
- **加法式迁移**：新表 + nullable 新列 + 幂等 ALTER（仿 result_store PRAGMA 检查）；既有行 project_id=NULL（legacy 散单），不丢数据、向后兼容。
- 风险：泛型 `TaskStore` 加列影响 audit_tasks（nullable 无害，audit 不引用）；archive 透传需改动 `json_bridge` 公共路径（audit/tender 共用）→ 加**可选**参数默认 None，audit 不传，零影响。
- 风险：project 自动建 vs 显式建的并发去重（同招标重复建）——v1 用显式 `POST /projects` + evaluate 挂已知 project_id 规避；自动建留 backlog。

## 6. 验收
- 同一 project 下 `POST /projects/{id}/evaluate` 追加多家 → `GET /projects/{id}/bids` 列出全部、`GET /projects/{id}/results` 回看全部结论（删某任务不影响其余结论回看）。
- 既有 `POST /tender/evaluate` + `/tender/tasks/*` 不破（向后兼容测试）。
- `uv run pytest -q` 全绿 + ruff + 迁移幂等（重复 init 不报错）。
- System 路径：codex review 设计 → 交叉审查代码 → 更新 architecture 档 → ship。

## 7. 待 codex review 的关键决策点
1. 实体（B）vs 轻量列（A）——是否认同建 `tender_projects` 实体作地基。
2. 链接列复用泛型 `group_id` vs 给 tender 专列 `project_id`——命名/耦合取舍。
3. project 自动建 vs 显式建——v1 范围。
4. archive 透传 project_id（改公共 json_bridge）vs worker 后置更新 result 行——哪个更干净。
