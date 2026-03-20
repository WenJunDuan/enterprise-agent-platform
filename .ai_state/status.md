# 项目状态

## 当前阶段
E/T (实现与验证)

## 路径
B (标准开发)

## 当前状态
- 已完成最小可运行底座：`server/api.py`、`server/config.py`、`server/core.py`、`server/model_client.py`、`server/logging_config.py`
- 已完成 CLI-only `/init` 规则初始化骨架：`server/cli.py`、`server/rule_init.py`
- 已完成业务运行记忆底座：`knowledge/memory/`、`server/memory_writer.py`
- 已完成 `knowledge/_schema/`、`knowledge/expense/`、`knowledge/hr/` 的首版规则与字段 schema 落库，并补齐 `server/models.py`
- 已修复 `/init` 与新增规则目录的集成问题：支持 `expense` 新分类与 `hr` 域目标文件，默认忽略 `knowledge/external/` 下的可查看抽取稿/README，且不再覆盖已有 `rule.schema.json`
- 当前仓库状态为“最小可运行链路 + 可查看制度抽取稿 + 首版规则库”，还未进入“真实业务可审核闭环”

## 当前任务
P0 优先补齐费控闭环最小样板：
- `data/pre-approvals/`、`data/invoices/` 等最小联调数据
- 基于 `server/core.py` 的正式结构化审核入口与统一输出协议
- 继续把现有规则库与样例数据接到可执行审核链上

## 进度
3/6 完成（最小底座、`/init` 骨架、首版规则/schema 已完成，业务闭环主链待继续推进）

## 当前验证
- `python3 -m pytest -q`: 54 passed
- `ruff check .`: passed
- 本轮 `curl http://127.0.0.1:8011/health` 与 `POST /chat` 未通过，原因是本地当前没有服务在 `127.0.0.1:8011` 监听，不能据此判断代码回归失败

## 最后更新
2026-03-20
