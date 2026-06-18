# data/ 业务存储重构 Design（深度勘察 + 计划）

> Sprint 2026-06-19 · Path: Refactor · **仅设计，待决策后动手**。
> 目标：logs/ 只留运行日志；data/ 收纳全部业务数据，用 SQLite 认真管理。

## 一、现状勘察（精确）

### 1.1 存储范式：SQLite 记录 + 文件 blob + legacy JSONL 回填

5 个 active store 全部是 **SQLite 单例**（JSONL 实现仅作 legacy 回填源，非默认）：

| store | SQLite 表 | 单例 | 额外文件 blob | 现位置 |
|---|---|---|---|---|
| result_store | `results`(PK request_id, verdict, tenant, conv, claim, cost, **result_file 指针**…) | `RESULT_STORE` | 完整结果 payload JSON：`by-request/YYYY/MM/DD/{rid}.json` | logs/results |
| request_store | `requests`(route/method/status/duration/tenant…) | `REQUEST_AUDIT_STORE` | legacy `requests-{月}.jsonl` 分片 | logs/service/requests |
| session(sqlite) | `sessions`(conv/claude_session/log_file/cost…) | `SESSION_STORE` | 原始 event 流：`sessions/events/YYYY/MM/DD/*.jsonl`（大、append-only） | logs/sessions |
| review_delta | `review_deltas` | `REVIEW_DELTA_STORE` | delta payload JSON `by-request/...` | logs/review-deltas |
| memory_store | `memory_assets` | `MEMORY_STORE` | 记忆产物 JSON 在 **knowledge/memory/{domain}/** | index 在 logs/knowledge |

### 1.2 三个"不干净"点（本次要解决）

1. **audit_task_store 是唯一没上 sqlite 的**：`tasks.json` 单文件，每次 upsert **全量重写** + flock。
   不可扩展、并发差、谈不上"认真管理"。→ 必须改 sqlite 表。
2. **业务数据全堆在 logs/ 下**（除 submissions）。logs/results、logs/sessions… 是误名（业务数据≠日志）。
3. **memory 存储割裂**：index 在 `logs/knowledge/`，文件在 `knowledge/memory/`，分两处。
4. **legacy JSONL 双后端 + 回填**：result/request/session 都带 `JSONL*Store` + `_backfill_legacy_records`，
   是早期 jsonl-only 的迁移脚手架，现 SQLite 已是默认，属可清理的历史重量。

### 1.3 SQLite 怎么管的（现状）

`platform/sqlite_store.py`：每个 store 各开**独立 .sqlite3 文件**，`connect_sqlite` 每次开/关连接
（busy_timeout=30s, synchronous=NORMAL）。即 5 个分散的 db 文件，无跨表事务、无统一备份。

## 二、设计目标

- `logs/` = 仅运行日志（app/ + runtime/），其余全部迁出。
- `data/` = 全部业务数据，**SQLite 为单一结构化真相源**，文件只留"放不进表的大 blob"。
- audit_tasks 上 sqlite；memory 收敛到一处；清理 legacy JSONL 双后端。
- 迁移**不丢现有数据**（一次性从旧 logs/ 位置导入新库）。

## 三、决策（已定 2026-06-19）

- **A1 统一单库** `data/db/platform.sqlite3`（多表 + WAL）。
- **B1 payload 折叠进 TEXT 列**（results.payload / review_deltas.payload），去 by-request 文件树 + result_file 指针。
- audit_tasks 上 sqlite；memory 收敛 data/memory；清理 legacy JSONL；会话 event 流 + 上传/合同原件留文件。

### 备选（未采纳，留痕）

### 决策 A — SQLite：统一单库 vs 每域独立库
- **A1 统一单库（推荐）**：`data/db/platform.sqlite3` 一个库，内含
  `results / requests / sessions / review_deltas / memory_assets / audit_tasks` 多表。
  单一备份文件、可跨表 join、统一连接与事务边界 = 真正"认真管理"。趁东西少改成本最低。
- **A2 每域独立库**：仅把 5 个 `*.sqlite3` 平移到 `data/db/{域}.sqlite3`。改动最小，但延续"分散 db"。

### 决策 B — 小 payload：进 SQLite TEXT 列 vs 留文件 + 指针
- **B1 折叠进库（推荐）**：result / review_delta 的完整 payload 不大（几 KB 的审核 JSON），
  直接存为 `results.payload` TEXT(JSON) 列，去掉 `by-request/` 文件树和 result_file 指针。
  一行 = 一条完整结果，最简。
- **B2 维持文件 + 指针**：payload 仍写 `data/results/by-request/...`，sqlite 存指针（现状）。改动小。
- **不变**：会话原始 event 流（大、append-only）+ 上传原件/合同原件 **永远留文件**，不进 sqlite。

## 四、目标 data/ 布局（按推荐 A1 + B1）

```
data/
  db/
    platform.sqlite3        ← 唯一业务库：results/requests/sessions/review_deltas/
                               memory_assets/audit_tasks 多表 + 索引
  submissions/<id>/         上传原件（ephemeral，maintenance 按 retention 清）
  sessions/events/YYYY/MM/DD/*.jsonl   会话原始 event 流（大 blob）
  memory/{domain}/*.json    业务记忆产物（从 knowledge/memory 收编，与 index 同根）
  contracts/<id>/           （未来合同库，C 设计）

logs/                       ← 此后只剩运行日志
  app/{app,error}.log
  runtime/app-server/
```

## 五、SQLite 存什么 / 怎么存（B1 下）

- **存**：所有可查结构化记录 —— 请求审计、结果（含 payload JSON 列）、会话索引、复核 delta、
  记忆资产索引、审核任务状态。主键 request_id，租户/会话/verdict 等建索引（沿用现有索引定义）。
- **不存（留文件）**：会话 event 原始流（jsonl）、上传/合同原件（二进制/大文档）。
- **怎么管**：单库多表；`sqlite_store` 增加"共享库路径 + 表初始化"；`connect_sqlite(platform.sqlite3)`
  统一；WAL 模式提升并发（`PRAGMA journal_mode=WAL`）；一次性迁移把旧 5 库 + tasks.json 导入新库。

## 六、代码 touchpoints（改动面，精确）

| 文件 | 改动 |
|---|---|
| `platform/paths.py` | 加 `DATA_ROOT`；业务路径常量改名+repoint 到 data/（去 `_LOG_` 误名）；`APP_LOG_DIR`/`RUNTIME_LOG_DIR` 留 logs/ |
| `platform/sqlite_store.py` | 支持共享单库 + 多表初始化（A1）；可选 WAL |
| `stores/result_store.py` | payload 折叠进列（B1）/ 改 db 路径；去 legacy 回填 |
| `stores/request_store.py` | 改 db 路径；去 JSONL 双写 + legacy 回填 |
| `stores/session_sqlite_store.py` + session 集群 | 改 db 路径；event 流迁 data/sessions/events |
| `stores/review_delta_store.py` | 同 result |
| `stores/memory_store.py` | index 进单库；memory 文件根收编 data/memory |
| `stores/audit_task_store.py` | **重写为 sqlite 表**（最大单点改动） |
| `ops/maintenance.py` | storage_report + 清理路径指向 data/；event 归档保留逻辑跟迁 |
| `platform/config.py` | session_store shard 容量项按需调整 |
| `routes/audit.py`、`routes/ocr.py` | 仅经 store 接口，**预期零改**（接口不变） |
| `docker-compose.yml` | `./data` 已挂载；确认 `./logs` 仍挂载即可，无需改 |
| `.dockerignore` / deploy 文档 | logs/data 说明微调 |
| `tests/` | test_maintenance、各 store 测试的路径/断言跟迁；新增 audit_task sqlite 测试 |

> 关键安全点：业务结论必须仍可回链 `evidence_chain`/`result_file`；迁移脚本要保证 request_id 主键不撞。

## 七、迁移（不丢数据）

一次性 `migrate_storage`：① 旧 5 个 sqlite 表 → 新单库对应表（INSERT OR IGNORE）；
② `tasks.json` → `audit_tasks` 表；③ 旧 `logs/results/by-request`、`logs/sessions/events` 文件
→ 移到 data/ 对应位置（或 B1 下结果 payload 导入列）；④ 保留旧目录只读一个版本，确认后再删。
data/ 与 logs/ 都 gitignore，迁移只动运行态、不入库。

## 八、风险与缓解

| 风险 | 缓解 |
|---|---|
| 单库并发写（A1）成瓶颈 | WAL + busy_timeout；当前单进程 uvicorn + 信号量限并发，压力低 |
| payload 入列（B1）使库变大 | 审核 JSON 仅数 KB；大 blob 仍留文件；可定期 VACUUM |
| 迁移丢数据 | 迁移幂等 + 旧目录保留一版 + 全程 pytest 兜底 |
| audit_task 重写改并发语义 | sqlite INSERT OR REPLACE 替代全量重写，并发更安全；补并发测试 |
| 改动面大（~12 文件 + 测试） | 分步：先 paths/单库基座 → 逐 store 迁 → audit_task → 迁移脚本 → 清 legacy；每步独立 commit + 全量绿 |

## 九、执行顺序（决策后）

1. paths.py 加 DATA_ROOT + 业务常量改名/repoint（不改语义，先让目录搬家）。
2. sqlite_store 支持单库多表（A1）+ WAL。
3. 逐 store 切到单库 / payload 入列（B1）：result → request → session → review → memory。
4. audit_task_store 重写 sqlite 表。
5. 一次性迁移脚本 + 跑通。
6. 清理 legacy JSONL 双后端 + backfill。
7. maintenance / docker / deploy 文档 / 测试跟迁。

每步 TDD + 独立 commit + 全量 pytest 绿；分层守卫不退化。
