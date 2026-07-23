# route-note · 2026-07-23-tender-case-header

> 2026-07-23 重建×2(hook 摧毁事故:X2 agent worktree Stop hook 反向同步 .ai_state,根因已锁定,worktree 已拆除)。

## 任务
用户报告(2026-07-23):评标 agent 分析已拿到项目名称/投标单位名称,但结论不留存、界面不显示;要求抓下来 + 评标 agent 字段完整性深研。用户拍板与 X1 **同步并行**。

## 分诊
- **根因四点**(file:line 在 items.yaml X2 note):命令层只要标识语义/结果契约无案卷头节/worker 不回填/前端展示名唯一来源=上传手填。
- **关键存量**:招标层 tender-info.schema.json(手填优先/派生只填空/区1 展示)+ 前端 displayNameByClaim——X2=同一纪律延伸到评标结论层。
- **路径**:Feature(选定,四层增量全有既有接缝);风险面:tender-evaluate.md 生产提示词改动克制;D1 golden 需网关→部署机窗口。
- **置信度**:高。

## 决策
path=Feature · design 先行 + critic(实际三轮)→ generator worktree → 主 agent 四证据独立验。

## 事后追记(2026-07-23,透明记录)
①**模型违约**:generator.md `model: sonnet` pin 压过 opus 覆盖,T1-T3 实为 sonnet-5 所写;②两次 API 断连;第二次后主工作区曾被错误切到 agent 分支(git 状态错乱),已修复回 main;③T1(8baef0f)/T2(5fbf482)/T3(d6bc5cc)在分支 `worktree-agent-a9ea79174969a5183` 上,**未 merge main**;T2 后端部分经主 agent 在分支态独立验 **981 passed/2 skipped+ruff 净**(基线 955,+26;期间 fitz 缺失系 uv sync 未带 --extra ocr,已恢复);T4 未做;④处置(merge or opus 重做)待用户拍板。
