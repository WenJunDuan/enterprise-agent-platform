# Runtime Verify — Tender Report Dimensions (D0–D6)

> 本轮 impl 后的运行时验证（实跑接口 + 真实 UI 试用 + 自测自改）。证据来自本会话实跑。

## 环境

- 后端：`uv run python -m server.cli serve`（:9999，含 dist 静态托管）。
  **启动必须清掉从 Claude Code 继承的 `ANTHROPIC_*`**（否则 `ANTHROPIC_BASE_URL=api.anthropic.com`
  盖过 .env 网关，触发离线护栏 `ClaudeRuntimeError`，criteria 抽取与评标全失败）。
- 前端：`bun run dev`（vite :5173，代理 /audit /ocr /tender → :9999）。
- 模型：.env 网关（实跑时为 deepseek-v4-pro / dashscope，用户自选）。

## 实跑与自改记录

1. **D0 跨域回归（修复前实证 → 修复后消失）**
   - 修复前：expense 结论 `…金额在预算内。综上，本次差旅报销合计 1200 元…予以通过。`
     被 `_finalize_user_explanation` 整句删成 `…金额在预算内`。
   - 修复后实跑 `enrich_audit_decision(...)`：结论**完整保留**。tender happy-path 小结仍服务端
     重算（模型写错的 999/86 被纠正为真实合计）、rejected 仍加「资格审查不通过，按废标处理」前缀。
2. **真实评标实跑（用户 UI 触发）**：修复 ANTHROPIC_* 后，后端日志连续 `session_end
   result_subtype: success`（无 `ClaudeRuntimeError`）；用户确认报告「效果可以」。
3. **资格审查独立类目**（用户反馈 → 自改）：原 codex 误把 eligibility 塞进 'tech'；改归 'qual'
   独立并列列；测试同步锁定。
4. **D6 类目动态化**（用户反馈 → 实现 + 自测）：criteria 加 `category`、S1 抽取、前端动态分栏；
   模型测试覆盖「资格审查 / 商务标 / 技术标 按标书 category 动态分栏、doc 顺序、原名作小标题」。

## 门禁（commit/push 前实跑，全绿）

```text
uv run pytest -q            → 727 passed, 8 warnings
uv run ruff check .         → All checks passed!
bun test model.test.ts      → 11 pass, 0 fail
bun run build               → ✓ built
eslint tender-review        → clean
```

## 已知边界（非阻塞）

- D6 真实 doc 类目需**新评标**才带 `category`；既有结果回退关键词推断的技术标/商务标，不报错。
- 后端启动的 ANTHROPIC_* 清理是本机用 Claude Code 启动的特例；用户自有终端启动无此问题
  （见 [[2026-06-25-trick-codex-proxy-hangs-streaming]] 同源环境继承问题）。
