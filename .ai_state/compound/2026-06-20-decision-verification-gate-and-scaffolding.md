---
doc_type: decision
date: 2026-06-20
slug: verification-gate-and-scaffolding
sprint: 2026-06-20-agent-capability-redesign
---

# 决策：验证闸=「验证非判断」 + 不可用依赖=「脚手架+env 门控」

agent-capability-redesign sprint 沉淀的两条可复用工程决策（依据 round4-fullstack-review）。

## 一、验证闸放在 `apply_schema_semantics`，做「验证」不做「判断」

平台核心价值 = 可追溯有依据的判断；但默认文本路径此前**不校验模型输出**（round4 F1 BLOCKER）。
修法：在 `server/common/contract.apply_schema_semantics`（DRAFT 后、enrich 前）逐层加校验，**只验输出
自洽/真伪，不替模型判 verdict**——这避开了 gotcha「审核判断在 Claude 侧、Python 不判断」：

1. `jsonschema.validate` 形校验（required/类型/additionalProperties/enum）。**必须在 enrich 前**——
   enrich 派生 result/conclusion，而 schema 是 `additionalProperties:false` 不含这俩。
2. 语义闸：approved/rejected 须引 ≥1 `policy_ref`（空=无依据判决）。
3. `policy_refs ⊆ 真实 rule_id`（防编造规则号）+ 评分 `score≤max`（防超量纲自相矛盾）。

**边界**：凡需 Python「拿真实输入文件/重算金额」的更深验证（evidence_chain source 解析、算术重算），
就越过「验证」滑向「判断」+ 需要 domain→rules/OCR 数 管线 → **留 backlog，开工前先和用户定边界**。

## 二、手上没有的依赖：建全套代码 + env 门控 + 优雅跳过，而非 de-scope

G3 外部信用 API「用户暂时没有接口」。**不要 de-scope**，也不要硬编。模式（用户拍板）：

- 全部代码做好（工具 `server/ops/credit_api.py` + 强 I/O 契约 + config + CLI + 测试）。
- **env 门控**：`CreditApiSettings.configured`（url/key 任一空）→ 工具返 `None`。
- **未配置→优雅跳过**：调用方保持 `manual_review`（= round4「不可判定项绝不判 0」的正确兜底）；
  HTTP/校验失败也降级 `None`，绝不 crash 审核。
- 用户后续只填 env（`CREDIT_API_URL/KEY`）即用，无需改代码。

同款用于 **G1b-full**（`RULE_REF_CHECK` 默认关，避免 gitignored `knowledge/` 破坏测试确定性；部署侧规则稳定后开启）。

## 三、good taste：五诉求 → 两脊椎

任务拆解/多工具/记忆/幻觉抑制/反馈修正 五诉求，**四项共用「类型化契约+过闸验证」（脊椎一·验证闸），
只有记忆是独立维度（脊椎二·制度>案例>工作，案例从属制度）**。先识别共用机制再动手，避免造五个并行模块。

## 复用提示

- 新加输出字段的语义校验 → 进 `output_contracts._validate_audit_result`（验证非判断）。
- 新接外部数据源 → 抄 credit_api 模式（契约+env 门控+优雅跳过）。
- 删死域先于抽象（round4「先减熵后抽象」）：本 sprint 先 G0a 删 contract/HR 再 G0b 泛型化。
