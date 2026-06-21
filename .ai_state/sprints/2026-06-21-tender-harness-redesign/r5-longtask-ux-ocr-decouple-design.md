# 第5轮 design · tender 长任务体验 + 上传即 OCR 解耦

> mac mini 实测:评标耗时 **537s(9分钟)**。前端把"提交+等待评标完成"绑在一个 mutation
> `await Promise.all(waitForTenderTask)`,超时(`DEFAULT_POLL_TIMEOUT_MS`)→ onError → `setScreen('create')`
> 掉回第二步,用户白等。用户诉求:不限时长 / 可离开 / 回来恢复流式 / 彻底完成跳分析中心。
> + OCR 串行预处理是慢的大头(评标一开始才跑百页 OCR,前端干等)→ 解耦。

## A. 前端长任务体验(解耦"提交"与"等待")

**核心:submitReview 只负责"建项目 + 提交评标",不再 await 评标完成。**
1. `submitReview` = createTenderProject + 逐家 evaluateTenderProjectUpload,返回 `{projectId, requestIds}`,
   **删掉 `await Promise.all(waitForTenderTask)`**。mutation 立即 onSuccess。
2. onSuccess → `setScreen('analyzing')` + 把 `requestIds` 写入**项目级"进行中"持久化**(localStorage,key by projectId)。
3. **analyzing 界面独立轮询**(useQuery,refetchInterval,enabled=有进行中 requestIds):
   - 每轮拉 /tender/tasks/{rid} → progress_message 喂 progressByRid(流式滚动,复用已做的)。
   - **全部 completed → 跳 `analysis`(分析中心)逐项展示**;任一 failed → analyzing 内显示该家错误(**不掉回 create**)。
4. **可离开 / 回来恢复**:requestIds 持久化;用户导航走→该项目评标继续后端跑;回到该项目,
   若 localStorage 有进行中 requestIds → 恢复 analyzing + 轮询;否则按结果走 analysis。
5. **移除超时掉回**:onError 只处理"提交本身失败"(建项目/提交 422);评标进行中/超时**不掉回**。
   waitForTenderTask 的前端超时不再用于阻塞 mutation(改独立轮询,无硬超时或大幅调大)。

## B. 后端不限时长

`TENDER_TIMEOUT_SEC` 默认从 600/1200 调大(如 3600s)或显式 env;后端超时只作"防无限挂"兜底,
不再是用户体验瓶颈(前端已不阻塞等待)。同步 audit 的对齐项保持。

## C. 上传即 OCR 解耦(治"前端卡 OCR")

**利好:OCR 缓存已按 content-sha256(性能轮加的),"上传即 OCR"= 上传落盘后预热缓存。**
1. `materialize_upload_submission` 落盘后,**后台触发 OCR 预热**(asyncio.create_task / to_thread,
   不阻塞提交返回):对刚落盘的招标/投标文件调 OCR extract → 填 content-sha256 缓存。
2. 评标时 `ocr_preprocess_block` **命中缓存秒回**,砍掉评标时那段串行 OCR 等待。
3. 招标文件被多家投标复用 → content 相同 → 同缓存 key,只 OCR 一次。
4. 失败/超时回落:预热失败不影响提交(评标时再 OCR,退回原行为)。

## 影响范围

- `agent-front/.../use-tender-review-page.ts`(submitReview 解耦 + 独立轮询 useQuery + 恢复 + onError 收窄)
- `agent-front/.../api.ts`(waitForTenderTask 不再用于阻塞;或加 fetchTenderTask 单拉)
- `agent-front/.../components`(analyzing 完成跳 analysis;持久化 hook)
- `server/routes/tender_worker.py`(TENDER_TIMEOUT_SEC 调大)
- `server/routes/upload_helpers.py` / `tender.py`(落盘后触发 OCR 预热)
- `server/ocr/pipeline.py`(预热接口,复用 extract+cache)
- 测试(OCR 预热命中 / 后端超时 env)

## 风险与缓解

- **前端持久化脏数据**:localStorage 存了已完成/不存在的 requestIds → 轮询 404/completed 即清理。
- **OCR 预热并发**:上传多文件并发 OCR → 复用性能轮的 ThreadPoolExecutor + 信号量(已有)。
- **预热与评标重复 OCR**:content-sha256 缓存保证只算一次(预热填,评标命中)。
- **后端不限时长 → 僵尸任务**:保留一个很大的兜底超时(如 3600s)+ recover_stale 兜底,不是真无限。

## 验收

- 评标 9 分钟前端**不掉回**;切走再回该项目**恢复流式**;彻底完成**跳分析中心逐项展示**。
- OCR 解耦:上传后缓存预热,评标 OCR 阶段秒过(对比 537s 应显著下降)。
- 回归:全套 passed + ruff + 前端 lint/build。codex 配合 review。
