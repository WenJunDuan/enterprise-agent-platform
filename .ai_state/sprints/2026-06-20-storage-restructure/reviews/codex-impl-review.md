# Codex 代码评审 — submissions 存储结构改造实现

> Codex (gpt-5.5) · commit storage(feat) · 2026-06-20 · 128K tokens

## VERDICT: **REWORK**（1 P1 安全漏洞 + 2 P2；P1.1-P1.3 落实确认 OK）

| # | 级别 | 问题 | 修复 |
|---|---|---|---|
| 1 | **P1** | **orphan 清理 symlink 逃逸**：`_iter_leaf_case_dirs` 用 `is_dir()`(跟随 symlink)，cleanup_orphan `rmtree(resolved)` 未重校验 resolved 在 submissions 根内 → 目录 symlink 叶子可删外部数据 | `_iter_leaf_case_dirs` 加 `not p.is_symlink()`；cleanup_orphan resolve 后 `relative_to(submission_root)` 再校验，逃出即跳过 |
| 2 | P2 | `build_case_dir` 不强制 domain 拓扑：允许 tender 无 project_id、audit/ocr 带 project_id（路由传对了不是 active bug，但 helper 可造 maintenance 不识别的形状） | tender 强制要 project_id；audit/ocr 拒绝 project_id |
| 3 | P2 | 测试缺 maintenance 安全 + 路由落盘：无 symlink-orphan 测试、无 tender known 测试、无 cleanup_old tender/compare `"-"` 测试、无路由级 materialize 到新结构断言 | 补这些测试 |

## Confirmed OK（codex 明确排除）
- P1.1 `unbound` 安全、不与 `tp-<hex>` 冲突。
- P1.2 `build_case_dir` 用 `tenant_submission_root` + 枚举 domain + 安全段。
- P1.3 audit/ocr/tender 都传对 expected_domain，tender 传 project；`rel == Path(".")` 是正确的根校验。

## 处置：REWORK→fixed（本轮）
P1 symlink + P2.1 topology + P2.2 tests 全修，见 storage-impl 收口 commit。
