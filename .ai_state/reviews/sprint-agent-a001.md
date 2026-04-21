# A-001 自审：命令单一事实源收口

## 结论

- VERDICT: PASS

## 本轮目标

- 让 `audit` / `init-rules` 的业务入口说明只存在于 `.claude/commands/`
- 让 Python adapter 只负责参数映射与 slash command 调用
- 去掉 `server/prompts/` 对业务语义的重复承载

## 实际改动

- `server/command_adapter.py`
  - 删除 `load_prompt()` / `validate_prompts()` / `build_audit_prompt()` / `build_init_rules_prompt()`
  - `run_command_full()` / `run_command_json()` 统一走 `build_command_prompt()`
  - 新增参数序列化逻辑：当参数包含空格、引号或反斜杠时，用 JSON string quoting 生成稳定的 slash command 参数
- `.claude/commands/audit.md`
  - 把历史 `data/claims/CLAIM-001.json` 示例改为当前主线 `data/case1`
- 删除
  - `server/prompts/audit.md`
  - `server/prompts/init-rules.md`
- `tests/test_command_adapter.py`
  - 改为断言 adapter 直接调用 `/audit ...` / `/init-rules ...`
  - 补路径带空格的 quoting 回归

## 为什么这版更对

1. 业务入口定义回到了 `.claude/commands/`，避免 HTTP/CLI 路径和 Claude 原生命令路径出现双重事实源。
2. Python adapter 的职责更纯：只负责 transport，不再维护业务语义文本。
3. 参数序列化比原先直接 join 更稳，至少覆盖了“路径含空格”的常见问题。

## 风险与观察点

- 当前采用的是 slash command 文本调用，因此参数 quoting 依赖 Claude 对命令参数的解析行为。现有自动化测试只验证了 Python 侧生成的命令字符串；不过已补做一次真实 smoke test，确认 `audit-json` 实际进入 Claude 审核链路并返回结构化结果。
- `init-rules` 常见路径当前大多没有空格，因此风险较低；但如果用户后续频繁使用带空格的本地路径，建议在真实 CLI / HTTP 路径上补一条集成测试或实机验证。
- `.ai_state` 历史文档里仍保留了 `server/prompts/` 的实现记录，这属于演进历史，不是当前事实；后续如果做一次文档收口，应统一标注“已被 A-001 取代”。

## Review Follow-up（2026-04-21）

- 已把原先在 `server/prompts/audit.md` 中承载、但在 A-001 初版中遗漏回填的关键结构化约束补回 `.claude/commands/audit.md`，包括：
  - `manual_review_reason` 枚举要求
  - `risk_dimensions` 形状约束
  - “只返回一个 JSON 对象”
  - “不要输出 JSON 之外的文字”
  - “不要手工写重复结果文件”
- 已统一 README 与蓝图口径，明确：
  - Python 只运行服务、获取外部输入、做鉴权/持久化并把输入交给 Claude
  - Claude 负责审核判断、规则命中、证据组织和结论生成
- 已执行真实 smoke test：
  - 命令：`uv run python -m server.cli audit-json data/case1`
  - 结果：由于 `data/case1` 不存在，Claude 返回结构化 `manual_review`
  - 观察：会话事件日志显示 Python 仅提交 `/audit data/case1`；后续读取路径、发现路径不存在、填充 `manual_review_reason=insufficient_evidence` 与最终 JSON 结果都由 Claude 完成

## 验证

- `uv run pytest tests/test_command_adapter.py` 通过
- `uv run pytest` 通过，当前共 28 项
- `uv run ruff check server tests` 通过

## 下一步建议

- 进入 A-002：收口 agent / skill 关系，并为 `extractor -> auditor -> reviewer` 增加中间契约
- 在进入 A-003 业务记忆层前，先把单域 agent 链条的输入输出稳定下来，避免后续记忆层绑定到漂移中的结构
