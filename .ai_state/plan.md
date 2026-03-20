# 开发计划

> 由 plan-first skill 在 P 阶段写入, E 阶段逐项完成

## 任务清单
- [x] T-001: 落地最小 HTTP 服务与日志链路 — 45min — `server/api.py`, `server/model_client.py`, `server/logging_config.py`, `tests/test_api.py`, `tests/test_model_client.py`, `tests/test_logging_config.py`
- [x] T-002: 落地 CLI-only `/init` 规则初始化骨架 — 45min — `server/cli.py`, `server/rule_init.py`, `tests/test_cli.py`, `tests/test_rule_init.py`
- [x] T-003: 将 `knowledge/expense/` 的样例规则和 schema 从“初始化骨架”推进到“可用样例” — 60min — `knowledge/_schema/rule.schema.json`, `knowledge/expense/*.rules.json`, `tests/`
- [ ] T-004: 为 PDF/DOCX/image 制度文件设计 OCR/向量化接入方案，并在启用前与用户确认 — 45min — `server/rule_init.py`, `README.md`
- [ ] T-005: 基于报销样例打通结构化审核入口，而不只是通用 `/chat` — 90min — `server/core.py`, `server/cli.py`, `tests/`
- [ ] T-006: 设计多公司 / 多业务域 / 多请求的统一隔离与队列方案，明确 `tenant_id`、`domain`、`request_id/job_id`、轻量队列与公平调度边界；待与用户专题讨论后再实施 — 60min — `server/`, `docs/`, `tests/`
