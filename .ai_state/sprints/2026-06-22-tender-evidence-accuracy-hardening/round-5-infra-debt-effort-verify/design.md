# R5 · 基建债 + effort 透传 验证（reconciliation round）+ 招标人合规 MVP 决议

> Sprint `2026-06-22-...` · Round 5 · 路径 **验证/对账（无新功能代码）+ 1 个测试补缺**
> 行号 2026-06-22 实测 grep + SDK 源码核对。

## 一、grounding 核查结论（逐项实测，重要）

R5 原计划三类，**逐项核对后发现基建债/effort 均已在前序工作完成**：

| 项 | goal 标注 | 实测结论 | 证据 |
|---|---|---|---|
| **F2 目录越权** | ❌未做 | ✅**已修** | `upload_helpers.py:46 _safe_segment` + `validate_directory_case_path:87` confine 到 `data/submissions/<tenant>/` 子树（round4 F2 注释 + resolve 校验）|
| **F4 同步 SQLite 阻塞事件循环** | ❌未做 | ✅**已修** | `tender_worker.py` / `audit_worker.py` 所有 SQLite 读写经 `asyncio.to_thread`（round4 F4 注释，多处）|
| **F5 超时不杀子进程** | ❌未做 | ✅**SDK 已处理** | SDK `_internal/client.py:73-87` process_query try/finally **显式 aclose 内层生成器** → 触发 `query.close()` → `subprocess_cli.py:571-590` disconnect 优雅关→`terminate()`→`kill()`；另 `:33` atexit SIGTERM 兜底。`asyncio.wait_for` 取消 → 生成器链关闭 → 子进程被终止 |
| **effort 各端点透传** | 🟡待验 | ✅**已实现+已测** | `agent_bridge.py:99-107` effort（env `CLAUDE_REASONING_EFFORT` + per-call）校验白名单 `_VALID_EFFORTS`；`tender_worker` 传 `effort=_TENDER_EFFORT(xhigh)`；`test_agent_bridge_options.py:38-58` 四例覆盖。R2 dogfood qwen/deepseek 实跑（扩展思考生效，耗时含 thinking）|

**真实测试缺口**：worker **超时→graceful failed** 路径无回归测试（F5 用户侧 UX：超时不崩、置 status=failed + error_detail）。本轮补此测试，锁定行为。

## 二、招标人侧合规 MVP（⑥）—— 决议：**本轮不做，移交 v2**

理由（诚实，非偷懒）：
1. **CLAUDE.md 已明确 v1 范围**：「v1 仅做评分评审；资格审查 / 一票否决 / 串标围标识别等**程序合规留作 v2**」。招标人侧排他性/可量化/废标清单/时限审查属程序合规 = v2。
2. **本 Sprint 主题是"证据可验证性 + 报价规模 + 准确度 durable 硬化"**（R1-R4 主线）；招标人侧合规是**新业务能力扩展**（评的是招标文件本身、非投标评分），非"硬化"。
3. **缺前置素材**：goal 自述需先 `/init-rules <法规源> tender` 补 `tender_regulation` + 时限规则到 `knowledge/tender`——**无法规源文件**则无法生成规则（不得现场编造规则，铁律）。
4. 规模大（新规则层 + 新分析路径 + 新契约），单轮自动完成且无确认 = 过度扩张风险。

→ 记入 backlog（v2），需用户提供法规源 + 确认范围后另开 Sprint。

## 三、本轮实做：worker 超时 graceful-fail 回归测试
- `tests/test_tender_worker_timeout.py`（或并入既有）：mock `_run_evaluation` 挂起 + 极短 `TENDER_TIMEOUT_SEC` → `_execute_inner` 捕获 `asyncio.TimeoutError` → upsert status=failed + error_detail 含"超时" + progress="评标超时"，不抛、不崩。
- 锁定 F5 用户侧 graceful 行为（SDK 杀子进程 + worker 置 failed）。

## 四、影响范围
| 文件 | 改动 |
|---|---|
| `tests/test_tender_worker_timeout.py` | **新建**：超时→failed 回归 |
（无 server/ 代码改动——F2/F4/F5/effort 均已实现）

## 五、验收
1. 新测试绿：超时 → status=failed + error_detail + 不抛。
2. 回归 `pytest -q` 全绿 + ruff。
3. F2/F4/F5/effort 证据记录在案（§一表）。

## 六、设计审查记录
验证/对账为主 + 1 测试补缺，低风险；跨轮最终自查统一覆盖。

## 七、自测结果（2026-06-22）
- 新测 `tests/test_tender_worker_timeout.py` 2 例：超时→failed+error_detail(含"超时")+progress="评标超时"；通用异常→failed+error_detail。全绿。
- 回归 `pytest -q` **679 全绿** + ruff clean。
- F2/F4/F5/effort 已实现/SDK 已处理/已测（§一表，代码+SDK 源码核对）。

## 八、进度回写（2026-06-22）
- **结论**：R5 基建债（F2 目录越权 / F4 同步 SQLite 阻塞 / F5 超时杀子进程）+ effort 透传 **均已在前序工作完成**（逐项代码核对 §一）；本轮补 worker 超时 graceful-fail 回归测试锁定行为。
- **招标人侧合规 MVP 移交 v2**（§二）：CLAUDE.md 已定 v1 不含程序合规；本 Sprint 主题是证据/报价/准确度硬化非新业务；缺法规源（不得编造规则）；规模大需确认。记 backlog。
- **Followup（v2）**：招标人合规需用户提供法规源 + 确认范围后另开 Sprint。
