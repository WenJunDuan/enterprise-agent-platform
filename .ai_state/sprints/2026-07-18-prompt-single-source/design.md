# Design (DRAFT · 待 E2 拍板) · D3 prompt 单源 + D10 直连可靠性包

> **状态: DRAFT。前置=用户 E2 拍板**(a=command 单源 / b=Python 单源+直连, 主 agent 推荐 b,
> 数据论证见 route-note.md「E2 拍板包」)。本稿按 **方向 b** 展开; 若拍 a 本稿作废重写(B2 形态)。
> 拍板后流程: 本稿定稿 → critic → impl(黄区, generator/codex 分派)。

## 背景(WHY)

三域三套 prompt 投递机制的双源漂移已实测兑换成生产可靠性差(D3 spike: 内联 4/6 契约失败 vs
command 侧 1/7); prompt-闸矛盾已单独修复 ship(60d860c)。E1 直连 spike 证明: anthropic SDK 直打
网关比 claude-agent-sdk CLI 子进程**快 40-60%**(中位 19s vs ~31s), 质量零损失, 且享网关 prompt
cache 红利、消除 CLI 独有故障类(流式解析崩溃/buffer 上限)。全部证据: 本目录 spike/*.jsonl。

## 方案(方向 b): Python 单源 + 直连 flag 门控

### T1 · D3 收口: .claude expense 资产标注非生产真相源

- `.claude/commands/audit.md` 改**薄壳**: 顶部显式声明「生产 prompt 唯一真相源 =
  `server/audit/runner.py:AUDIT_INSTRUCTIONS`; 本文件仅供 CC 对话调试, 判断纪律以 Python 源为准」;
  删除与 AUDIT_INSTRUCTIONS 重复的判断细则(保留输入解析/路由说明), 不再维护双份纪律文本。
- `.claude/CLAUDE.md` expense 段核对: 只留路由表+红线(现状已较薄, 增量小)。
- 默认关闭 agent(expense-extractor/auditor/reviewer)纪律文本抽 shared reference(D3 原范围,
  可降级为 follow-up)。
- **验收**: rg 证明判断纪律无双源实质重复; audit 生产行为零变化(golden manifest 3 连跑全过,
  字节级 domain_profile 快照不变)。

### T2 · D10①: 直连路径落地(flag 门控)

- 新增 `server/audit/direct.py`: `run_direct_audit(prompt, request_id, ...)` — anthropic
  `AsyncAnthropic` 一次网关往返; client 构造用 `configure_claude_runtime_env()` 解析
  base_url/auth_token + **`trust_env=False` 显式关代理继承**(SOCKS 坑, 见 compound codex-proxy
  trick 2026-07-18 增补); 复用生产同款抽取与契约链(`_extract_json_object` 提升公开名或经 core
  导出 + `apply_schema_semantics`); 复用 `settings.contract_max_retry` 重试环。
- `runner.py` 接线: `AUDIT_DIRECT_CONNECT` env flag(默认 **0**); off 路径与现状**逐字节不变**
  (对齐 D8 TENDER_SLIM_CONTEXT 门控先例); on 时走直连, 异常回落 CLI 路径(保底)。
- 依赖: `anthropic` 进 pyproject 锁版本(uv.lock)。
- **验收**: flag off 现有 test_audit* 全过未改; flag on 单测(mock transport)+真网关 golden 3 连跑;
  时延对比记录进 eval 报告。

### T3 · D10③: 耗时分解指标

- direct 路径把 wall/input_tokens/output_tokens/(cache_read 如网关返回)写进 AgentRunMeta 或
  eval 报告(对齐 D1 retry/latency 先例); CLI 路径保持现状。

### T4 · D10②: 多模态附件预嵌(POC 先行)

- 直连形态下附件(发票图/PDF)按 anthropic 协议 image/document block 预嵌 messages;
  **前置 POC**: 确认 deepseek 网关对 vision block 的支持面, 不支持则该项降级 backlog。

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

## 验收标准(定稿时细化为 checklist)

1. flag off: 861 基线全绿, domain_profile 字节快照不变, golden 3 连跑全过。
2. flag on: golden 3 连跑全过 + 中位时延 ≤ CLI 路径 70%(以 E1 数据为基准)。
3. 判断纪律单源: rg 双源重复=0; audit.md 薄壳声明在位。
4. ruff 净; anthropic 版本锁定。

## 方向 a 差异注记(若拍 a)

统一到 command B2 形态: AUDIT_INSTRUCTIONS 迁 audit.md, runner 走 run_command_json+context 注入,
直连不做。本稿 T2-T5 作废, T1 反向(Python 侧标注非真相源)。数据上不推荐(+35% 成本, 无时延收益)。
