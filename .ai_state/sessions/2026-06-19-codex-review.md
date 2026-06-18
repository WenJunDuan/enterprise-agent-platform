# Codex 独立 Review · 2026-06-19 · 存储/日志/分层重构

> 用 `codex exec -s read-only` 对本会话 origin/main..HEAD 的后端改动做独立审查（排除 agent-front）。
> codex 联网核对了 Python sqlite3 / SQLite 官方文档。VERDICT：**需返工**（已全部处置，见下）。

## Findings 与处置

| 严重度 | 问题 | 处置 |
|---|---|---|
| **High** | 迁移只重建 `results.payload`，漏 `review_deltas.payload` → 旧复核 delta 迁移后 payload=NULL 不可读，删旧目录即丢数据 | ✅ **已修** `migrate._reconstruct_payloads` 泛化到 `(results, review_deltas)` 两表 + 测试 |
| Medium | 迁移没搬旧 `logs/sessions/events`，maintenance 只管新目录 → 删旧目录丢会话流 | ✅ **已修** 新增 `_migrate_session_events`（copy2 旧→新，已存在跳过）+ 测试 |
| Medium | `_copy_table` 用源列名直插：列不匹配报 "no column"/缺 NOT NULL 报错/单行坏数据中断整表；audit_task backfill 缺必填字段会在 import 时炸服务启动 | ✅ **已修** `_copy_table` 按目标列交集 + 逐行 try/except；backfill 缺字段 `TypeError` 跳过 |
| Medium | `memory_store.refresh_index` 每次读 `DELETE+全量重插` → 统一库下与 audit/请求写抢同一 SQLite writer | ✅ **已修** 加 mtime 指纹守卫（文件没变就不写库），可 `force=True` 强制 |
| Medium | `common/contract.py` 仍含 audit 专属逻辑，未达 "common 域中立" | ✅ **已修（但纠正 codex 方案）** codex 建议"移到 audit/"是错耦合（audit-result 是 audit/tender/expense 共享契约，移到 audit/ 会让 tender/expense 反向依赖 audit）。正解：contract.py 拆成纯机制（registry+schema infra，337→173 行）+ output_contracts.py 装内置策略并注册。commit `c6724b0` |
| Low | 存储测试直接写真实 `data/db/platform.sqlite3`（靠随机 id 防撞），非 hermetic | ⏸️ 新增的 session-events 测试已 monkeypatch tmp；旧 store 单例在 import 期捕获 db_path，彻底 hermetic 需重构，gitignore+随机 id 风险低，暂留 |
| Low | `deploy/prod/litellm_config.yaml` 硬编码 key | ✅ **已改** git rm --cached + gitignore + .example 占位模板（commit `7664697`）。⚠️ 旧 key 仍在 git 历史，**需在后端轮换**（gitignore 抹不掉历史）——运维侧动作 |
| — | **BEGIN IMMEDIATE 生效性** | codex 查官方文档确认：默认 legacy transaction control 下 SELECT 前不隐式开事务，故 SELECT 前显式 `BEGIN IMMEDIATE` 能先拿写锁，原子化成立 |

## 对我自审的评价（codex 原话提炼）
"自审质量整体不错，覆盖了分层、原子化和 happy path；但对**迁移完整性、schema drift、统一库下写锁放大**这几类边界盲点偏乐观。"

## 结论
所有 Blocker/High/可修 Medium 已处置，commit `4d2cd8a`。两个 Low + 1 个设计取舍(#5)明确暂留并记录理由。
修复后 237 passed / ruff clean。教训：**迁移类改动必须逐表核对"折叠列/文件指针/blob 搬运"完整性**，
不能只验主表 happy path。
