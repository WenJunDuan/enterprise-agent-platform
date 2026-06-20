# 全地址读取模式 — 外部源对接友好（设计 · 待下会话实现）

> Sprint 2026-06-20-external-source-mode · Path: **System**（触及 H4 路径安全）· 用户需求 #29。
> 本会话只出设计 + codex review；实现留新会话。

## 1. 现状（已查证）

接收文件 **2 种模式**（audit/ocr/tender 三域共用，`upload_helpers`）：
- **`directory`**：`{mode:"directory", directory_path}`，路径必须**已在 `<tenant>/<domain>/[<project>/]` 子树内**（`validate_directory_case_path` confine）。外部系统须先把文件拷进租户子树。
- **`upload`**：multipart form-data，文件字节流式 POST，`materialize_*` 落 `<tenant>/<domain>/[<project>/]<request_id>/`。
- `source_proxy.py` 只是 PDF→文本预处理（pdftotext），非外部源机制。无 URL/远程读取。

**痛点**：外部系统文件若已在共享盘（NFS/NAS）或 URL 上，现在必须①拷进租户子树 或 ②重新 multipart 上传——对外对接别扭。

## 2. 目标：新增 `external` 模式（全地址读取）

让外部调用方**指向已存在的文件地址**，无需预拷/重传。两类地址，分期：

### Phase 1：本地/挂载绝对路径（最常见企业集成）
`{mode:"external", source_path:"/mnt/shared/incoming/case-123"}` —— 外部系统把文件放共享挂载，API 直接读。
- **行为**：把 source_path 下文件**拷入** `<tenant>/<domain>/[<project>/]<request_id>/`（materialize 化），下游与 upload 模式完全一致 → retention 清理、租户隔离、新结构全自动适用。**不就地读**（就地读会让 eval 输入逃出租户子树、retention 管不到）。
- **安全（核心）**：
  - **allowlist**：env `EXTERNAL_SOURCE_ROOTS`（逗号分隔的允许根目录，如 `/mnt/shared`）。source_path `resolve()` 后必须在某个 allowed root 下，否则拒。**未配置 = 该模式整体关闭**（默认拒，不开口子）。
  - 防穿越：`resolve().relative_to(allowed_root)`（同 H4 手法）；拒符号链接逃逸（`is_symlink` 检查，仿 maintenance P1 修复）。
  - 大小/数量限制：复用 `max_upload_file_bytes` + 文件数上限，防超大目录拷爆磁盘。
  - 拷贝时 sanitize 文件名（`sanitize_upload_name`），扁平化（不递归保留任意深层结构，或限定深度）。

### Phase 2（留后）：URL 拉取
`{mode:"external", source_url:"https://..."}` —— fetch 远程文件落盘。更复杂：host allowlist、auth、超时、content-type/size 校验、SSRF 防护（拒内网地址/metadata 端点）。单独立项。

## 3. 影响范围（Phase 1）

- `server/platform/config.py`：加 `EXTERNAL_SOURCE_ROOTS` 解析（`get_external_source_roots()`，逗号分隔→resolved Path 列表；空=关闭）。
- `server/routes/upload_helpers.py`：新 `materialize_external_submission(*, request_id, tenant, domain, project_id, source_path)` —— allowlist 校验 source_path → 拷文件进 `build_case_dir(...)` → 返回 case_path。复用 `validate_upload_bytes`/`sanitize_upload_name`。
- 三路由请求模型加 `mode:"external"` 分支（audit/ocr/tender 的 Directory*Request 扩成 union，或加 ExternalSubmitRequest `{mode, source_path}`）。
- 文档：`deploy/README.md` 记 `EXTERNAL_SOURCE_ROOTS` + 对外对接约定。
- 测试：allowlist 命中/未命中拒、未配置拒、穿越拒、symlink 拒、拷贝落新结构、大小限制。

## 4. 安全红线（不可破）
- 默认关闭（`EXTERNAL_SOURCE_ROOTS` 未配 → 拒）——绝不默认开任意路径读取。
- 只读 allowlist 根下；resolve + relative_to + symlink 检查三重防穿越。
- 拷入租户子树后处理（不就地读），retention/隔离/新结构全继承。

## 5. 验收
- 配 `EXTERNAL_SOURCE_ROOTS=/tmp/allowed`，external 模式读 `/tmp/allowed/case/` → 文件拷进 `<tenant>/<domain>/<rid>/`，评标正常。
- 未配置 / 路径在 allowlist 外 / `../` 穿越 / symlink 逃逸 → 拒（400/403）。
- 不影响现有 directory/upload 两模式。
- `uv run pytest -q` 全绿 + ruff + codex/cc 交叉审查（System + 安全敏感）。

## 6. 待 codex review 决策点
1. Phase 1 只做本地绝对路径（allowlist）是否够，URL 是否该一期一起。
2. external 模式**拷入** vs **就地读**——拷入(推荐,继承隔离/retention) vs 就地(省拷贝但破子树模型)。
3. allowlist 粒度：全局 `EXTERNAL_SOURCE_ROOTS` vs 按租户 `EXTERNAL_SOURCE_ROOTS_<tenant>`（多租户场景外部根是否该隔离）。
4. 请求模型：mode union 扩展 vs 独立 external 端点。
