# Decision · 外来 bid-document-auditor skill（用户 Claude 单跑提炼 v3.1.0）按最小面吸收

- 日期: 2026-08-17
- 类型: decision
- 背景: 用户在 Claude 网页端单独跑真实政府采购投标审核后提炼出一份 21KB 的
  bid-document-auditor skill，要求与平台现有 tender 提示词对照整合，且不得把提示词拆散。

## 吸收了什么（落点全在既有结构内，未新增文件）

| 采纳项 | 落点 | 理由 |
|---|---|---|
| 无效标触发词兜底检索（「否则按无效标处理」藏在技术需求正文） | tender-evaluate S1 rejection_rules + tender-extract-info 步骤2 | 通用防漏手法，S1 原文只说"逐条提取"未给检索方法 |
| 跨文件交叉一致性核对清单（声明函制造商↔报价表品牌、检测报告型号/依据标准↔所投参数、人员证书↔社保↔投标人、偏离表↔方案正文） | tender-evaluate S2 | 用户实测"最高价值缺陷全部来自跨文件矛盾"；原 S2 只有一句"一致性线索写进 ambiguities" |
| 证据效力核查要点（有效期覆盖投标日、业绩日期窗口、章的归属原厂≠投标人、多证同一人） | tender-evaluate S3 逐项判定 | 通用效力陷阱枚举；判定归宿仍走决策表 A2/A3/A8，未另立口径 |
| 电子标平台在线生成文件（投标函/开标一览表）缺失 ≠ 必交材料缺失 | tender-evaluate S3 废标 confirmed 闸反例 | 防误废标：平台机制导致的"缺失"须 confirmed:false + manual |

## 明确不吸收（防止未来被重新引入）

- **保守~乐观得分区间** → 与已定纪律「果断出分、分数即判定」冲突（eac2a16/914eb1b
  系列收口），且下游横比/合成总分需要单值。低置信走 low_confidence 标注，不走区间。
- **审核视角参数（投标人自检/评审模拟/第三方）** → 平台只有评审视角，加视角会分叉提示词。
- **阶段〇文档预处理（qpdf 修复/图片页清单/抽样目检）** → 归 Python 文档物理层
  （doc_pipeline / evidence_resolution.low_clarity_files / ocr-page），模型侧禁 Read，不进提示词。
- **中小企业划型阈值数字（工信部 300 号文）** → 训练记忆数字不进提示词（铁律[证据与出处]）；
  要用须拿官方源文件走 /init-rules 生成 govprocure 通则层。仅吸收其"声明函↔报价表交叉比对"手法。
- **Markdown 报告结构/中标概率/价格敏感性** → 输出是 audit-result JSON 契约，报告由前端派生。

## 连带发现

- `.claude/skills/tender-eval/references/` 下 5 个"权威版"文件（s1-criteria-structuring /
  s3-scoring-modes / s4-verdict-summary / evidence-citation / output-json）是 8-14 回滚
  （621c1e8 骨架+Read 形态生产爆窗）后的**死副本**：头部仍写"由 S2/S3 开头确定性 Read"，
  实际命令已禁 Read 且全文内联，内容已落后于 8-17 决策表收敛（b1bc53f）。
  唯一活引用 = tests/test_tender_pending_reason.py:82 拼接断言（其注释同样停留在回滚前）。
  s1-locate-criteria.md 仍被 /tender-extract-info 使用，是活的。处置待用户拍板（删 or 改头）。
