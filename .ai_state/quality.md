# 质量报告

> 由 verification + code-review skill 在 T 阶段写入

## 验证报告
- 日期: 2026-03-20
- `python3 -m pytest -q`: 54 passed
- `ruff check .`: passed
- 本轮本地服务 smoke test:
  - `curl http://127.0.0.1:8011/health` 返回连接失败
  - `curl -X POST http://127.0.0.1:8011/chat ...` 返回连接失败
  - 当前原因不是代码异常，而是本轮检查时本地没有服务在 `127.0.0.1:8011` 监听
- 最近一次已知成功的 live 验证:
  - `GET /health` 返回 `200 OK`
  - `POST /chat` 成功返回 `{"model":"gpt-5.4","response":"服务联通测试成功"}`
  - 上游客户端已切换为 `httpx`，不再使用此前表现不稳定的 `urllib`
- 日志能力验证:
  - 启动命令: `APP_LOG_LEVEL=DEBUG APP_LOG_FILE=/tmp/enterprise-agent-service.log python3 -m uvicorn server.api:app --host 127.0.0.1 --port 8012 --env-file .env`
  - `/tmp/enterprise-agent-service.log` 实际包含 `DEBUG / INFO / WARNING / ERROR`
- CLI `/init` 验证:
  - `tests/test_cli.py` 覆盖交互确认、取消、写入报告
  - `tests/test_rule_init.py` 覆盖 schema/规则骨架生成、advanced source 提示、已有规则文件合并、`hr` 目标文件生成、`knowledge/external/` 抽取稿过滤、已有 schema 保留
  - `tests/test_api.py` 明确验证 `/init` 不通过 HTTP 暴露
  - 为了保留命令的交互确认语义，本次没有直接在仓库根目录执行真实 `/init` 写入 `knowledge/`
- 规则库与字段 schema 验证:
  - `tests/test_knowledge_rules.py` 覆盖 `knowledge/_schema/`、`knowledge/expense/`、`knowledge/hr/` 的关键文件存在性与代表性规则字段
  - `tests/test_server_models.py` 覆盖 `server/models.py` 的核心业务对象与 JSON schema 暴露

## 审查报告
- 本轮修复前发现的阻断项已处理：
  - `/init` 已支持 `expense` 新分类与 `hr` 域目标文件生成，不再退化成仅 `general.rules.json`
  - `/init` 默认扫描 `knowledge/external/` 时，已忽略 `README.md` 与 `.structured.md` 等可查看抽取稿，避免反向污染规则库
  - `initialize_rules()` 不再覆盖已有 `knowledge/_schema/rule.schema.json`
- 剩余风险 1: 当前 `.txt` / `.md` 的规则提取仍是低置信度占位初始化，只适合作为人工修订起点，不应直接视为正式制度规则。
- 剩余风险 2: `.pdf` / `.docx` / 图片和其他未知格式目前统一归为需要确认的 advanced source，OCR/向量化方案需要后续单独设计并再次与用户确认。
- 剩余风险 3: 现有规则库已落地，但还缺 `data/pre-approvals/`、`data/invoices/`、`data/claims/` 的联调样例，尚未进入真实业务闭环验证。
- 剩余风险 4: `agent-cli init` 默认以当前工作目录为项目根目录运行，使用时应从仓库根目录执行。
