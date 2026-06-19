# Phase 0 · 第 4 轮 codex 交叉 review

> `codex exec -s read-only`（codex-cli 0.141.0）· 同 diff 区间 `bbf40ac..a337fd7` · 联网核对 SQLite/FastAPI/logging 官方文档
> codex 未跑测试（只读环境，pytest 会写库/缓存）——纯静态 + 文档核对。

## VERDICT: REWORK

> "运行期分层整体比原来干净，但迁移遗漏 JSONL 历史面和生产代理暴露面需要合并前修掉。"

## 新发现（前 3 轮漏掉/低估）

- **C1 [P1] `server/stores/migrate.py:33`** —— 迁移只读旧 `index.sqlite3`，遗漏旧 JSONL shard。基线 `bbf40ac` 的 request/session/result store 曾保留 `logs/.../index/*.jsonl` 回填路径，新 `_TABLE_SOURCES` 只覆盖 SQLite。若旧 SQLite 不完整/损坏，或更早版本只留 JSONL → 历史请求/会话/结果索引及 payload 指针不进 `platform.sqlite3`。建议恢复 JSONL reader 迁移路径 + 补"只有 JSONL 无 SQLite"迁移测试。**【待定：取决于是否真存在 JSONL-only 部署数据】**
- **C2 [P1] `deploy/prod/docker-compose.yml:14`** —— LiteLLM 代理发布 `0.0.0.0:4000`，模板无网关鉴权。生产机有可达面即开放模型代理。建议默认绑 `127.0.0.1:4000:4000` 或仅 `expose` 内部 docker network + LiteLLM master key/auth，由 app-server 内部访问。
- **C3 [P2] `server/stores/migrate.py:94`** —— payload 重建直接拼 `LOGS_ROOT / result_file`，无 root containment 校验。恶意/损坏的旧 `result_file`（绝对路径或 `../`）→ 读取日志根外文件。建议 `resolve()` 后强制 `relative_to(LOGS_ROOT.resolve())`，越界计入 skipped/error。（R3 判"穿越已防护"漏了 migrate 这条。）

## 交叉印证 / 补充

- **C4 [P2] `migrate.py:72`** —— `_copy_table` 静默 `continue`，报告只给成功数 → 与 **R1-F2 同源**。codex 建议返回 `{source,total_inserted,ignored,failed}` + 默认打印 failed 明细 + 可选 `--strict` 失败退出。
- **C5 [P2] `tests/test_session_store_char.py:113`** —— 测试 monkeypatch facade `session_store.SESSION_STORE`，但重导出函数实际用 `session_queries.SESSION_STORE` → "临时 DB"测试不真正切 tmp_path，可能写真实库 + 掩盖 facade 耦合。建议 patch `session_queries.SESSION_STORE` 或 facade 提供可注入入口。
- **C6 [P2] `tests/test_migrate.py:15`** —— 迁移测试缺 JSONL-only/result payload/越界 result_file/坏行统计/并发 upsert 锁边界覆盖 → 印证 **R1-F3 + R3-M1**。

## 官方文档核对（codex 联网）

- SQLite WAL 读写并发但单 writer；`BEGIN IMMEDIATE` 提前取写事务；`PRAGMA busy_timeout` 是锁等待边界 → 当前实现成立。
- FastAPI 自定义 exception handler、`RotatingFileHandler` namer/rotator 用法符合官方文档。
- Sources: sqlite.org/wal.html、lang_transaction.html、pragma.html#busy_timeout；fastapi handling-errors；docs.python.org logging.handlers。
</content>
