---
sprint_slug: "2026-08-11-compare-authority"
created: "2026-08-12"
path: "System"
polish_worker: "polish_worker subagent (worktree agent-ad32a594fad71cd9a)"
program: "2026-08-11-tender-eval-hardening (H1)"
---

# Cleanup Pass — 2026-08-11-compare-authority (H1)

> 范围 = 本 sprint review 已确认的 P2 清单，逐项闭环。不扩功能、不改判据语义、
> 不借格式化掩盖行为变化。全量回归与基线逐条一致（见文末）。

## 已执行

### F8 — `server/tender/compare_input.py` 两处职责混合

1. **副作用推导式**：`collect_compare_input` 组装 `CompareSignature` 时用列表推导跑
   `entry.pop("_request_id")`——推导式读起来是纯取值，实际在原地删 bidders 元素的字段。
   改显式循环，并注明 `_request_id` 只服务签名、取完即从对外结构剔除。
2. **判定函数改参**：`_pool_blocked_reason(bidders, warnings)` 既做封锁判定又往调用方传进来的
   列表里追加告警，签名看不出它会写。改为返回 `(reason, warnings)` 二元组，
   合并动作由 `collect_compare_input` 一处负责。告警在 `compare_input["warnings"]` 里的
   相对顺序不变（逐家护栏告警在前，单位不一致告警在后）。

commit `804874d`。行为等价：`tests/test_tender_compare.py` 全绿，未改任何测试。

## 已 defer（本轮不做，理由如下）

- **pass2-N5 前端 mutation 接线**：无前端 harness 覆盖该接线，polish 阶段动它属于
  「改了但验不了」。留给前端有测试覆盖时一并处理。
- 其余 pass1/pass2/pass3 findings 已在各自 impl 轮关闭，无 polish 残留。

## 5 检查项结论（本 sprint diff 范围）

1. **临时代码 / 调试痕迹**：无 `print` / `debugger` / 无 issue 号 TODO。
2. **注释完整性**：`_pool_blocked_reason` 新签名补齐 Args/Returns；模块级 KD 说明已有且准确。
3. **冗余 / 重复**：本次消掉的是"职责混合"而非重复实现；无第二套判据。
4. **低效模式**：判据全在内存列表上做，无循环内 IO。
5. **过度设计**：`_pool_blocked_reason` 返回二元组是**为消除隐式写参**，不是预留扩展点；
   无新增配置项 / 抽象层。

## VERDICT

**PASS** — F8 闭环，N5 显式 defer 并记录理由。
