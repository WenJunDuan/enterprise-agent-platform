# Server 安全修复计划 — 2026-04-13

- 基线报告: `.ai_state/reviews/server-security-audit-2026-04-13.md`
- 计划范围: server/** 的 P0 与关键 P1 问题
- 已整合: Codex 第二审查反馈（2026-04-13 20:44 CST）
- 预计 sprint: 下一轮开发 sprint，分两个阶段落地

## 修订说明（与原报告的差异）

基于 Codex 复核意见：

1. 新增 **P0-0**：`/chat`、`/chat/stream`、`/audit` 的 agent 工具链攻击面（原报告漏项，优先级最高）。
2. **P0-3** 改写：删除 "audit-request.json 覆盖元数据" 错误表述，保留"同批同名附件互覆盖 + Windows 保留设备名"。
3. **P1-4 NoReturn** 从正确性缺陷下沉到 P2（类型标注）。
4. P0-1 / P0-2 / P0-4 / P0-5 / P0-6 / P1-1 / P1-2 / P1-3 不变。

## 阶段划分

- **Phase 1（本周，必修）**：P0-0、P0-1、P0-6、P0-3、P0-2
- **Phase 2（下周）**：P0-4、P0-5、P1-1、P1-3、P1-2
- **Phase 3（后续）**：P2 重构 + 类型标注清理

---

## Phase 1 —— 本周必修

### F1. P0-0 agent 工具链攻击面收敛（新增，最高优先级）

**问题**
- `server/api.py:321` `/chat` 直接把 `req.message` 交给 `run_agent_json`；`server/api.py:570` `/audit` 把 `req.path` 作为 shell 命令参数交给 `run_command_json`；`/chat/stream`（720 行附近）同样。
- 鉴权过后，持有 tenant token 的调用方可诱导高权限 Claude agent 读本地仓库与文件系统。

**修复**
1. `/audit` 的 `req.path` 必须先经 `_validate_directory_case_path` 或白名单根目录（`SUBMISSION_ROOT_DIR`）校验；禁止相对路径、禁止 `..`、禁止跨 tenant 目录。
2. `/chat` / `/chat/stream` 的 `message` 加入输入长度上限（复用 `max_upload_file_bytes` 或新增 `MAX_PROMPT_CHARS`），并记录 prompt 指纹到审计日志。
3. 在 `core.run_agent_json` / `run_command_json` 外层加 tenant 级 allowed-tools 白名单（至少先关闭 Bash / Write / Edit，仅保留只读工具）；通过 `.claude/settings.json` 或 SDK 调用参数传入。
4. 新增集成测试覆盖：越权路径、超长 prompt、禁用工具尝试被拒。

**涉及文件**
- `server/api.py:321,570,720`
- `server/core.py`（agent 调用配置）
- `server/platform/config.py`（新增 `AGENT_ALLOWED_TOOLS` / `MAX_PROMPT_CHARS`）
- `tests/server/test_agent_surface.py`（新增）

**验收**
- 持 tenant token 请求 `/audit` 传 `../../etc/passwd` → 400
- 持 tenant token 请求 `/chat` 诱导写文件 → agent 拒绝或返回 sandbox 错误
- 新测试通过

---

### F2. P0-1 删除 TENANT_KEYS 弱默认

**问题**
`server/platform/config.py:218` 未设置 `TENANT_KEYS` 时回落到 `{"default":"sk-default"}`。

**修复**
```python
def load_tenant_keys() -> dict[str, str]:
    raw = os.getenv("TENANT_KEYS")
    if not raw:
        raise RuntimeError("TENANT_KEYS is required and must be a non-empty JSON object")
    ...
```

**验收**：未设置环境变量时进程启动失败，错误信息明确。

---

### F3. P0-6 /health /ready 信息裁剪

**问题**
`server/api.py:826-835` 未鉴权暴露 `anthropic_base_url`、`credential_source`、`dotenv_path`。

**修复**
1. 公开版 `/health` 仅返回 `{"status":"ok"}` 和 `{"version": ...}`。
2. 详细诊断挪到 `/internal/diagnostics`，强制走 `verify_tenant` 且仅允许 `tenant=admin` 或 `DIAGNOSTICS_ALLOWED_TENANTS` 白名单。
3. `platform/diagnostics.py:15-75` 拆分 `public_status()` / `internal_status()` 两个函数。

**验收**：`curl /health` 不再泄露 URL/路径字段。

---

### F4. P0-3 上传文件名冲突与保留名

**问题**（已按 Codex 反馈修订）
- `_sanitize_upload_name` 只做 basename，同批同名附件互覆盖。
- Windows 保留设备名（`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`）未过滤。

**修复**
```python
WINDOWS_RESERVED = {"CON","PRN","AUX","NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}

def _sanitize_upload_name(name: str, index: int, used: set[str]) -> str:
    stem = Path(name).name or f"upload-{index}"
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
    if Path(stem).stem.upper() in WINDOWS_RESERVED:
        stem = f"upload-{index}-{stem}"
    # 同批冲突加后缀
    base, suffix = Path(stem).stem, Path(stem).suffix
    candidate, n = stem, 1
    while candidate in used:
        candidate = f"{base}-{n}{suffix}"
        n += 1
    used.add(candidate)
    return candidate
```

**验收**：上传两个同名 `scan.pdf` → 存为 `scan.pdf` + `scan-1.pdf`；上传 `CON.pdf` → 存为 `upload-0-CON.pdf`。

---

### F5. P0-2 时序安全字符串比较

**修复**
```python
import hmac
def verify_tenant(api_key: str) -> str:
    token = api_key.replace("Bearer ", "", 1).strip()
    for tenant, key in TENANT_KEYS.items():
        if hmac.compare_digest(key, token):
            return tenant
    raise HTTPException(status_code=401, detail="Invalid API key")
```

**验收**：保留现有单测通过；新增一条构造不同长度 key 的用例，确保 `compare_digest` 不抛异常。

---

## Phase 2 —— 下周

### F6. P0-4 / P0-5 路径穿越 & symlink

- `_validate_directory_case_path`：`resolved.is_symlink()` 或 `resolved not in SUBMISSION_ROOT_DIR.parents` → 400。
- `prepare_text_proxy`：`source_path.resolve()` 后必须在 `SUBMISSION_ROOT_DIR` 白名单内。
- 新增测试：软链指向 `/etc/passwd` → 400。

### F7. P1-1 后台任务生命周期

- `_schedule_directory_audit_task` 保存 task 引用到 `app.state.background_tasks`。
- `add_done_callback(_log_background_error)` 记录异常 → `requests/audit.log`。
- FastAPI `lifespan` shutdown：`await asyncio.gather(*tasks, return_exceptions=True)` + 超时强制 cancel。

### F8. P1-3 upsert 容错

- `upsert_audit_task` 对 `AuditTaskRecord(**merged)` 用 `try/except (TypeError, KeyError)` 包住，降级为 warning + 跳过，不阻断 lifespan。

### F9. P1-2 recover_stale 并发控制

- 仅当 `os.environ.get("WORKER_RANK","0") == "0"` 或新增 `RECOVER_STALE_ENABLED` flag 时执行。
- 文档说明：NFS 部署下禁用 `flock`，改用外部分布式锁（后续任务）。

---

## Phase 3 —— 后续

### F10. P2-1 api.py 拆分 routers
- `server/routers/audit.py` / `chat.py` / `sessions.py` / `diagnostics.py`。

### F11. P2-2 config 错误提示
- `_env_int` 包 `RuntimeError(f"invalid int for {name}: {value!r}")`。

### F12. P1-4 → P2 NoReturn 类型标注
- `_raise_endpoint_error` 返回类型 `NoReturn`；跑 mypy 扫一遍。

---

## 落地顺序 & 工时估算

| # | 任务 | 优先级 | 估时 | 依赖 |
|---|---|---|---|---|
| F1 | agent 工具链收敛 | P0-0 | 1.5d | 测试基线 |
| F2 | 删 sk-default | P0 | 0.2d | — |
| F3 | /health 裁字段 | P0 | 0.5d | — |
| F4 | 上传名冲突 | P0 | 0.5d | — |
| F5 | compare_digest | P0 | 0.2d | — |
| F6 | 路径穿越 | P0 | 0.5d | — |
| F7 | 后台任务生命周期 | P1 | 0.5d | — |
| F8 | upsert 容错 | P1 | 0.3d | — |
| F9 | recover_stale 并发 | P1 | 0.3d | — |

Phase 1 合计约 3 人日，Phase 2 约 1.5 人日。

## 验收清单

- [ ] Phase 1 全部合入后重跑 `pytest tests/server/`
- [ ] 新增 agent surface 测试 ≥ 3 条（路径穿越、超长 prompt、禁用工具）
- [ ] `curl -s /health` 输出字段 ≤ 2 个
- [ ] 未设 `TENANT_KEYS` 启动进程 → 立即失败
- [ ] `.ai_state/reviews/sprint-N.md` 记录本次修复的 review + 测试结果
