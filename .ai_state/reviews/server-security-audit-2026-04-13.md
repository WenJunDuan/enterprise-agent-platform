# Server 代码独立审查 — 2026-04-13

- 范围: `server/**/*.py` 全量（18 个文件；`stores/session_store.py` / `stores/runtime_store.py` 未深入）
- 不含: `.claude/**`、`tests/**`、`.ai_state/**`
- 审查者: `feature-dev:code-reviewer` 子 agent（独立会话）
- 健康度总评: **中**

## P0 — 安全（高置信度）

| # | 位置 | 问题 | 修复方向 |
|---|---|---|---|
| P0-1 | `server/platform/config.py:218` | `TENANT_KEYS` 未设置时硬编码回落为 `{"default":"sk-default"}` —— 生产环境忘记配环境变量就静默启用弱密钥 | 未设置直接 `raise RuntimeError`，拒绝启动 |
| P0-2 | `server/api.py:139` | `if key == token` 普通字符串比较，存在时序侧信道 | 改 `hmac.compare_digest(key, token)` |
| P0-3 | `server/api.py:398-399` | `_sanitize_upload_name` 只取 basename；(a) 上传同名文件 `audit-request.json` 会覆盖元数据；(b) 同批同名附件互相覆盖；(c) Windows 设备名未防护 | 字符白名单 + 写前查 exists + 保留名冲突检测 |
| P0-4 | `server/api.py:423-434` | `_validate_directory_case_path` 对 `data/` 内的符号链接未检测，能读到同 case 外目录 | `resolve` 后检查 `is_symlink` 或收窄到 `SUBMISSION_ROOT_DIR/` 下 |
| P0-5 | `server/platform/source_proxy.py:17` | `prepare_text_proxy` 直接用 `req.source_path` 给 `pdftotext`，可读任意本地文件 | 对 `source_path.resolve()` 做白名单校验 |
| P0-6 | `server/api.py:826-835` + `platform/diagnostics.py:15-75` | `/health` `/ready` 无鉴权，返回 `anthropic_base_url`、`credential_source`、`dotenv_path` 等内部配置 | 这两个接口加鉴权，或公开版裁剪字段只返回 `{status:"ok"}` |

> P0-1 和 P0-6 生产环境即刻可利用。

## P1 — 正确性（高置信度）

| # | 位置 | 问题 | 修复方向 |
|---|---|---|---|
| P1-1 | `server/api.py:388-395` | `asyncio.create_task(...)` 未持有引用；任务异常被静默吞、SIGTERM 时强制取消、状态留在 `running` 直到下次启动 | 持有 task + `add_done_callback` 记录异常；lifespan 关停时优雅 cancel |
| P1-2 | `server/stores/audit_task_store.py:76-99` | 多 worker 启动同时跑 `recover_stale_audit_tasks` 会写放大；`fcntl.flock` 在 NFS 挂载下无效 | 仅主 worker 恢复，或基于文件内 `status` 幂等跳过 |
| P1-3 | `server/stores/audit_task_store.py:44-55` | `recover_stale_audit_tasks` → `upsert_audit_task` 传入的 dict 字段不全，`AuditTaskRecord(**merged)` 可能抛 `TypeError`，直接阻断 lifespan 启动 | upsert 内捕获 TypeError/KeyError 并告警；或恢复链路传完整字段 |
| P1-4 | `server/api.py:280-318` | `_raise_endpoint_error` 总是 raise 但返回类型是 `None`，静态分析器识别不出控制流 | 返回类型标注为 `NoReturn` |

## P2 — 设计（中置信度）

| # | 位置 | 问题 | 修复方向 |
|---|---|---|---|
| P2-1 | `server/api.py` | 945 行过胖，路由/校验/调度/审计混在一起 | 按域拆分 `routers/audit.py` / `routers/chat.py` / `routers/sessions.py` |
| P2-2 | `server/platform/config.py:210-213` | `_env_int` 非法值抛裸 `ValueError`，且触发点在 `@lru_cache` 首次调用，traceback 不友好 | 包装成 `RuntimeError(f"invalid int for {name}: {value!r}")` |

## 落地优先级建议

**本周必修（P0）**：
1. P0-1 删除 sk-default 兜底 —— 改动 1 行，风险最大
2. P0-6 `/health` `/ready` 裁字段或加鉴权
3. P0-2 `hmac.compare_digest`
4. P0-3 上传文件名冲突检测（先防止 `audit-request.json` 被覆盖）

**下周（P1 + 剩余 P0）**：
5. P0-4 / P0-5 路径穿越 & symlink 检测
6. P1-1 后台任务生命周期
7. P1-3 upsert 容错

**后续（P2）**：
8. `api.py` 拆分 routers
9. config 错误提示友好化

## 关联

- 本轮审查为主动发起的独立质量评估，不对应具体 sprint
- Codex 第二审查正在后台运行，完成后另附 `codex-review-*.md` 并做交叉对比
- 所有 P0 建议纳入下一个 sprint 的开发计划

## Codex 复核备注

- 复核时间: 2026-04-13 20:44:16 CST
- 复核人: Codex
- 复核方式: 静态代码复核（未执行服务启动或利用 PoC）
- 复核意见:
  - 该报告整体方向可参考，但不建议直接作为最终定稿，需修订后再进入开发计划。
  - `TENANT_KEYS` 弱默认值、`/health` 与 `/ready` 信息暴露、后台任务生命周期问题，这几项判断基本成立。
  - P0-3 中“上传 `audit-request.json` 会覆盖元数据”这一点不成立；当前上传白名单不允许 `.json`，真实问题应表述为“同批同名附件会互相覆盖”。
  - 本轮复核发现报告漏掉了更高优先级的攻击面：`/chat`、`/chat/stream` 和 `/audit` 当前可驱动高权限 Claude agent 访问本地仓库与文件系统，这个风险级别高于字符串常量时间比较。
  - P1-4 `NoReturn` 更偏静态类型标注与可维护性问题，不建议按“正确性”缺陷处理。
