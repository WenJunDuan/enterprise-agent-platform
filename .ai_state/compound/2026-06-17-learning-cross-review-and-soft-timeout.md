---
name: cross-review-and-soft-timeout
description: to_thread 软超时无法限流的反模式 + 交叉 review 的修复本身会引入新问题、需按收敛判据多轮
metadata:
  type: learning
---

## to_thread 软超时反模式

`asyncio.wait_for(asyncio.to_thread(fn), timeout=T)` 超时**不取消线程**——只取消等待的
协程；线程继续跑，而 `async with semaphore` 立即退出释放名额。后果：在并发闸下，重复的
超时请求会不断启动新线程，实际并发远超 `MAX_CONCURRENT_OCR`，CPU/GPU/内存耗尽。

**正解**：不可取消的阻塞任务（线程 / 子进程）应在信号量内 `await` 到自然完成，靠**下游
自身超时**（如 litellm request_timeout）兜底，而非用 wait_for 在外层"取消"。只有可取消的
asyncio 协程（如 HTTP 请求）才适合 wait_for 超时——OCR `/fill` 的模型映射就保留了 wait_for。

踩了 codex 三轮才点透：轮1/2 当软超时缓解（不删目录、靠 maintenance），轮3 才认清根因。

## 交叉 review 的修复本身需再 review

codex 四轮交叉 review 共 14 findings，趋势 5→2→4→3，**未收敛到 0**；且多个 finding 是
修复前一轮引入的：

- 轮2 的 2 个 = 轮1 修复（软超时不删目录 / path 投影 basename）的副作用
- 轮4 的 P2/P3 = 轮2/轮3 修复（orphan cleanup CWD / font-only 回退 note）的副作用

**教训**：每轮修复都是新代码、会带新 bug；交叉 review 不能"修完即收工"，修复 diff 要进
下一轮 review。应设**收敛判据**（连续一轮无 P0/P1/P2）而非固定轮数——固定轮数要么过早停
（漏掉轮4 的 symlink 任意文件读取 P1），要么无限跑。

**Why:** 独立交叉 review（CC 改、CX 审）能持续发现自我锚定看不见的问题，尤其安全；
但边际递减且修复会引新债，必须有收敛判据。
**How to apply:** 多轮交叉 review 时，每轮 review 上一轮的**修复 diff**，按"连续一轮无
P0/P1/P2"停。关联 [[classify-fix-exposes-latent-bug]]。
