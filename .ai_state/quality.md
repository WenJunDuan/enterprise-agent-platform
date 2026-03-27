# Quality Gate

- 当前状态: PASS
- 已验证:
  - `.venv/bin/ruff check .` 通过
  - `.venv/bin/pytest` 通过（15 个测试）
  - `.venv/bin/python -m server.cli --help` 成功
  - `.venv/bin/python -m server.app_server --help` 成功
- 当前质量结论:
  - `server/` 已稳定为入口层 + `platform/` + `stores/` 三层结构
  - 结构化输出默认走 JSON Schema 契约，本地结果归档和请求/会话审计链路已打通
  - 运行态数据目录统一为项目根 `logs/`，不再存在 `server/logs` 的实现依赖
- 注意事项:
  - 当前验证仍以本地静态检查和单元测试为主，尚未在本轮执行真实 `ANTHROPIC_API_KEY` 的端到端调用
  - `app-server` 后台生命周期需要继续在真实长时间运行场景中观察
