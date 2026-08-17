# 部署窗口清单（一次跑完 · 2026-08-18 开工即用）

> **为什么先部署再评审**：runtime-verify 需要部署机 + 真实标书，它是 review 的**前置**
> （Refactor 路径门禁序：runtime-verify → review → polish）。8-17 那轮把顺序做反了（先跑
> pass3），导致用户想"跑一遍看看"的目标一直往后退。**明天第一件事是部署，不是 pass4。**
>
> 本档把散在 design / handoff / pass3 / tdd-evidence **四处共 18 处**的 deferred 项收成一张
> 有序清单，现场照着做，不要再回去拼文档。

## 0. 前置（本机，10 分钟内）

- [ ] `git log --oneline -1` 确认 HEAD = 含全部修复的那个（S5–S8 + 三条 P1 修复 + 匿名化）
- [ ] 全量回归结果为 **17F/1633P 量级、与基线逐名 diff 为空**（记录见 tdd-evidence
      `pass4_full_regression`）。**未取得则先修，不带病部署**
- [ ] 前端 `cd agent-front && bun run build`
- [ ] 推送：`ATHENA_ALLOW_PUSH=1 git push`（本地领先 origin 约 40 个提交）

## 1. 部署（按 `_index.md` 既有形态，勿即兴改）

- [ ] 后端 `docker build --build-arg WITH_OCR=1`
- [ ] **env 有改动必须 `docker rm -f` 重建**（`restart` 不重读 `--env-file`，踩过）
- [ ] SSH 用长连接 `ControlMaster` + `ControlPersist=60m`
- [ ] 起服务后 `GET /health` 确认

## 2. 冒烟：先证明它能跑通（用户的核心诉求）

- [ ] 传一份**真实招标文件 + 一家投标**，走 `POST /tender/projects` →传文档→
      `POST /projects/{id}/evaluate`
- [ ] **看结论**：`verdict` / `eligibility_checks` / `scoring` 是否成形；出处能否点回原文页
- [ ] **计时**（AC7）：端到端耗时。目标 ≤10 分钟；>20 分钟按用户口径 = 架构问题

## 3. runtime-verify 产出物（补门禁缺口，边跑边记）

写 `runtime-verify.md`，至少含：接口实跑记录、耗时、结论截图/JSON 片段、发现的问题。
**这是 delivery-gate 认的产出物，pass3 里那句"defer 到部署窗口"不算数。**

## 4. AC16 数据闸 + 遗留项实测（同一份底稿一次测完，避免重复上传）

- [ ] **AC16 主体**：`uv run python scripts/measure_tender_evidence.py <底稿> --criteria <本项目 criteria>`
      对比 S5 基线；⚠ **口径已变**：S5 数字是「单项独跑」，S7 后须按**全项同跑 `item_tokens`**
      重测基线，或改用内容判据（该项证据是否仍覆盖同一小节）——见 design 实施修订③
- [ ] **AC13 后半**：其余 8 项命中与注入量逐项比对，确认 S6 回退未误触发
- [ ] **AC9/AC10 重测**：出处保真率、逐项注入字数（S8+S7 后从未重测）
- [ ] **F8 关键观测**：**必须用一份评分项数 ≥15 的标书**跑一次。`per_item = evidence_tokens/n_items`
      在 15 项时跌破 `MAX_CHUNK_CHARS`(4000)，届时任何满尺寸 chunk 都装不下、续接完全不发生。
      本 sprint 全部实测基于 9 项那一份，**该形态从未被真实数据覆盖**。先测形态再定修法
      （候选：不可分单块借用全局额度 / 超长行按字符兜底切分 / 视为固有约束），不得盲改
- [ ] **F9 顺带观察**：多份源文件的投标，续接是否跨文件滑动（`following_rows` 只按层过滤）

## 5. 回本机后

- [ ] runtime-verify 结果落档 → **pass4**（reviewer + spec-compliance → evaluator）
- [ ] pass4 PASS → **polish**：F4/F5/F6/F9 四条 P2 + `contract_repair` 架构档
      （`.ai_state/architecture/`，含"为何不整单重跑"与 resume 前提）
- [ ] 全部收口才谈 ship

## 现场原则

- 真实标书**只在部署机上用**，任何片段不得回流进仓库（守卫 `tests/test_no_real_corpus.py` 会咬）
- 发现新问题**先记不修**，回本机走 TDD；现场热修没有红绿证据
