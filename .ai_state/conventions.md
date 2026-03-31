# 项目约定

## 核心原则

- 路由放在 `.claude/CLAUDE.md`，流程放在 agents，原子能力放在 skills，规则只放在 `knowledge/`。
- Python 代码只负责 Claude 调用适配、输入输出适配、日志、schema 校验和 hook 执行，不写业务判断。
- `init-rules`、`audit` 等业务能力只能定义在 `.claude/commands` / `.claude/skills`，不能在 Python 里重写第二份业务流程。
- CLI 与 serve 必须共用同一套 Python 调用适配层；两者差异只允许存在于终端输出与 HTTP JSON/SSE 输出。
- 服务层的调用契约、JSON 返回约束、鉴权和会话控制属于 `.ai_state` 约定，不写进 `.claude/CLAUDE.md`。
- 所有 SDK 调用都必须设置 `setting_sources=["project"]`，确保 `.claude/` 配置被加载。
- 最终结构化结果统一写入 `logs/results/`，会话日志统一写入 `logs/sessions/`。
- 不确定时优先返回 `manual_review`，不要在 agent 或 Python 中编造规则。

## Agent 易犯错误

- 在 Python 或 agent 文本里硬编码规则，而不是读取 `knowledge/*.json`。
- 结果里缺少 `policy_refs` 或 `evidence_chain`，导致 hook 拦截。
- 把最终结果写到 `logs/results/` 之外，绕过质量检查。
- 忘记区分确定性构件与概率性构件：拦截必须走 hook，不能只靠 skill。
