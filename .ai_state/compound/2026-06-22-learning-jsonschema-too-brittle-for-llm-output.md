---
doc_type: learning
date: 2026-06-22
slug: jsonschema-too-brittle-for-llm-output
tags: [contract, validation, llm, tender, criteria]
---

# 整份 jsonschema 校验对"模型直出 JSON"过脆 → 用承重结构 sanity 检查

## 背景
R1 让 tender-doc OCR 后即抽 criteria（评分标准）存库+注入评标。codex 评审正确指出：注入评标的
criteria 必须先校验，否则残缺 criteria 污染逐项 scoring（P1）。第一反应是 `jsonschema.validate(criteria,
criteria.schema.json)`。

## 现象（接口自测，非单测——单测 mock 了模型调用看不到）
qwen 一次真实输出在**同一份合格 criteria（14 项 / Σmax=100）里同时出现三处枚举/类型漂移**：
- `method: "综合评分法"`（schema enum 要 "综合评估法"，一字之差）
- `items[].tag: "cross_bid"`（误用了 variables[].source 的短名，应 "requires_cross_bid_comparison"）
- `formula_spec.rounding: "内插法（线性）"`（enum 要 floor/round/ceil/none）
- `formula_spec.cap: {min:0,max:3}`（type 要 number|null，模型塞了对象）

`jsonschema.validate` 是 **all-or-nothing**：任一叶子不合格 → 整份 14 项合格 criteria 被判 failed →
功能形同虚设。逐个加 normalizer 是 whack-a-mole（修完 method 冒出 tag，修完 tag 冒出 rounding…）。

## 决策
分两层，按"这字段是否承重"对待：
1. **已知枚举漂移 → 确定性归一化**（`_normalize_criteria_enums`：method/tag/score_mode 别名→规范，
   映射不到→安全兜底：method=其他、tag=强制人工枚举、score_mode=manual）。清洁存储数据。
2. **承重校验改"结构 sanity 检查"**（`_criteria_looks_usable`）而非整份 schema：只查评标真正需要的
   最小结构——有评分项 + 每项有名字 + 满分是数字。结构垃圾（无 items/缺名/满分非数）→ failed；
   零星叶子瑕疵（enum/嵌套 type）→ 容忍（注入评标只作文本 hint、区2 防御式渲染，无害）。
3. 简单对象（tender_info 全 optional string）仍可用整份 jsonschema（叶子少、漂移少）。

## 一般化（可跨项目复用）
- **模型直出的结构化 JSON，不要用整份 JSON Schema 当硬闸**——模型在 enum/嵌套 type 上普遍漂移，
  all-or-nothing 会因一叶误杀整份可用输出。
- 问"**这份输出下游真正承重的最小结构是什么**"，只硬校验那部分；其余 normalize 或容忍。
- 校验失败的兜底要"优雅降级到下一条可用路径"（criteria 抽取失败 → 评标自行 S1 解析），不是整链崩。
- **接口自测抓到、单测漏掉**：单测 mock 了 `run_command_json`，看不到真实模型输出的漂移；每轮必须
  起真后端 + 真模型跑一遍（见本 Sprint 用户铁令"每轮 3 家 AI 切环境自测"）。

## 关联
- 设计/处置详情：sprints/2026-06-22-multimodel-tender-optimization/round-1-tender-info-extraction/design.md
- 同源教训 [[2026-06-18-learning-absence-is-not-zero]]（范畴错误：把"读不清/无对应"当客观 0 分）。
