---
date: 2026-08-14
type: learning
slug: prompt-budget-must-be-per-session
sprint: 2026-08-12-prompt-architecture
---

# 提示词预算必须按「单会话累计注入 vs 最小窗口模型」算，不是按单文件字节

## 事故

prompt-architecture 重构（2026-08-13 SHIP）上生产后，内网 DeepSeek Flash 跑评标**四次全部无结论**：
分析十几分钟后 `JSONContractError: Prompt is too long`，三次重试在 700ms 内确定性打完。
回滚 `tender-evaluate.md` 至重构前单文件形态后恢复。

## 真因（实测数字）

| 进入上下文的部分 | 改之前 | 改之后 |
|---|---|---|
| CLAUDE.md（每次调用进系统提示） | 8,323 B | 8,412 B |
| tender-evaluate.md 命令正文 | 38,754 B | 12,442 B |
| 强制 Read 的 references | 1 个 · 1,629 B | 6 个 · 34,585 B |
| **单次评标脚手架合计** | **48,706 B** | **55,439 B（+13.8%）** |

**文件瘦身 68% 与上下文增长 13.8% 同时成立** —— 26KB 没有消失，只是搬到 references 里在会话中
读回来，且多带 5 个文件。

三个放大因素：

1. **峰值时刻从开头挪到结尾**：6 条 Read 分散在 S1/S2/S3/S4 与产出 JSON 之前（命令 L25/26/32/45/57/64），
   上下文峰值恰好压在最需要余量吐结论的那一刻。改之前规则一次性前置，输出阶段上下文平坦。
2. **「每文件恰读一次」是写给模型的纪律，不是代码强制**：小模型指令跟随弱，重读一次
   `s3-scoring-modes.md` 即 +9.8KB，Claude 上不犯的错换模型就犯。
3. **降级路径吃余量**：云 OCR 超时 → `inline_ocr` 灌整目录全文，把本就不多的余量吃光
   （放大器，非元凶）。

## 门禁为什么没拦住

`tests/test_prompt_budget.py`（KD3）只断言**单文件字节上界**。重构让每个文件都变小、门禁全绿，
真实负载却在涨——**给了虚假安全感**。三个评审 agent、两轮 review 也没抓住：reviewer 的 F7 只提了
轮次数（Read +5 vs `AUDIT_MAX_TURNS=30`），**没有人把 6 个 references 的字节加起来与旧版比**。
spec-compliance 逐条实测了 AC1「单文件 ≤15,000」并判 PASS——判据本身错了，执行得再严也没用。

## 教训（下次重设结构必须先做）

1. **预算判据改成单会话累计**：`命令正文 + 全部确定性 Read 的 references + CLAUDE.md + 注入的
   OCR 底稿` 之和，对照**部署矩阵里窗口最小的那个模型**（不是开发时用的 Claude）。渐进披露省的是
   "无关内容不进上下文"，当所有 references 都是**强制**读时，它一点也不省，只是换个地方装。
2. **验收标准的方向要与真实目标对齐**：AC 写「单文件 ≤15,000」时，真实目标是「会话上下文别爆」。
   判据与目标错位时，评审链越严格越是在为错误判据背书。参见
   [[2026-08-13-learning-design-budget-must-account-own-mandates]]（同一 sprint 的另一个预算表教训）。
3. **跨模型部署的功能，验收必须在最小窗口模型上做**：本次 runtime-verify 4 项被 defer 到部署窗口，
   其中第 1 项正是"6 条 Read 真实执行"——如果在小模型上跑过一单，事故会在 review 阶段暴露而非生产。
   defer runtime-verify 的代价这次实打实付了。
4. **`Prompt is too long` 不该重试**：确定性错误重试三次纯浪费，且掩盖真因。
   `server/tender/runner.py:294` 的重试循环需区分可重试 / 确定性错误。

## 回滚范围（2026-08-14）

只还原 `.claude/commands/tender-evaluate.md` 至 38,754B 单文件形态 + 预算上界复原。保留：
KD2 schema 单源（`output.py` 惰性 loader，无上下文影响）、KD4 调度表修正、references 5 档
（暂无引用，内容留作重设结构的素材）、KD3 门禁机制本身（判据待改）。
