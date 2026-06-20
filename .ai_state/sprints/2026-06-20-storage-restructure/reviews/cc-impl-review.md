# CC 代码评审 — submissions 存储结构改造实现

> Reviewer: Claude(主实现方自审) · commit storage(feat) · 2026-06-20 · 配套 codex-impl-review.md

## VERDICT: **PASS（1 项行为变更须文档化，无安全漏洞）**

353 passed/ruff。4 codex P1 全落实，新安全测试 9 例。核查无路径穿越/跨租户/跨域漏洞。

## 一、4 P1 落实核查（通过）

- **P1.1 unbound sentinel**：`UNBOUND_PROJECT="unbound"` 无前导下划线，过 `_SAFE_TENANT` 白名单；`tp-<hex>` 项目 ID 不会等于 "unbound"，无冲突。`test_unbound_project_passes_whitelist` 证。✓
- **P1.2 build_case_dir 复用 tenant 白名单**：`tenant_submission_root(tenant)`（含 tenant 白名单）/ `domain`(枚举 `SUBMISSION_DOMAINS`) / `_safe_segment(project_id/request_id)`——每段白名单，`../`/绝对路径/`/` 全拒。`test_build_case_dir_rejects_traversal_segment` / `_rejects_unknown_domain` 证。✓
- **P1.3 validate 跨域/根拒绝**：`expected_domain` confine 到 `<tenant>/<domain>[/<project>]`；`rel == Path(".")` 拒 confine 根本身；`relative_to` ValueError 拒跨域/跨项目。三路由都传对 domain（audit→audit、ocr→ocr、tender→tender+project）。`test_validate_rejects_wrong_domain` / `_domain_root` / `_tender_project_subtree` 证。✓
- **P1.4 maintenance**：`_iter_leaf_case_dirs` 域感知 glob（`*/audit/*`、`*/ocr/*`、`*/tender/*/*`）只取叶子、不碰中间目录；`_known_case_dirs` 纳入 audit+tender（compare `case_path="-"` 排除）；`_resolve_case_path` 按 PROJECT_ROOT；`cleanup_old` 同步改 `_all_upload_tasks`。3 maintenance 测试改新结构验证。✓

## 二、安全核查（无新漏洞）

- **H4 租户隔离不破**：tenant 仍在路径最外层，`tenant_submission_root` 是唯一构造入口，validate confine 默认仍 tenant 根（传 domain 时收紧）。跨租户测试（`test_evaluate_directory_cross_tenant_rejected` 等）仍过。
- **路径穿越**：domain 枚举 + 段白名单 + `resolve().relative_to(confine)` 三重；无绝对路径/`..`/symlink 逃逸口。
- **remove_submission_dir 不变**：仍 confine submissions 根，新深层路径透明（case_path 是完整新路径）。
- **OCR /fill**：`materialize_ocr_upload` 默认 `domain="ocr"`，两端点都走新结构。

## 三、行为变更（须文档化，非 bug）

- **directory 模式外部调用方**：现在必须把文件预置到 `<tenant>/<domain>/[<project>/]<rid>/`（旧为 `<tenant>/<rid>/`）。upload 模式（前端用的）由 materialize 自动落新结构，**不受影响**；前端拿 case_path 不自己构造路径，无需改。
- 这正好衔接用户下一需求（"全地址读取"对外友好）——directory 模式的外部对接约定可在那里一并明确。

## 四、明确排除
- 无其它硬编码旧 `<tenant>/<request_id>` 结构（audit/ocr runner 读 case_path 不构造）。
- DB `case_path` 存完整相对路径字符串，worker/runner 透传透明。
- 死数据已清（data/contracts 死域 + smoke），data gitignored 不影响 git。
