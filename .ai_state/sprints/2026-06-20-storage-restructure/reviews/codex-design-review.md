# Codex 设计评审 — 存储结构改造

> Codex (gpt-5.5) · 2026-06-20 · 120K tokens · 对象 design.md

## VERDICT: **APPROVE-WITH-CHANGES**（4 P1 全纳入）

| # | P1 | 修订 |
|---|---|---|
| 1 | `_unbound` 违反白名单（首字符不能 `_`） | sentinel 改 **`unbound`**（无前导下划线）；声明不与 `tp-<hex>` 项目 ID 冲突 |
| 2 | materialize 直接拼 `SUBMISSION_ROOT_DIR/tenant/rid`，绕过 tenant 白名单 | 统一 `tenant_submission_root(tenant)/domain/...`，对 domain/project_id/request_id 都走安全段校验 → H4 白名单覆盖 upload 模式 |
| 3 | `validate_directory_case_path` 只 confine tenant 根，新 domain 结构不够 | 加 `expected_domain` + 可选 `expected_project_id`；拒绝 tenant 根/domain 根/错误 domain（不改 H4 边界，防同租户跨域误读） |
| 4 | maintenance 非"结构无关"：orphan 只扫 1 层、known 只含 audit task、old 用 CWD resolve | 改递归到叶子 case 目录清理；known 纳入 **audit+tender** task；relative case_path 统一按 PROJECT_ROOT 解析 |

## 决策点（codex 确认）
1. 投标人目录用 `request_id` ✓（企业名上传时不稳定/中文空格碰撞）。
2. legacy tender 保留 sentinel 层，用 `unbound`（不要 `_unbound`/不要 `tender/<rid>`）。
3. audit/ocr 也加 domain 命名空间值得做（统一模型，改动可控）。
4. domain 用**枚举集合**校验（不只 regex）；project_id 用 `tp-...` 或 legacy sentinel 规则。
5. 无需迁移（submissions 空）；DB case_path 透传透明，**唯 maintenance 必须修**；前提：无 accepted/running 旧 upload 任务依赖旧目录（工作区已清，成立）。
