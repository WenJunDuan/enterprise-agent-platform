---
date: 2026-08-14
type: issue-analysis
slug: tender-context-overflow
path: Bugfix
---

# 根因链

```
云 OCR 写超时
  └→ doc 层底稿不可用 → runner 降级 source=inline_ocr（tender_ocr_source 日志实证）
       └→ ocr_preprocess_block(directory_path) 返回**整个 case 目录**的 OCR 全文
            └→ 注入点直接 f-string 拼进 context，无任何长度上限          ← 缺陷 A
                 └→ 内网 DeepSeek Flash 窗口（远小于开发用的 Claude）被打爆
                      └→ 网关 400 'Prompt is too long' → JSONContractError
                           └→ 重试环把同一个过长 prompt 原样重发 3 次        ← 缺陷 B
                                └→ 整单无结论，真因埋在三条一样的重试日志后
```

## 缺陷 A：注入点无预算闸

`server/tender/runner.py` 的注入点把 `ocr_block` 原样拼进 context。案卷大小由用户上传决定，
是**外部输入**——信任边界上没有任何上界，属 P0 级缺防御。

已有的 `server/tender/context_slim.bound_tender_context` 看似是闸，实则**配置态**：
`_preextract_char_budget()` 需要部署同时声明模型 context window 与 max output tokens，
任一缺失即返回 `None` → 调用方保留全量 context。内网部署未声明，闸整体静默失效。
"未配置就不设防"在这里等价于没有闸。

## 缺陷 B：确定性失败被当作可重试

重试环（`for attempt in range(TENDER_CONTRACT_MAX_RETRY + 1)`）当初是为 deepseek 文本模式
**间歇性**不出 JSON 加的，前提是"重跑可能成功"。`Prompt is too long` 是**确定性**失败：
输入不变 → 结果必然相同。三次重试不仅浪费十几分钟内的窗口，还让日志里出现三条同文
WARNING，把唯一有信息量的那一行淹没。

## 与 2026-08-13 prompt-architecture 重构的关系

重构让单次评标脚手架从 48,706 B 涨到 55,439 B（+13.8%），确实压缩了余量，但它**不是**唯一元凶：

- 缺陷 A 与 B 在重构前就存在（`inline_ocr` 全目录注入是老路径），只是当时云 OCR 没坏、没触发。
- 回滚只还原了脚手架体积，A、B 两条一个都没修 —— 云 OCR 再超时仍会复现。

结论：脚手架增长是**放大器**，缺陷 A 是**元凶**，缺陷 B 是**掩盖器**。本次两处修复独立于回滚。

## 为什么门禁没拦住

`tests/test_prompt_budget.py` 只断言**单文件字节上界**，而真实风险是**单会话累计注入**
（命令正文 + references + CLAUDE.md + 注入底稿）对照**部署矩阵里窗口最小的模型**。
判据方向与真实目标错位时，评审链越严格越是在为错误判据背书
（详见 `.ai_state/compound/2026-08-14-learning-prompt-budget-must-be-per-session.md`）。

本次修复对齐的是"注入底稿"这一项的硬地板；会话累计预算判据本身的重设不在本 Bugfix 范围。
