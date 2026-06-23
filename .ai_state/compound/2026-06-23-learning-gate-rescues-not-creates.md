---
doc_type: learning
date: 2026-06-23
sprint: 2026-06-23-tender-judgment-discipline
title: 服务端确定性闸只能「救」模型已产出的值，救不了「模型自己选保守」
---

# 服务端闸的边界：rescue ≠ create

## 一句话
确定性校验闸（evidence-resolution 降级、verdict 纠偏、格式兜底）只能**回滚/纠正模型已经产出的值**；
它**造不出模型根本没产出的值**——「模型自己选了 manual / 自己打了过低分 / 自相矛盾」是 prompt/model 层，
不是 gate 层。残留分类前必须先问这一刀。

## 证据（ZJ deepseek+glm 重测）
- **R2a 子项级证据降级** 救了 deepseek 技术参数：deepseek **打了 21 分**（性能参数有检测报告），
  闸原本因「无偏离」0 分子项 unresolved 把整项降 null——子项级修复让有分子项保住。✅ 闸能救。
- 同一修复**救不了 glm**：glm **自己**把技术参数标 `manual_review`（没打分）。闸面前没有「被误降的分」
  可回滚——值压根不存在。glm 的保守是 model-inherent，只能靠 prompt 收敛或 gate **反向强制造分**（慎用）。
- **R2b confirmed 闸** 救了 deepseek 被误强制 rejected：模型本意 manual_review + 一条 `confirmed:null`
  疑似命中 → 旧闸强制 rejected（造了个模型没要的废标）。加 confirmed 要求 = 闸**不再替模型造决断**。

## 推论（可复用）
1. 看到残留先二分：**「值被闸误伤」**（确定性可治：放宽/纠偏闸）vs **「值模型没产出」**（prompt 收敛 /
   或 gate 反向造值——造值是把判断权从模型移给规则，要非常克制，只在规则确定性强的场景）。
2. 闸的天然强项是**防误**（防编造、防越界、防自相矛盾），不是**补缺**。补缺优先 prompt。
3. e2e 多模型重测是区分这两类的唯一手段——单测只能验闸逻辑，验不了「模型会不会照做」。

## 附 trick：reasoning 模型文本模式 JSON 抽取
别用 `text.rsplit("</think>", 1)[-1]` 取答案——模型偶发在答案后跟**游离尾随 `</think>`**
（glm/deepseek），会截成空串误返 None → 整单契约失败重试至失败。改 `re.sub(r"<think>.*?</think>", "")`
**剥离成对块**：既去思考草稿、又不丢答案，游离单个 `</think>`（无配对）保留但不含 `{` 无害。
另：`reasons`/`policy_refs` 模型可能写成多行编号**字符串**（非数组）→ normalize 须 string→string[] 兜底。

相关：[[2026-06-22-learning-jsonschema-too-brittle-for-llm-output]] · [[2026-06-18-learning-absence-is-not-zero]]
