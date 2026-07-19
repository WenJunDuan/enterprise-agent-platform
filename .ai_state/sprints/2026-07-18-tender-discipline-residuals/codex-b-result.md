Batch B 已实现并提交，未 push、未触碰 main。

Commits:

- `de78184` `feat(tender): derive evidence chain from scoring hits`
- `2677c64` `fix(tender): stamp tender reviewed-by metadata`
- `009f105` `fix(tender): warn on OCR timeout budget mismatch`

验证结果：

- 相关测试：`297 passed`
- `uv run ruff check .`：通过

说明：共享 schema 的所需枚举已存在，因此仅新增 tender schema 回归测试，未修改 schema 文件。INFRA-02 的 README/runbook 注记因用户允许修改清单限制未完成；启动日志提示已实现并测试通过。工作树仅保留原有 `.ai_state/_index.md` 改动。