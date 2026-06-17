"""基础设施：Claude SDK 桥接层与会话日志。

- agent_bridge.py    build_options / run_agent / run_agent_full + ClaudeRuntimeError
- json_bridge.py     run_agent_json（结构化输出入口）
- session_logging.py SessionLogger 与 CLI stderr / 桥接失败日志
- command_adapter.py slash command 适配

对外稳定入口仍是 `server.core` facade；本包是其实现归属。
"""
