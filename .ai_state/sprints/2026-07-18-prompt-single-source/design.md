# Design · D3 prompt 单源 + D10 直连可靠性包

> **状态: 定稿(2026-07-18 用户 E2 拍板=方向 b**,「好的 开始做下个 Sprint」确认主 agent 推荐;
> 数据论证见 route-note.md「E2 拍板包」)。流程: critic → impl(黄区 generator+worktree, path=System 强制)。

## 背景(WHY)

三域三套 prompt 投递机制的双源漂移已实测兑换成生产可靠性差(D3 spike: 内联 4/6 契约失败 vs
command 侧 1/7); prompt-闸矛盾已单独修复 ship(60d860c)。E1 直连 spike 证明: anthropic SDK 直打
网关比 claude-agent-sdk CLI 子进程**快 40-60%**(中位 19s vs ~31s), 质量零损失, 且享网关 prompt
cache 红利、消除 CLI 独有故障类(流式解析崩溃/buffer 上限)。全部证据: 本目录 spike/*.jsonl。

## 方案(方向 b): Python 单源 + 直连 flag 门控

### T1 · D3 收口: .claude expense 资产改薄壳, 判断纪律单源化

- `.claude/commands/audit.md` 改**薄壳**(critic F5 修订): 定性=「CC 对话渠道的执行入口; 判断纪律
  唯一真相源 = `server/audit/runner.py:AUDIT_INSTRUCTIONS`」——**不写「仅供调试」**(项目 CLAUDE.md
  路由表仍以 /audit 为 CC 渠道报销默认入口); 薄壳稿**首步强制指令: 判断前必须 Read
  server/audit/runner.py 取 AUDIT_INSTRUCTIONS 全文作为判断纪律**(不靠模型自觉——B1 自行取证
  1/3 verdict 漂移的教训); 删除与 AUDIT_INSTRUCTIONS 重复的判断细则(保留输入解析/输出契约说明)。
- `.claude/CLAUDE.md` expense 段核对: 只留路由表+红线(现状已较薄, 增量小)。
- 默认关闭 agent(expense-extractor/auditor/reviewer)纪律文本抽 shared reference(D3 原范围,
  可降级为 follow-up)。
- **验收**: rg 证明判断纪律无双源实质重复; audit 生产行为零变化(golden manifest 3 连跑全过,
  字节级 domain_profile 快照不变)。

### T2 · D10①: 直连路径落地(flag 门控)

- 新增 `server/audit/direct.py`: `run_direct_audit(...)` — anthropic `AsyncAnthropic` 一次网关
  往返; client 构造用 `configure_claude_runtime_env()` 解析 base_url/auth_token +
  **`trust_env=False` 显式关代理继承**(SOCKS 坑, compound codex-proxy trick 2026-07-18 增补);
  抽取复用 `from server.core import _extract_json_object`(**复刻 ocr/runner.py:23 既有门面导入
  约定, 不改名不动 core/contract**, critic F4)+ `apply_schema_semantics`; 契约类失败复用
  `settings.contract_max_retry` 重试。
- **归档接缝(critic F1, P0)**: flag-on 分支拿到过闸结果后显式调用 `archive_result_payload` 写
  `results` 表并构造等价 `AgentRunMeta`(claude_session_id=None; log_file=直连专属日志路径或留空
  并注释理由)——GET 结果端点(routes/audit.py:190→result_store:182)只读 results 表, 缺这步 =
  completed 但结论 404。
- **回落语义(critic F2, P0)**: 按异常类型分流——**传输类**(连接/鉴权/网关 5xx/超时, 秒级失败)→
  **单次**回落现有 CLI 路径(含其自身重试), 复合最坏 ≈ 2×~5s + 2×55s ≈ 120s < AUDIT_TIMEOUT_SEC
  180s; **契约类**(重试耗尽仍不合规——模型输出问题, 换路径大概率同败)→ 直接失败上报**不回落**
  (禁静默降级); 最坏 2×25s ≈ 50s。预算计入风险表。
- `runner.py` 接线: `AUDIT_DIRECT_CONNECT` env flag(默认 **0**); off 路径验证 = **wiring 断言**
  (monkeypatch direct 入口 fail-if-called + flag off 全量 test_audit* 与 golden 全绿, 对齐 D8
  tests/test_tender_context_slim_wiring.py:51-77 写法, critic F3——不承诺无法验证的「逐字节」)。
- 依赖: `anthropic` 进 pyproject 锁版本(uv.lock); 部署机离线安装可达性列入 T5 runbook 核对项。
- **验收**: flag off wiring 断言+全量绿; flag on 单测(mock transport)**含 results 表落地 + GET
  结果端点读回断言**; 真网关 golden 3 连跑; 时延对比进 eval 报告。

### T3 · D10③: 耗时分解指标

- direct 路径把 wall/input_tokens/output_tokens/(cache_read 如网关返回)写进 AgentRunMeta 或
  eval 报告(对齐 D1 retry/latency 先例); CLI 路径保持现状。

### T4 · D10②: 多模态附件预嵌 POC(带终止条件, critic F6)

- 交付=POC 脚本(sprint spike/ 目录, 评测工装): 对 1 张含文字测试图发 anthropic 协议 image block
  请求。**终止条件**: 网关 200 且回答引用图内文字=支持(记档, 预嵌正式实施另立任务); 4xx/明确
  不支持=降级 backlog——**两种结果均算 T4 完成**。真网关执行由主 agent 验收时跑。

### T5 · D10④: 休眠资产重启 runbook(文档项, 随 T2 收口)

## 影响范围

`server/audit/{runner.py, direct.py(新)}` / `server/common/contract.py`(仅公开名导出) /
`.claude/commands/audit.md` / `.claude/CLAUDE.md` / pyproject+uv.lock / tests(新增 direct 单测)。
tender/ocr 域零改动; 闸零改动。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 直连丢工具面(Read 附件) | flag 默认关; T4 附件预嵌补齐前, 需读附件的案件走 CLI 路径 |
| 部署机代理/网络形态未知 | trust_env=False + runbook 核对项; 上线前部署机跑 golden |
| 网关 prompt cache 计费语义未确认 | T3 指标落地后部署机观测 input_tokens 口径 |
| 流式进度(on_progress)缺失 | 直连初版不接进度流(audit 单步短任务); 需要时用 SDK streaming 二期 |

## 验收标准(checklist 权威版, Round1 修订后)

1. flag off: 861 基线全绿 + domain_profile 字节快照不变 + direct 入口 wiring 断言(未触达) +
   golden 3 连跑全过。
2. flag on: mock 单测全绿(**含 results 表落地 + GET 结果端点读回断言**, critic F1); 真网关
   taxi+placeholder 各 3 轮与 flag off 同窗交错对照, **跨 case 合并中位 on ≤ off×70%**(critic F7
   口径; 单样本超同 case 中位 2 倍视为网关抖动, 允许整场重跑一次)。
3. 判断纪律单源: rg 双源实质重复=0; audit.md 薄壳定性+首步强制 Read 指令在位; **CC 对话路径核验**:
   主 agent 以 /audit 跑 case-taxi 1 次, verdict/policy_refs 与 Python 路径一致(critic F5)。
4. ruff 净; anthropic 版本锁定; 回落语义单测覆盖「传输类回落一次」+「契约类不回落」两分支(critic F2)。

## Round 1 · Critic Findings 与修订应答(2026-07-18, critic subagent, VERDICT=NEEDS_REVISION→已全部应答)

| # | 级 | Finding(摘要) | 应答(已并入正文) |
|---|---|---|---|
| F1 | P0 | 直连绕开 json_bridge 丢 results 表归档→GET 结论 404(json_bridge.py:284-301 归档链/audit.py:190 只读 results 表) | T2 增「归档接缝」段: flag-on 显式 archive_result_payload+等价 AgentRunMeta; 验收 2 加表落地+端点读回断言 |
| F2 | P0 | 回落 CLI 叠加双侧重试, 最坏 ~160s 逼近 AUDIT_TIMEOUT_SEC 180s, 与降延迟目标相悖 | T2 增「回落语义」段: 传输类单次回落(预算 ~120s<180s)/契约类不回落直接失败(禁静默降级, ~50s); 验收 4 加两分支单测 |
| F3 | P1 | 「flag off 逐字节不变」不可验证(D8 先例实为 wiring 断言) | T2 措辞改实: monkeypatch fail-if-called wiring 断言+全量绿, 删「逐字节」 |
| F4 | P1 | 「_extract_json_object 提升公开名」过度设计(core.py `__all__` 已导出私有名, ocr/runner.py:23 既有消费约定) | 已删该分支: direct.py 复刻既有 `from server.core import _extract_json_object`, 不动 core/contract |
| F5 | P1 | audit.md「仅供调试」定性与 CLAUDE.md 路由表矛盾; 薄壳后 CC 对话路径判断质量零验证 | T1 定性改「CC 对话渠道执行入口」+首步强制 Read runner.py 取纪律全文; 验收 3 加 CC 路径核验(/audit 跑 case-taxi 比对) |
| F6 | P2 | T4 POC 无终止条件, Sisyphus 完整性悬置 | T4 加终止条件: 支持=记档/不支持=降 backlog, 两者均算完成 |
| F7 | P2 | 时延验收口径未定(E1 样本小、波动大) | 验收 2 定口径: taxi+placeholder 各 3 轮同窗交错、跨 case 合并中位、抖动允许整场重跑一次 |

critic 全文(代码引用与评分表)见会话记录; 关键证据路径: json_bridge.py 归档链 / routes/audit.py
结果端点 / core.py `__all__` 导出约定 / test_tender_context_slim_wiring.py 门控测试先例。
P0 全部闭合, 主 agent 判 ready 进 impl(改动面不再触碰共享 contract 机制, 单轮 critic 足够)。

## 方向 a 差异注记(若拍 a)

统一到 command B2 形态: AUDIT_INSTRUCTIONS 迁 audit.md, runner 走 run_command_json+context 注入,
直连不做。本稿 T2-T5 作废, T1 反向(Python 侧标注非真相源)。数据上不推荐(+35% 成本, 无时延收益)。
