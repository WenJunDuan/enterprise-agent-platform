# Round 3 Review — 安全与健壮性

> Reviewer findings (F1-F9) + spec-compliance findings (M1-M3) 汇总。
> 本文件由 evaluator subagent 生成于 2026-06-19。

## VERDICT (evaluator, sprint-round3)

**判定**: CONCERNS

### P0 裁量核心——F2/F3 到底是 P0 还是 P1？

security-checklist 原文（适用规则）：
- "❌ 把 stack trace / SQL 错误 / 内部路径直接返回给客户端" → P1
- "❌ 在 console.log / print / 日志中输出密钥" → P0 (密钥/凭证类)

**F2 裁量**：audit_worker.py:158 error_detail = str(exc) 写入 audit_tasks 并经 API 返回。
- 核心威胁是"含 key 片段的网关响应被 str(exc) 捕获并回流到租户"。
- 当前 litellm 实际返回格式需实测才能确认是否包含 key，非必然路径。
- security-checklist 把"raw 错误返回客户端"明确列为 P1，reviewer 升级理由（"潜在 key 片段"）属推测性风险，非已证实路径。
- **裁定：P1**（信息泄露，非 P0 密钥硬编码/直接日志输出）。但必须修——属门禁项，因 P1 累计已触发 CONCERNS。

**F3 裁量**：api.py:312 SPA fallback raise HTTPException(500, detail=f"index.html not found at {index_html}")。
- 绝对路径泄露，典型 P1 信息泄露（security-checklist: "❌ 把...内部路径直接返回给客户端" = P1）。
- **裁定：P1**（与 F2 同类信息泄露）。

**F1 裁量**：真实 API key 在 git 历史 commit 7122b31。
- 密钥已入 git 历史，属 P0 安全事件。
- 但这是纯运维动作（轮换密钥 + BFG 清历史），代码侧无可修内容（gitignore 已到位，.example 已提供）。
- pending-actions.md 已记录。不计入代码评审 P0 计数，归入运维待办。
- **结论：F1 不触发 REWORK**——代码侧已尽（gitignore + .example），剩余为用户/运维手动动作。

**无 P0 代码违规 → 不触发 REWORK。**
P1 共 6 条（F2/F3/F4/F5/F6/M1）→ ≥3 P1 → 触发 CONCERNS。

### 评分依据 (4 维)

| 维度 | 得分 | 说明 |
|---|---|---|
| Functionality | 4.0 | 主流程无命令注入/SQL注入/路径穿越；WAL+BEGIN IMMEDIATE已到位；核心安全机制正确 |
| Spec Compliance | 3.5 | M1 并发测试缺失（design §八明确要求）；F2/F3 违反 security-checklist P1；M2/M3 属 P2 |
| Craft | 3.6 | F4 可预测默认 token 设计缺陷；F7 migrate.py SQL 拼接无运行期断言；F5 日志框架无脱敏防护 |
| Robustness | 3.4 | F2 exc→租户回流路径存在；F6 信号量 shutdown 无显式 cancel；M1 WAL 并发测试零覆盖 |

总评: 3.6 / 5.0

### 触发判定的关键 findings

- F2 (P1): audit_worker.py:158 str(exc) 原样回流租户，含潜在 key 片段风险 → 脱敏为通用错误消息 → 贡献 CONCERNS
- F3 (P1): api.py:312 SPA fallback 泄露服务器绝对路径 → 改为通用 404 → 贡献 CONCERNS
- F4 (P1): config.py:21 硬编码可预测默认 token sk-default，ALLOW_INSECURE_DEFAULT_TENANT_KEY=1 可绕过认证 → 贡献 CONCERNS
- F5 (P1): logging_setup.py:234-266 日志框架无脱敏黑名单，框架层零防护 = 回归风险 → 贡献 CONCERNS
- F6 (P1): audit_worker.py:27-28 shutdown 无显式 cancel，running 任务靠时间轮询 → 贡献 CONCERNS
- M1 (P1): design §八明确"补并发测试"，test_audit_task_store.py 零并发用例，WAL 实现无测试守卫 → 贡献 CONCERNS

P1 共 6 条 ≥3 → CONCERNS；F1 归运维待办，代码侧无 P0 → 不触发 REWORK。

### 行动建议

**门禁项（进 Phase 1 前必须修，代码侧）**
- F2: audit_worker.py:158 替换 str(exc) 为脱敏消息 "internal error" 或 "task execution failed"，详情只写服务端日志（logger.exception(exc)）
- F3: api.py:312 SPA fallback 改为 raise HTTPException(404, detail="UI not available")，去掉路径插值
- F4: config.py 默认 token 改为 None（或要求 TENANT_KEYS 非空），ALLOW_INSECURE_DEFAULT_TENANT_KEY=1 写启动 WARNING，不允许空密钥直接认证通过
- M1: test_audit_task_store.py 补 ≥1 个并发写测试（asyncio.gather 或 threading），验证 WAL+BEGIN IMMEDIATE 防锁行为

**运维侧手动（不阻塞代码合并，但必须在 Phase 1 上线前完成）**
- F1: 在 Qwen 后端轮换 sk-hATxkq_* 密钥；视情况执行 BFG 清历史（pending-actions.md 已记录）

**polish 阶段处理**
- F5: logging_setup.py 加脱敏黑名单（api_key, token, secret, password），_extra_fields 过滤后落盘
- F7: migrate.py SQL 拼接加运行期白名单断言（assert table in ALLOWED_TABLES）
- F6: audit_worker.py shutdown handler 显式 task.cancel() 后 gather(tasks, return_exceptions=True)
- M2: 补 LOG_MAX_BYTES/LOG_BACKUP_COUNT env 覆盖路径测试
- F8 (P2): CORS * 与 regex 加格式校验

**推迟**
- M3: VACUUM 入口属运维 DBA 功能，v2 可加
- F9 (INFO): warning 去重非幂等，无实际 bug

### Phase 0 收口建议——"修复 sprint" 必要性评估

R1 + R2 + R3 三轮门禁项汇总：

| 来源 | 门禁项 | 性质 |
|---|---|---|
| R1-F1 | _load_memory_files 无异常隔离 | 健壮性 |
| R1-F2 | _copy_table 静默丢行无计数 | 可观测性 |
| R2-F7 | _env_int DRY P0 违反 | 代码规范 |
| R2-F5 | _validate_audit_result SRP 拆职 | 代码规范 |
| R2-F1+F3+F4 | 守卫补全 + 三处分层违规修复 | 架构 |
| R3-F2 | str(exc) 回流租户脱敏 | 安全 |
| R3-F3 | SPA fallback 路径泄露 | 安全 |
| R3-F4 | 默认 token 硬编码可预测 | 安全 |
| R3-M1 | 并发写测试补全 | 测试覆盖 |

**结论：应合并为单一「Phase 0 修复 sprint」。**

理由：
1. 三轮无 REWORK/FAIL，但 CONCERNS 累积共 16+ P1——单独进 Phase 1 前逐项修复比分散合并更可控。
2. 修复项相对独立（无大架构改动），黄区单 subagent 可完成，预计 1 次 sprint 全清。
3. 全量 pytest 须在修复后统一补跑（R2 守卫绿灯 + R3 并发测试 + 全量通过）才能关闭 Phase 0。
4. 运维项 F1（密钥轮换）独立于代码，可并行，不阻塞修复 sprint 结束。

修复 sprint 完成判定条件：上述 9 项门禁全绿 + uv run pytest -q 全量通过 + ruff 零警告 → Phase 0 completed → 进 Phase 1 item1。

### Sisyphus 完整性检查
- [x] R3 reviewer findings 已分析（F1-F9 全覆盖）
- [x] R3 spec-compliance findings 已分析（M1-M3 + DEVIATED/EXTRA）
- [x] F2/F3 P0/P1 裁量已给出明确结论（均裁为 P1）
- [x] F1 归属已裁量（运维项，不触发 REWORK，pending-actions.md 已有记录）
- [ ] R3 门禁修复（F2/F3/F4/M1）尚未执行——待修复 sprint
- [ ] R1/R2/R3 合并修复 sprint 尚未启动
- [ ] 全量 pytest 须在修复后统一通过
- [ ] 修复后须更新 architecture/（Refactor 路径铁律[Polish强制]要求）
