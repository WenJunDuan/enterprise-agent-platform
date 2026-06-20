# Phase 0 复核汇总 · 后端重构（bbf40ac..a337fd7）

> 3 轮深度 review 完成（R1/R2/R3 均 CONCERNS）。codex 交叉 review 待跑。
> 范围：server 分层 / 企业日志 / 校验注册表 OCP / data 存储统一单库+迁移。44 文件 +1536/-1169。

## 各轮 VERDICT

| 轮 | 主题 | VERDICT | P0 | P1 | 要点 |
|---|---|---|---|---|---|
| R1 | 数据/迁移完整性 | CONCERNS | 0 | 5 | 核心迁移逻辑正确且幂等；缺口在测试覆盖 + 可观测性 |
| R2 | 架构/分层一致性 | CONCERNS | 0 | 6 | A1-A4 断环成功；**守卫网有洞**（实 4 条、ops/stores 零守卫）+ 3 处上向 import |
| R3 | 安全/健壮性 | CONCERNS | 0(代码) | 6 | 无注入/无穿越；**F1 密钥在 git 历史=运维 P0**；信息泄露 F2/F3 |
| codex | 独立交叉 | **REWORK** | 0(代码) | 2 | **C1 迁移漏 JSONL 历史面** + **C2 litellm 0.0.0.0 暴露**；C3 migrate 路径穿越(R3 漏判) |

> **item0 聚合 VERDICT = REWORK**（codex 门禁；3 轮内部均 CONCERNS）。修复后须全绿才收口。
> 本地已确认：无遗留 JSONL shard、无旧 per-store sqlite，只有统一库 `data/db/platform.sqlite3` → **C1 在 dev 不适用；生产是否有 JSONL-only 历史数据待用户判断**。

## 🔴 运维项（代码侧无法修，须你/运维处理）

- **F1 [P0] litellm 真实 key `sk-hATxkq_*` + 内网 IP 在 git 历史 commit `7122b31`**。gitignore 抹不掉历史。
  须 ① 在 Qwen 后端**轮换该 key 使其失效**；② 用 BFG/filter-branch 清史并强制 push。**仅运维可做（本条即唯一归宿）**。

## 🟡 Phase 0 修复门禁（9 项，进 Phase 1 前批量修，TDD）

| # | 来源 | 门禁项 | 文件 |
|---|---|---|---|
| 1 | R1-F1 | `_load_memory_files` 加 try/except 异常隔离（单坏文件不拖垮全部 memory 查询） | `stores/memory_store.py:172` |
| 2 | R1-F2 | `_copy_table` 加 skipped 计数 + WARNING（迁移静默丢 NOT NULL 冲突行不可见） | `stores/migrate.py:80` |
| 3 | R2-F7 | `_env_int` 去重提取（DRY P0） | `platform/logging_setup.py:156` + `config.py:246` |
| 4 | R2-F5 | 拆出 `_cleanse_risk_dimensions`（校验 ≠ mutate，SRP） | `common/output_contracts.py:109-151` |
| 5 | R2-F1/F3/F4 | 修 3 处上向 import 改直连源模块 + 补 2 条分层守卫 | `routes/health.py:12`、`ops/diagnostics.py:9`、`routes/audit.py:17`、`tests/test_layering.py` |
| 6 | R3-F2 | `error_detail = str(exc)` 改脱敏消息，原始异常仅进服务端日志 | `routes/audit_worker.py:158` |
| 7 | R3-F3 | SPA fallback 500 detail 去掉绝对路径 | `api.py:312` |
| 8 | R3-F4 | 默认租户 token 可预测：限定 insecure default 仅测试环境/构建期强制关 | `config.py:21`、`routes/deps.py:41-59` |
| 9 | R3-M1 | 补 audit_task 并发写测试（design §八 明确要求，零覆盖） | `tests/test_audit_task_store.py` |

## ⚪ polish / 推迟（非门禁）

- R1: F3/F4 补迁移端到端 + store 读路径测试、F5 connect_sqlite 显式 rollback、F6 tmp_path 隔离、F7 分批迁移、F8 memory_assets 迁移冗余。
- R2: F6 configure_logging 拆分（41 行）、F8 包内循环、F9 magic set、D2 文档"5/4 条"措辞。
- R3: F5 `_extra_fields` 脱敏黑名单（回归防护）、F6 shutdown 显式 cancel、F7 migrate 表名运行期断言、F8 CORS `*`/regex 校验、M2 env 测试、M3 VACUUM 入口、D4 旧目录显式保留策略。

## 🟡 codex 新增门禁（合并进修复 sprint）

| # | 来源 | 门禁项 | 文件 |
|---|---|---|---|
| 10 | codex-C2 | LiteLLM compose 绑 `127.0.0.1`/仅内部 network + master key（MODEL_BASE_URL 用 docker 服务名，绑内部安全） | `deploy/prod/docker-compose.yml:14` + `litellm_config.yaml(.example)` |
| 11 | codex-C3 | migrate payload 路径 containment：`resolve()` 后 `relative_to(LOGS_ROOT)`，越界计 skipped/error | `stores/migrate.py:94` |
| 12 | codex-C5 | test patch 目标改 `session_queries.SESSION_STORE`（现 patch facade 不生效，写真实库） | `tests/test_session_store_char.py:113` |
| 13 | codex-C1 | 迁移 JSONL 历史面 —— **方案待用户决定**（dev 无 JSONL 残留；生产是否有 JSONL-only 数据未知） | `stores/migrate.py:33` |

> C4（_copy_table 静默丢行）已并入 #2；C6（迁移测试盲点）已并入 #9 + #2 的测试。

## 重新定界（用户 2026-06-19：demo 阶段 / 内网无风险 / key 自轮替 / litellm 不用管）

**丢弃**（prod/ops/legacy，demo 不需要）：C1 JSONL 历史迁移、F1 litellm key 轮换+清史、C2 litellm 绑定。
→ 聚合 VERDICT 从 REWORK 回落 **CONCERNS**（REWORK 的两个门禁 C1/C2 已 de-scope）。

**现在修（纯代码质量/正确性，与风险无关，利于 Phase 1 基座）**：
1. R2-F7 `_env_int` 去重（DRY P0）
2. R2-F5 `_validate_audit_result` 拆出 `_cleanse_risk_dimensions`（SRP，校验≠mutate）
3. R1-F1 `_load_memory_files` 异常隔离（单坏文件不拖垮 memory 查询）
4. codex-C5 `test_session_store_char` patch `session_queries.SESSION_STORE`（修测试不真正隔离的 bug）

**延后**（记录在案，Phase 1 触达 routes/ 时一并处理或后续 backlog）：
- 架构分层（R2-F1/F3/F4 + 补守卫）——**需"ops 相对 routes 层序"设计决策**（health 路由合法需要 diagnostics），Phase 1 加 `routes/contract.py` 时一并定层序 + 补守卫。
- API 错误脱敏 R3-F2/F3、默认 token R3-F4、并发写测试 M1、migrate 可观测性 R1-F2/C3 + 路径 containment——内网 demo 非基座项，列 backlog；Phase 1 新代码自带脱敏好习惯。
- 全部 polish 项（见上）。

## 收口条件（item0 → completed）

上述 4 项 fix 全绿 + `uv run pytest -q` 全量通过 + `uv run ruff check .` 零警告。延后项已文档化（不丢）。架构层序决策转入 Phase 1。
</content>
