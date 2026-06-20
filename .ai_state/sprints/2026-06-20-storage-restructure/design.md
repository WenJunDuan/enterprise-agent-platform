# 存储结构改造 — submissions 域命名空间 + tender 项目层级（设计）

> Sprint 2026-06-20-storage-restructure · Path: **System**（触及 H4 租户隔离安全边界 + audit/ocr/tender 三域）。
> 驱动：用户指出当前 `submissions/<tenant>/<request_id>/` 扁平，不体现 tender 的"招标项目→投标人"域模型；要求 audit/ocr 一起改。
> 前置：死数据已清（data/contracts/ 死域 + smoke 测试目录）。

## 1. 现状（已查证）

```
data/submissions/<tenant>/<request_id>/   ← 扁平，audit/ocr/tender 三域共用，无域/项目区分
   ├─ <上传文件>
   └─ audit-request.json (metadata sidecar, ocr 不写)
```
- 路径逻辑：`upload_helpers.py` — `materialize_upload_submission` / `materialize_ocr_upload`（都 `SUBMISSION_ROOT_DIR/<tenant>/<request_id>`）、`validate_directory_case_path`（confine `<tenant>/` 子树 = H4 隔离边界）、`remove_submission_dir`（confine submissions 根）。
- **文件是 ephemeral 工作副本**（gitignored + `SUBMISSION_RETENTION_DAYS` 到期清理）；系统真相在 DB（`results.payload`）。
- 缺口：tender Phase1/2 在 DB 建了 `项目→N 投标人` 层级（`results.project_id`），但文件系统没体现。

## 2. 目标结构

```
data/submissions/<tenant>/audit/<request_id>/          ← audit 域命名空间
data/submissions/<tenant>/ocr/<request_id>/            ← ocr 域命名空间
data/submissions/<tenant>/tender/<project_id>/<request_id>/   ← tender 加项目层级(按招标分组)
data/submissions/<tenant>/tender/_unbound/<request_id>/       ← 旧 /tender/evaluate 无 project 时
```

**铁律级约束**：
- **`<tenant>/` 必须在最外层**——H4 租户隔离的安全边界，`validate_directory_case_path` 仍 confine 到 `tenant_submission_root(tenant)`，不能为了域/项目把租户挪进去。
- **域名 / project_id 走白名单**（同 tenant 白名单 `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`），防 `../` 穿越。project_id 本就是服务端生成的 `tp-<hex>`，天然安全。

## 3. 投标人目录命名（决策点）

bidder 企业名在**上传时未知**（评标时 Claude 才抽取），且企业名含中文/空格/可能碰撞 → **不适合直接做目录名**。
- **方案 A（推荐）**：叶子用 `request_id`（上传时已知、唯一、安全）；企业名存进 metadata sidecar。`<tenant>/tender/<project_id>/<request_id>/`。
- 方案 B：`<bidder_sanitized>-<request_id_short>`（人类可读 + 唯一）。但企业名上传时前端才传 `bidder_name`（可空），且 sanitize 中文损失大。
- 取 A：可靠、安全；"按企业浏览"靠 DB（results.claim_id）+ metadata，不靠目录名。

## 4. 影响范围

- `server/routes/upload_helpers.py`：
  - `materialize_upload_submission(..., domain, project_id=None)` → 路径 `<tenant>/<domain>/[<project_id>/]<request_id>/`。
  - `materialize_ocr_upload(..., domain="ocr")`。
  - 加 `_safe_segment()` 校验 domain/project_id（白名单，防穿越）。
  - `validate_directory_case_path` / `remove_submission_dir`：confine 边界不变（仍 `<tenant>/` 根 / submissions 根）——深层结构变化对它们透明。
- `server/routes/audit.py`：`materialize_upload_submission(..., domain="audit")`。
- `server/routes/ocr.py`：`materialize_ocr_upload(..., domain="ocr")`。
- `server/routes/tender.py`：`_submit_bid_evaluation` 传 `domain="tender", project_id=project_id or "_unbound"`。
- 保留期清理（`server/ops/maintenance.py` 若按 mtime 扫 submissions）：结构无关，应仍工作——需核对。
- 测试：upload_helpers + 三路由测试改新路径；跨租户隔离回归（核心：tenant 仍是边界）。

## 5. 迁移

- 无需迁移：submissions 是 ephemeral + 现有内容已全删（测试数据）。新上传即用新结构。
- DB 不动（case_path 列存新的相对路径字符串，读写透明）。

## 6. 验收

- audit 上传 → `<tenant>/audit/<rid>/`；ocr → `<tenant>/ocr/<rid>/`；tender(项目内) → `<tenant>/tender/<pid>/<rid>/`；旧 tender → `<tenant>/tender/_unbound/<rid>/`。
- 跨租户/路径穿越仍被拒（H4 回归）：directory 模式不可读他租户、不可 `../` 逃逸。
- `uv run pytest -q` 全绿 + ruff + 路由表不变。
- codex + cc 代码交叉审查（System 路径）。

## 7. 待 codex review 决策点

1. 投标人目录用 request_id（A）vs 企业名+rid（B）——安全 vs 可读。
2. 旧 `/tender/evaluate`（无 project）放 `tender/_unbound/<rid>` vs 直接 `tender/<rid>`。
3. domain 命名空间是否值得给 audit/ocr 也加（vs 仅 tender 加项目层、audit/ocr 不动）——一致性 vs 改动面。
4. 是否需要 `validate_directory_case_path` 额外校验"directory 在正确的 domain 子树"（更严格）vs 只 confine tenant（够不够）。
