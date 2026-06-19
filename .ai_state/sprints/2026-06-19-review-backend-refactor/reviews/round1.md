# Round 1 Review — 数据/迁移完整性 (bbf40ac..a337fd7)

> Reviewer findings + spec-compliance findings 汇总于 evaluator prompt 输入。
> 本文件由 evaluator subagent 生成。

## VERDICT (evaluator, R1 — 数据/迁移完整性)

**判定**: CONCERNS

### 评分依据 (4 维)

| 维度 | 得分 | 说明 |
|---|---|---|
| Functionality | 4.2 | 核心迁移逻辑正确且幂等；单库统一、payload 折叠、audit_tasks 上线均已实现；spec §九 7步全覆盖 |
| Spec Compliance | 4.5 | MISSING=0；EXTRA=4 合理；DEVIATED=4 均有记录理由（D1/D3 已在 ship.md 注释，D2/D4 属 P2 文档缺失）|
| Craft | 3.5 | F2 except Exception continue 静默丢数据无 skipped 计数是可观测性欠债；F5 finally 无显式 rollback 是习惯性瑕疵 |
| Robustness | 3.2 | F1 _load_memory_files 无异常隔离确认：单坏文件崩全量查询；F4 payload 折叠读回路径 0 边界测试 |

总评: 3.85 / 5.0

### 触发判定的关键 findings

- F1 (P1): memory_store._load_memory_files:172 json.loads 无 try/except — 单个 corrupt JSON 文件导致所有 memory 查询在当次请求内 500，已代码验证 → P1 累计贡献 CONCERNS
- F2 (P1): migrate.py:80 except Exception: continue 静默丢行，report 无 skipped 计数；生产早期数据静默丢失无法区分 → P1 累计贡献 CONCERNS
- F3 (P1): test_migrate.py 无 migrate_storage() 端到端测试；_reconstruct_payloads 测试路径不含 YYYY/MM/DD 真实结构 → 测试覆盖不足 P1
- F4 (P1): result/request/review_delta/memory store 缺独立功能测试；get_payload_by_request_id、NULL payload、反序列化失败边界 0 覆盖 → 测试覆盖 P1
- F5 (P1): sqlite_store.py:29-33 finally 只 close 不 rollback，WAL + BEGIN IMMEDIATE 场景锁可能多持 → P1（低概率但跨 Py 版本行为不稳定）
- D2/D4 (P2): deploy 文档 data/logs 挂载说明微调缺失；§七 step④ 旧目录无显式 read-only 标记 — 可进 polish 顺手处理

P1 共 5 个 → ≥3 P1 → CONCERNS；无 P0 → 不触发 REWORK

### 行动建议

**Phase 1 前必须修（门禁项）**
- F1: _load_memory_files 循环体加 try/except (json.JSONDecodeError, OSError) 隔离单文件错误，记 WARNING，跳过该文件继续
- F2: _copy_table except 块加 skipped += 1 计数，函数返回 (migrated, skipped)，调用侧有 skipped>0 时打 WARNING 日志

**可进 polish / 下轮顺手清理**
- F3: 补 migrate_storage() 端到端测试（含 YYYY/MM/DD 路径结构）
- F4: 补 result_store/review_delta_store 的 payload NULL 和反序列化失败单测
- F5: connect_sqlite finally 改为 try: connection.rollback() except: pass 后再 close
- D2: 补 deploy/prod 文档 data/logs 目录挂载说明
- D4: 在 migrate.py 注释中显式标注旧库保留不删、如需删除需人工 verify-then-delete

**推迟（INFO 级）**
- F6: 测试写真实 PLATFORM_DB_FILE（uuid 降风险已足够，tmp_path 隔离是锦上添花）
- F7: fetchall 全表内存（当前数据量级不构成实际风险，v2 可换 cursor 分批）
- F8: memory_assets 迁移冗余（refresh_index 会覆盖，无实际数据风险）

### Sisyphus 完整性检查
- [x] R1 reviewer findings 已完成（8 条 findings 已提交）
- [x] R1 spec-compliance findings 已完成（MISSING/EXTRA/DEVIATED 全分析）
- [ ] F1/F2 门禁修复尚未执行（CONCERNS 判定，需修后再进 R2）
- [ ] R2/R3/codex 轮次尚未启动（属后续 sprint，非本轮 Sisyphus 范围）
- [ ] 全量 pytest 通过（门禁修复后需重跑确认）
