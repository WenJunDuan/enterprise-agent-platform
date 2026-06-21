# Goal · 多模型评标优化 Sprint（2026-06-22 起）

> 用户设定（2026-06-21 晚）：多模型轮换测试持续优化评标质量与性能，自测 + 自调优，每轮 codex 配合。

## 一、目标（优化方向）

1. **OCR 速度与效率** —— 上传即 OCR 已解耦（第6轮），继续压速度/准确度（扫描件/盖章/表格还原）。
2. **招投标审核速度与准确度**：
   - **抓取招标评分点和分数**（criteria 提取：评分项/满分/扣分点/废标条款，准确不漏不错）。
   - **应标数据正确抓取 + 对应上下文**（投标抓点：投标人/报价/业绩/资质 + evidence_chain 对应到正确出处页）。
3. **数据存储**（三层数据结构正确性：招标层项目级一份 / 投标层每家 / criteria 回填复用）。

## 二、工作方式

- **多模型轮换测试**（.env 切 MODEL_NAME + MODEL_BASE_URL + MODEL_AUTH_TOKEN）：
  - **DeepSeek**：`deepseek-v4-pro` @ api.deepseek.com/anthropic
  - **qwen3.7-max**：`qwen3.7-max` @ dashscope.aliyuncs.com/apps/anthropic
  - **claude-opus-4-8**：@ anyrouter.top（注意 anyrouter 强制 [1M] 变体 + 偶发 429/Service Unavailable）
- **每改完一版自测**：起后端(`uv run python -m server.cli serve`) → 调 API(上传/评标) → 看 serve.log + 评标结果(verdict/scoring/claim_id/耗时) → 自己定下一步调优方向。
- **范围**：`.claude/`(prompt/契约) + Python `server/`(OCR/评标/store) + `agent-front/`(前端对接)。
- **每轮 codex 配合** review（codex exec --sandbox read-only）。每轮可 generator subagent(worktree) 实施大块。
- 模型差异要点：**思考流式实时性依赖端点是否流式吐 partial**——claude/deepseek 文本模式吐多片段(实时)，**qwen 一次性返回(不实时)**，见遗留①。

## 三、本会话遗留问题（待本 Sprint 处理）

| # | 问题 | 现状/方向 |
|---|---|---|
| ① | **qwen 思考流式不实时** | qwen 端点一次性返回(session log 仅 1 个 assistant_text)，on_progress 只在结束触发一次、flusher 已 cancel → progress 停"运行中"。修：开 `include_partial_messages` + run_agent_json 处理 StreamEvent partial(要试 dashscope 是否支持流式 SSE)；或简单兜底 flusher 退出前最后 flush 一次。 |
| ② | **criteria 项目级回填验证** | 第6轮已实现 `update_project_doc_criteria`(评标后回填、后续家复用治"每家重复解析")，**待端到端验证**首个写入赢 + 后续家读已存。 |
| ③ | **compare 首次横比 refetchInterval 停** | codex r5 P1-5 未修：triggerTenderCompare 异步，compare 查询 404/null 时 refetchInterval=false → 首次横比没生成停空。多家完成后边缘。 |
| ④ | **delete 磁盘目录清理** | 第6轮 delete 级联清了两表，但 `data/submissions` 下 OCR 产物目录可能未清(codex P2 P1-5)。 |
| ⑤ | **G5 S2 公式变量清单** | 第3轮 codex P1-2 backlog：限价类 formula 单家算需 S2 抽 limit_value/bid_component/formula_variables 结构化(现 S3 靠模型从底稿临场找)。 |
| ⑥ | **招标人侧合规 MVP** | design-r2 未 impl：排他性条款/可量化性/废标清单/投标时限规则。先 /init-rules 补 tender_regulation_032 + 时限到 knowledge/tender。 |
| ⑦ | **OCR 置信度深化** | design P2：扫描盖章页/手写低置信 → file_clarity 标注 + 提示人工(接 G3 触发)。 |
| ⑧ | **effort 对各端点支持** | effort=xhigh(tender per-call) 对 Claude 原生支持；deepseek/qwen 兼容端点是否透传/有效待验(qwen 评标跑通但 effort 是否生效未确认)。 |

## 四、已有基础（本会话第1-6轮成果，git main，29 commits 未 push）

- **第1-2轮**：criteria 提取从2项→20项精准(C 根因 normalize 剥未知字段 + cowork G1-G7 prompt) + A absence-not-zero + OCR 性能轮(并行/缓存/线程安全)。
- **第3轮 G5**：formula 公式变量结构化 formula_spec(限价类单家可算/白名单派生/拆子项/阶梯走 banded)。
- **第4轮**：thinking effort(tender per-call xhigh) + logs 三项(清噪音/思考日志/轮转) + 思考流式(轮询伪流式 progressByRid)。
- **第5轮 A+B**：长任务体验解耦(评标不阻塞前端/独立轮询/可离开回来恢复/不超时掉回/完成跳分析中心)+ 后端 TENDER_TIMEOUT_SEC 3600 兜底。
- **第6轮 C(P2+P3)**：三层数据(tender_doc_store) + 上传即 OCR 解耦(tender-doc/bids 端点后台 OCR 预热 + docs-status 轮询 + 评标读层单家) + 前端三区布局 + 拆"上传/开始分析"两步。codex P2 REWORK→全修(读层单家防污染/OCR并发/失败failed/强制文件/tenant)。+ ClientDisconnect 捕获 + analyzing 假死能返回列表。
- **端到端验证(qwen3.7-max)**：评标 completed 225s(比之前 537s 快一半，OCR 解耦+读层命中) / verdict rejected(投错标废标正确) / 20项 scoring / claim_id 正确。
- **558 passed + ruff + 前端 lint/build**。git 干净(只 main、零未 commit)。

## 五、关键操作备忘

- **dogfood**：项目级 `POST /tender/projects/{id}/evaluate`(无绑定 /tender/evaluate 要 __unbound__ 路径)；素材 `data/submissions/default/tender/tp-f856d66c0e244467/case`；绝对路径 + `mode:"directory"`；token = `.env` TENANT_KEYS JSON 的 `.default`。
- **上传即 OCR 测**：`POST /tender/projects/{id}/tender-doc`(招标)、`POST .../bids`(投标 + bidder_name form 字段)、`GET .../docs-status`(轮询)。multipart `-F "files=@路径"`。
- **mac mini 部署**：rsync(非 git)；SSH 直连 `mac@100.107.151.115` ConnectTimeout30 + StrictHostKeyChecking=no(.ts.net 域名解析慢用 IP)；远程登录需开。
- **cat 被 alias 成 bat(未装)**——用 Read/grep 别用 cat；查 mac mini 日志用 ssh 远程 grep。
- **本机 cat 别用**(bat alias)；读 token 用 `rg -o 'TENANT_KEYS=\{[^}]*\}' .env | sed | jq -r '.default'`。
</content>
