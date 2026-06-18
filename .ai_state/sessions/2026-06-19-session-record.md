# 会话记录 · 2026-06-18→19 · 后端结构 + 日志 + 存储重构

> 一次长会话，跨 server 分层 / 企业日志 / validate 注册表 / data 存储重构 / 部署归并。
> 基线起点 origin/main；全程 TDD + 每步独立 commit + 全量 pytest。终态 **234 passed / ruff clean / 无循环导入**。

## 一、做了什么（按主题）

### 1. ui → agent-front 改名（`bbf40ac`）
整目录 git rename + 8 处引用修复（Dockerfile COPY、`server/api.py` 同源托管兜底路径、
.dockerignore、README、deploy 文档、前端报错文案、package.json 名）。会静默 404 的 api.py
兜底路径是关键修复点。

### 2. server/ 分层整理（Refactor，design `c1581d3` / ship `e705e65`）
消除 4 处结构债，依赖严格单向向下，新增 `tests/test_layering.py` 5 条守卫固化：
- A3 `b7eece9`：抽 `routes/deps.py`（verify_tenant 出 api），删 8 处 lazy import，解 api↔routes 环。
- A1 `e8ae42d`：抽 `server/ops/`（diagnostics/maintenance 出 platform），platform 回归纯叶子。
- A2 `cd02389`：契约模块下沉 `common/contract.py`，解 common→audit 域泄漏（边反转为 audit→common）。
  偏离原设计的 post_process 回调——relocation 更干净、零签名改动。
- A4 `516d17d`：command_adapter 直连源模块，断 core↔common 环。

### 3. agent-front 追踪策略（`7f44309`；曾误操作 `106b55d` 已 reset）
用户先要"忽略"→我误解成 git 取消追踪（rm --cached + gitignore）；用户纠正"要保持追踪，只是
CC 别关注"。已回退误操作，agent-front 保持正常追踪，决策记入 compound：CC 视其为 out-of-scope。

### 4. 企业日志 log4j2 化（`68bdd8d`）
`configure_logging` 在 console appender 外新增 file appender：`logs/app/app.log`(INFO+) +
`error.log`(WARN+ 独立)，RotatingFileHandler size 滚动 + gz 备份，文件始终 JSON；
env 驱动 LOG_TO_FILES（默认关，测试不写盘）/ LOG_MAX_BYTES / LOG_BACKUP_COUNT；serve/app-server
默认开。先删了 logs/tmp 23M 陈旧 OCR 测试残渣。

### 5. validate 调度器 → 注册表（`8867f13`，OCP）
`common/contract.py` schema-keyed if/elif → `register_schema_processor` + `apply_schema_semantics`；
json_bridge 不再认识具体 schema 名；加新 schema = 一次 register。

### 6. data/ 业务存储重构（深度设计 `1e1fc3a`，7 步）
决策 A1 统一单库 + B1 payload 折叠进列。**净 -198 行**。
- step1 `c3324ae`：统一单库 `data/db/platform.sqlite3`(6 表+WAL)；logs/ 只剩运行日志；blob 迁 data/。
- step4 `3efd853`：audit_tasks 从 tasks.json 全量重写 → sqlite 表（merge upsert + 索引）。
- step2+3 `05c67a7`：result/review payload 折叠进 TEXT 列，去 by-request 文件树 + 指针。
- **step5 纠偏**：memory 文件保留 knowledge/memory（CLAUDE.md distill 契约 + asset_validation 依赖），
  不挪 data/；index 已随 step1 入统一库。
- step6 `5f1a1ab`：清 legacy JSONL 双后端（request 不再双写）+ 死类（-360 行）。
- step7a `947382d`：清死常量/vestigial 参数；storage_report 改报统一库。
- step7b `74c5a1f`：migrate-storage CLI（旧 logs/ → 统一库幂等迁移）+ 文档同步。

### 7. 收尾清理（`e40c05f` / `86860d8` / `5a4b377`）
- 低风险修：connect_sqlite 加 immediate（BEGIN IMMEDIATE），audit_task upsert 读-改-写原子化。
- 死代码：storage.py 4 个 JSONL 函数 + config.py session_store_max_shard 配置 + session_records._month_key。
- 失效注释：diagnostics storage_backend 标签；各 store docstring。
- 废弃目录：先跑 migrate-storage 再删旧 logs/ 业务目录 + data/ 空子目录。

### 8. prod/ → deploy/prod/ 归并（`7122b31`）
LiteLLM 生产 compose + config 从仓库根 prod/ 移到 deploy/prod/，与部署/排障文档归一处。纯 move。
**安全提示**：litellm_config.yaml 含硬编码内网 key（已在 git 历史），按用户决定原样追踪——
该 key 建议轮换（gitignore 无法抹历史）。

## 二、不是我的改动（混在历史里）
- `b3de6b7` feat(agent-front): migrate frontend framework —— 用户的前端重构。
- agent-front/.env 改名 —— 用户前端工作，我从 prod commit 里摘除未卷入。

## 三、终态
- `logs/`：app/{app,error}.log + runtime/app-server/（仅日志）。
- `data/`：db/platform.sqlite3（6 表）+ submissions/ + sessions/events/（业务数据）。
- `knowledge/memory/`：记忆产物（知识库归属）。
- 234 passed / ruff clean / 无循环导入；分层 5 守卫 + audit_task 6 + logging 4 + 注册表 5 + migrate 3 新测试。

## 四、遗留
- C 合同库实现（随合同审计开工，设计见 design-data-storage.md §C）。
- 日志按天滚动 toggle（如需）。
- litellm_config.yaml 已泄露 key 轮换（运维侧）。
