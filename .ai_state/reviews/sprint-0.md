# Sprint-0 Review — /audit/submit 零附件支持

- 日期: 2026-04-13
- 范围: `server/api.py` 附件守卫拆除 + 新增 2 条回归测试 + 前端对接文档同步
- 交付者: 主 Agent (Sonnet 4.6)
- 审查者: `feature-dev:code-reviewer` 子 agent（独立会话，未见实现过程）

## 改动清单

| 文件 | 改动 |
|---|---|
| `server/api.py` | 删除 `_materialize_upload_submission` 内 `if not files: raise HTTPException(400, ...)` 硬守卫；保留 `files = form_data.getlist("files")`。下游循环对空列表本就安全。 |
| `tests/test_audit_submit_attachments.py` | 新建：`test_audit_submit_upload_without_files`（手写 multipart，0 附件）+ `test_audit_submit_upload_with_multiple_files`（httpx `files=`，2 附件）。隔离通过 monkeypatch `SUBMISSION_ROOT_DIR`/`_schedule_directory_audit_task`/`upsert_audit_task`/`recover_stale_audit_tasks`。 |
| `.ai_state/docs/前端审核服务对接文档.md` | 4.3 节"一个或多个附件" → "零个或多个附件（可选）"；§12 错误码表删除 `400 At least one file is required for upload mode`。 |

## 验证

- `uv run pytest tests/test_audit_submit_attachments.py -v` → 2 PASS
- `uv run ruff check server/api.py tests/` → All checks passed

## 审查结论

**PASS (≥4.0)**

独立审查覆盖：
- 安全面：`_validate_form_payload` 独立于附件；无下游代码假设 `attachments` 非空（全局搜索 `attachments[0]`/`len(attachments)>0`/`if attachments` 零匹配）。
- 正确性：空附件路径不触发 `shutil.rmtree(case_dir)`，`audit-request.json` 正常落盘。
- 测试真伪：monkeypatch 作用于模块命名空间；`TestClient` lifespan 在首个请求触发，patch 已提前生效；httpx `files=[("files", ...), ("files", ...)]` 会产生 2 个同名 part，`getlist("files")` 返回 2 个 `UploadFile`。
- 回归面：仅 `_materialize_upload_submission` 受影响；JSON directory 模式、session、audit task 查询均无耦合。
- 文档一致性：§11 "用户选择一个或多个文件" 是 UX 引导，非后端约束，不需同步。

## 经验/踩坑（建议入 lessons.md）

1. httpx `TestClient` 在 `files=` 空或缺失时不保证使用 `multipart/form-data`；零附件回归测试应手写 multipart body 并显式设置 `Content-Type; boundary=...`，避免退化为 `application/x-www-form-urlencoded` 导致端点分发到错误分支。
2. FastAPI 模块级常量（如 `SUBMISSION_ROOT_DIR`）通过 `from ... import X` 导入后，测试 monkeypatch 需作用于**目标模块**（`server.api`），而非原模块（`server.platform.paths`），否则运行时读到旧绑定。
