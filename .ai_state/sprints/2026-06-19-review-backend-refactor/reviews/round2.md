## VERDICT (evaluator, sprint-round2)

**判定**: CONCERNS

### 评分依据 (4 维)

| 维度 | 得分 | 说明 |
|---|---|---|
| Functionality | 4.3 | A1-A4 主结构债全断；OCP 注册表已有测试守卫；验收标准 4 条通过；216 tests passed |
| Spec Compliance | 4.0 | MISSING=0；D1 偏调有双记录且理由成立；F1/F3/F4 三处上向依赖与 design.md 验收标准 2 的守卫意图相悖但守卫未覆盖 routes→ops/core |
| Craft | 3.4 | F5 validate+cleanse 双职混合 (43 行>P0 40)；F7 _env_int DRY 违反 P0；F6 configure_logging 41 行微超 P0；F8 包内循环运行期依赖缓存 |
| Robustness | 3.8 | 守卫网有三处盲区 (F1 routes→ops、F3 ops→core、F4 routes→core)；F2 实 4 条守卫非 5 条；ops/stores 层零守卫 |

总评: 3.9 / 5.0

### 触发判定的关键 findings

- F5 (P1, 触 P0 SRP): output_contracts._validate_audit_result 43 行 + validate/cleanse 双职 → 超 40 行 P0 阈值；裁量为 CONCERNS 必修项（见裁量说明）
- F7 (P1, 触 P0 DRY): _env_int 在 logging_setup.py:156 与 config.py:246 重复定义 → 严格 P0 DRY 违反；提取至 platform/config.py 后各处 import
- F6 (P1, 触 P0 SRP): configure_logging 41 行，超阈值 1 行 → 裁量为 CONCERNS 可接受，polish 顺手拆 _install_file_handlers 子函数
- F1 (P1): routes/health.py:12 反向 import server.ops.diagnostics — routes 层吃 ops 层；test_routes_do_not_import_app_module 仅拦 server.api，对此完全盲
- F3 (P1): ops/diagnostics.py:9 from server.core import ... — ops 层经门面间接依赖 core；应直连 common.contract；守卫未覆盖 ops→core
- F4 (P1): routes/audit.py:17 from server.core import enrich_audit_decision — routes 层经门面绕到 audit 域；守卫未覆盖 routes→core

P1 共 6 条 (F1/F3/F4 分层盲区 + F5/F6/F7 P0 规则触发)，≥3 P1 → CONCERNS；无未修 P0 实质性违反（F5/F7 裁量见下）

### F5/F6/F7 P0 阈值裁量

**裁量结论：归 CONCERNS 必修项，不触发 REWORK。**

理由：
- F7 (_env_int DRY) 是真实 P0 违反，应修，但两处均为 6 行纯工具函数，无逻辑分歧风险，修复成本极低（提取一次 import 即可）；不构成整体架构不可信的 REWORK 条件。
- F5 (_validate_audit_result 43 行) 超出 3 行，注释已说明 risk_dimensions 清洗意图，逻辑不是真正双职（validate 失败 → raise；cleanse 是 validate 通过后的原地净化，作者注释也已解释）；但应在进 Phase 1 前拆出 _cleanse_risk_dimensions 以符合规范。
- F6 (configure_logging 41 行) 超出 1 行，有完整 docstring，handler 安装逻辑内聚，polish 阶段顺手提取 _install_file_handlers 即可；不阻塞分层正确性。

若 F7 (DRY P0) 进 Phase 1 前不修则升为 REWORK。

### 守卫网洞——架构定调

**F1+F3+F4+F2 共同指向：分层守卫网有结构性盲区，这是本轮最重要的架构债。**

- 现有 4 条守卫只覆盖：routes→api（F1 盲）、platform→上层、common→feature/上层、audit↔ocr 互不 import。
- 完全未守卫：routes→ops、routes→core、ops→core、ops→stores（ops 可否向下 import stores 本身就应明确）。
- **进 Phase 1 前须补守卫**：至少补 test_routes_do_not_import_ops_or_core 与 test_ops_do_not_import_app_or_routes，使 F1/F3/F4 三处现存违规能被自动检出（先补守卫让测试变红，再修违规让测试变绿——TDD 精神）。

### 行动建议

**进 Phase 1 前必须修（门禁项）**
- F7: 提取 _env_int 到 platform/config.py 或新建 platform/_utils.py，两处改为 import，消除 DRY P0 违反
- F5: 从 _validate_audit_result 拆出 _cleanse_risk_dimensions(structured_output) 子函数，使 _validate_audit_result 职责单一（只 raise，不 mutate）
- F1+F3+F4 守卫补全 + 违规修复：在 test_layering.py 新增 test_routes_do_not_import_ops_or_core 和 test_ops_do_not_import_app_or_routes；修复 F1 (routes/health.py 改走 ops 合法路径或 routes/deps 转发)、F3 (ops/diagnostics.py:9 改为直连 common.contract)、F4 (routes/audit.py:17 改为直连 common.output_contracts 或 audit.contract)

**polish 顺手处理**
- F6: configure_logging 拆出 _install_file_handlers 子函数，主体压到 ≤40 行
- F8: common/contract.py:173 底部循环 import 补注释说明原因，或在 __init__.py 侧解耦
- F2: test_layering.py docstring 措辞修正（实 4 条守卫，补全 ops/stores 守卫计划注释）
- D3: ops/diagnostics → core facade 偏调补记录到 ship.md

**推迟**
- D2: 守卫数量措辞不精确（P2）——修完守卫后数字自动正确
- F9: valid_dim_names magic set 提取为模块常量（P2，功能无影响）

### Sisyphus 完整性检查
- [x] A1-A4 Task 全完成（ship.md 有 commit 对照）
- [x] 验收标准 4 条已通过（216 tests passed, ruff 绿）
- [ ] F7 (DRY P0) 门禁修复未执行
- [ ] F5 (SRP 拆职) 门禁修复未执行
- [ ] F1/F3/F4 守卫补全 + 违规修复未执行
- [ ] 上述 3 项完成后需重跑全量 pytest 确认守卫绿灯
- [x] Refactor 路径，进 Phase 1 后须触发 polish（cleanup-pass.md + architecture/ 更新）
