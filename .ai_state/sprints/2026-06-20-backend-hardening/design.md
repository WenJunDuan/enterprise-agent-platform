# Backend Hardening Design — 两轮审查共同开着的债

> Sprint 2026-06-20 · Path: System · 源自 round4(2026-06-19) + round5(2026-06-20) 两轮审查**一致认定**、且 agent-capability-redesign sprint 未触达的项。落档先于实现。

## 背景
round4 全栈审查列 F1–F12；agent-capability-redesign sprint 关掉了 F1(幻觉闸,有测试)、删了 F8(死域)。round5 复审确认：其余**四类基础设施/正确性债"一条没动"**。本 sprint 收口这四类，按 `成本 × 价值 × 风险` 排序——先摘低垂果实，重活靠后。

非目标：不重开全量二审；不引入向量库；**不改模型 / LiteLLM 层**（anyrouter/网关路由另案，见会话记录）。

## 现状（已对真实代码核验 2026-06-20，非仅引用 review）
- 真伪闸 `RULE_REF_CHECK` 默认 **OFF**（`output_contracts.py:38-41`）；ON 时已有空集优雅跳过(`if known:` `:212`)。
- F3 statute 两文件 `category`/`rule_id` 与 `statute-*` 文件名不符（`asset_validation.py:57-68` vs `statute-evalmethod.rules.json` category=`evalmethod`/rule_id=`tender_evalmethod_001`）→ validate-assets **degraded**。
- F2 directory 模式仅校验 `relative_to(data/)`，无租户（`upload_helpers.py:32-46`）；upload 模式安全(写 `SUBMISSION_ROOT/request_id`，且 multipart 强制 mode=upload `audit.py:101`)。破在 JSON `mode=directory` 一个口子。
- F4 worker 内 4 处 `upsert_audit_task` 同步跑在事件循环（`audit_worker.py:66/93/121/147`），无 `to_thread`。
- F5 裸 `create_task`(`audit_worker.py:174`) 不留引用；准入无上限(任务堆在 accepted)；超时只 cancel 协程、不杀 claude CLI 子进程。
- F6 retry/delete 读-判-写非原子（`audit.py:194-221` / `:238-244`）；并发 retry 双执行/双成本。

## 方案与优先级（H1→H4）

### H1 · 真伪闸默认开 + F3 statute 自检 —— 最低成本最高杠杆，先做
- **真伪闸**：`RULE_REF_CHECK` 默认 **ON**（空集已优雅跳过；CI 无 gitignored knowledge/ 自动不误挂）。本地全量回归，审清任何用假 `policy_refs` 的 fixture（改真 rule_id 或该用例显式 `RULE_REF_CHECK=0`）。
- **F3**：把两 statute 文件 `category`/`rule_id` 对齐 `statute-*` 文件名（`category→statute-evalmethod`/`statute-regulation`，rule_id 前缀→`tender_statute-evalmethod_`/`tender_statute-regulation_`），使 validate-assets 转 ok；清 round5 L4 死引用。**注：statute 文件在 gitignored `knowledge/`，属部署侧编辑**（git 不可追溯，验收以 validate-assets 转 ok 为准）。
- 备选(不取)：改 `asset_validation` 放宽校验——改验证器影响全域，且会掩盖项目层(`r2024007.rules.json`)的命名约束。

### H2 · F6 retry/delete 原子化 —— 正确性 bug，contained
- `audit_task_store` 加原子状态转移 `try_transition(request_id, tenant, to_status, allowed_from)`（`UPDATE ... SET status=? WHERE request_id=? AND tenant=? AND status IN (...)`，按 rowcount 判成功），retry/delete 用它替"读→判→写"。
- 验收：并发两 retry 仅一个 schedule；delete 与 running 竞态被守住（新增并发测试）。

### H3 · F4 to_thread + F5 任务生命周期 —— 异步正确性，重活靠后
- F4：4 处 `upsert_audit_task` 包 `await asyncio.to_thread(...)`。
- F5：① 保留 task 引用集 + `add_done_callback` 丢弃；② 准入上限(pending 超额 → 503 拒)；③ 超时 path 确保 kill claude CLI 子进程(需 runner 暴露取消/kill 语义)。
- 验收：孤儿任务不被 GC；超额准入被拒；超时后无残留子进程。

### H4 · F2 租户隔离 —— 数据边界，**需用户决策**（见 checklist `user_decision`）
- fork (a) 对外仅留 upload 模式(directory 不暴露外部 API) / (b) 每租户限定 `data/submissions/<tenant>/` 子树并校验归属。
- 且需确认 demo/内网单组织阶段是否本 sprint 做（round4 评：单组织 HIGH / 多租户 BLOCKER）。**未定前不动 F2 代码。**

## 影响范围
`server/common/output_contracts.py`、`knowledge/tender/statute-*`(部署侧)、`server/stores/audit_task_store.py`、`server/routes/audit.py`、`server/routes/audit_worker.py`、`server/routes/upload_helpers.py` + 对应 `tests/`。

## 风险与缓解
- **真伪闸默认开**→prod 依赖 knowledge/ 规则集完整：空集跳过兜底；规则缺失只会"放过"不会误杀，但"已注入却不在 knowledge 的 rule"会被误判 → H1 验收须确认 `注入规则集 == knowledge 规则集`。
- **F5 杀子进程**依赖 runner 取消语义，最不确定 → 排最后；做不动则降级为"记录孤儿 + 告警"。
- **F2** 面向外部契约，先定 a/b 再动。

## 验收标准
每项 TDD(先测后改)；全量 `uv run pytest -q` 绿 + `uv run ruff check .` 零警告；`validate-assets` 对 tender 域转 ok；并发 retry/delete 测试通过。基线：本 sprint 起点 287 passed / ruff clean。

## 关联
- 依据：[`../2026-06-19-review-backend-refactor/reviews/round4-fullstack-review.md`](../2026-06-19-review-backend-refactor/reviews/round4-fullstack-review.md)(F2/F3/F4/F5/F6) + [`round5-post-sprint-review.md`](../2026-06-19-review-backend-refactor/reviews/round5-post-sprint-review.md)(F1-a 真伪闸默认关 / L3 statute)
