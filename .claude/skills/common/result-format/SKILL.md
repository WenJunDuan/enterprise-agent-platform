---
name: common-result-format
description: 将最终审核结论整理为统一结构的结果
---

# 通用结果整理

适用于所有需要输出统一审核结论的业务域。

输出格式如下：

```json
{
  "claim_id": "",
  "verdict": "approved | rejected | manual_review",
  "reasons": [],
  "policy_refs": [],
  "risk_score": 0,
  "extracted_data": {},
  "evidence_chain": [],
  "reviewed_by": "",
  "timestamp": ""
}
```
