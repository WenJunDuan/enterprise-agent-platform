# 日志工程化 + 存储态梳理 Ship

> Sprint 2026-06-19 · B 日志(实现) + A validate 注册表(实现) 已交付；C 合同存储(设计就绪，待开工)。

## 成果

基线 216 → **225 passed**（+9：4 日志 + 5 注册表），ruff 全绿，分层守卫不退化。

| 线 | 改动 | commit |
|---|---|---|
| 清理 | logs/tmp 23M 陈旧 OCR 测试残渣删除（logs 23M→128K） | （磁盘操作，logs gitignore 内） |
| 设计 | 三线统一 design（log4j2→python 映射 / 注册表 / 合同库） | `5f3...` 见 git |
| **B** | 企业日志：app.log(INFO+)/error.log(WARN+) file appender + size 滚动 + gz 备份 | `68bdd8d` |
| **A** | validate 调度器 → 注册表（OCP），json_bridge 去 schema 名特判 | `8867f13` |

## B · 企业日志（已实现）

- `configure_logging` = console appender（始终）+ 可选 file appender。
- `logs/app/app.log`（INFO+ 全量）+ `logs/app/error.log`（WARN+，ThresholdFilter 等价）。
- `RotatingFileHandler` size 滚动 + gz 压缩备份（自定义 rotator/namer）；文件始终 JSON。
- env 驱动：`LOG_TO_FILES`（默认关，测试不写盘）/ `LOG_MAX_BYTES`（50MB）/ `LOG_BACKUP_COUNT`（10）。
- serve（cli serve）/ app-server 托管进程默认开启文件落盘；env 可覆盖。
- 业务归档（results/sessions/…）按用户决定**留 logs/ 原位不动**——本轮只新增运行日志层。
- 时间滚动（TimedRotating）留作后续 toggle；本轮先 size+gz（log4j2 最常用策略）。

## A · validate 注册表（已实现）

- `SchemaProcessor{validate, enrich}` + `_SCHEMA_PROCESSORS` + `register_schema_processor` +
  `apply_schema_semantics`（单一入口，validate+enrich，未注册原样返回）。
- 内置 audit-result / init-rules 两 schema 在 contract.py 注册；新域从自己模块注册即可扩展。
- `json_bridge` 两处 `if schema==DEFAULT: enrich` 特判 → `apply_schema_semantics`，不再认识具体 schema。
- `validate_structured_output_semantics` 保留薄包装，test_core_pure 零改动。

## C · 合同审计存储态（设计就绪，待合同审计开工实现）

`data/contracts/<contract_id>/`（source / clauses.json / payment_nodes.json / meta.json）持久合同库，
与 ephemeral 的 submissions 分离；生命周期 intake→registered→extracted→referenced。
详见 design.md「C」。新增 `stores/contract_store.py` + `paths.CONTRACT_ROOT_DIR` + 结论 evidence_chain
回链 contract_id —— **本轮不实现**，待开工。

> 事实更正：`data/` 当前为空、0 追踪、gitignore，并无"已提交初始数据"。

## 遗留 / 后续

- C 合同库实现（随合同审计开工）。
- 日志按天滚动 toggle（如需）。
- `validate_structured_output_semantics` 薄包装可在确认无外部依赖后并入 apply_schema_semantics。
