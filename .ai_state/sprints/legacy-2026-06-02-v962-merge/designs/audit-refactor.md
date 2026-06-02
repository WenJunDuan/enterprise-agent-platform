# Audit 业务重构设计 — ⚠️ P1 已撤销

**状态（2026-04-20 更新）**：P0 契约扩展保留（`audit-result.schema.json` 新字段 + `core.py` validator），P1 全部撤销（违反脚手架原则），设计文档后半部分（金额提取/签字提取/orchestrator/fast 端点）仅作历史记录。

**撤销原因**：设计最初把 Python 划分为"数据搬运层"是错的。Python 只负责通信 / 鉴权 / 服务，不碰任何业务概念（发票、规则、金额、审批节点等）。审核流程应继续走 `/audit` 和 `/audit/submit` agentic 路径，由 Claude 一手负责文件读取 + 规则匹配 + 判断 + 结论。

**保留的真 IPC 契约**：
- `.claude/contracts/common/audit-result.schema.json` 新增 `manual_review_reason` / `risk_dimensions`
- `server/core.py:validate_structured_output_semantics` 对应两段守卫
- `server/prompts/audit.md` 规则 #7 补充 `manual_review_reason` 枚举指令
- `README.md` 新字段说明

**以下内容仅作为设计演进记录保留，不再作为实施基准。**

---

# Audit 业务重构设计 — 对齐财务审核工作流（历史草稿）

**状态**：草稿，已弃用
**作者**：基于 2026-04-20 调研，2026-04-20 校准边界
**范围**：`server/audit/*`（新增）、`knowledge/expense/*.rules.json`（补齐）、`.claude/contracts/common/audit-result.schema.json`（扩展）

---

## 0. 架构边界原则（重要）

**Python = bridge / infrastructure，Claude = auditor**。所有业务判断必须在 Claude 侧完成，Python 只做数据搬运和守门。

| 属于 Python（允许） | 属于 Claude（必须） |
|---|---|
| HTTP、鉴权、持久化、会话管理 | 合规判断（规则命中） |
| 受理守门（表单完整性 / 附件 MIME / 规则库就绪） | 金额是否偏差过大 |
| PDF → 文本、OCR（数据搬运） | 审批链是否合规 |
| 规则 JSON 读到内存（数据搬运） | 风险等级定性 |
| 加载 prompt 模板 | 证据链组织 |
| 把 AuditContext 喂给 Claude | verdict / conclusion / explanation / risk_score |

**判断型工作全归 Claude**，即使涉及数学（Claude 4.7 算术足够好）。Python 从不输出"是否合规 / 是否超标 / 缺哪个节点"等**比对结论**，只输出原始数据（`invoices_total`、`actual_signed_nodes` 等）。

---

## 1. 动机

当前 audit 业务存在三类结构性问题：

1. **职责错配**：Claude 做确定性工作（枚举文件、PDF 解析、金额比对、规则 JSON 读取），Python 做薄编排。单次审核对外 4-5 次 API 请求。
2. **规则库缺失**：`knowledge/expense/*.rules.json` 当前为空，Claude 只能靠 prompt 里的兜底文本做判断。
3. **质量无分类**：`manual_review` 出自由文本，无法统计"最多被打回的原因"。`risk_score` 是静态值，多维风险叠加识别不到。

---

## 2. 目标架构：11 步财务审核编排

```
┌──────────────── Python 层（搬运 / 守门 / 归档，不做业务判断）──────────────────┐
│ Step 1  受理守门    表单必填、附件 MIME、规则库就绪；判"该不该发 Claude"        │
│ Step 2  资料数字化  PDF→文本、图片 OCR、附件元数据归类（纯搬运）                │
│ Step 3  规则预加载  启动时载入 knowledge/expense/*.rules.json，按 category 索引 │
│ Step 4  金额提取    解析发票合计、申请合计、事前审批额（只输出数值，不做判断）  │
│ Step 5  签字提取    从表单/附件抽"已签字节点"清单（只输出事实，不比对应签）     │
│ Step 11 归档        结果落盘、索引更新                                         │
└──────────────────┬─────────────────────────────────────────────────────────────┘
                   │  AuditContext（纯数据 + 规则 + 历史摘要）
                   ▼
┌──────────────── Claude 层（所有业务判断都在这里）──────────────────────────────┐
│ Step 6  合规判断        规则命中、例外情形、冲突裁决                            │
│ Step 7  金额 / 事前审批 比对数值、判偏差是否合理、事由一致性、时间顺序          │
│ Step 8  审批链合规      对照规则推导应签节点、指出缺口                          │
│ Step 9  异常识别        结合历史摘要（若有）                                    │
│ Step 10 风险评分        各维度 0-10 打分（Claude 填）+ 综合 risk_score（Claude 填）│
│ Step 11 结论出具        verdict / conclusion / explanation / evidence_chain     │
└────────────────────────────────────────────────────────────────────────────────┘

Claude 运行时：allowed_tools=[]，max_turns=1，output_format=json_schema
```

---

## 3. 数据契约

### 3.1 AuditContext（Python → Claude）

```python
# server/audit/contracts.py（新增）

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Literal


class ExpenseCategory(str, Enum):
    invoice = "invoice"
    travel = "travel"
    entertainment = "entertainment"
    loan = "loan"
    transport = "transport"
    general = "general"


@dataclass(frozen=True, slots=True)
class ApplicantInfo:
    name: str
    role: str            # 职级（P5/M2/…）
    department: str
    employee_id: str


@dataclass(frozen=True, slots=True)
class ExpenseClaim:
    claim_id: str
    category: ExpenseCategory
    amount_claimed: float
    currency: str        # CNY / USD
    event_date: date     # 发生日期
    purpose: str         # 事由
    city: str            # 发生地
    city_tier: Literal[1, 2, 3] | None  # 城市等级（仅差旅用）


@dataclass(frozen=True, slots=True)
class ParsedInvoice:
    invoice_no: str
    invoice_type: Literal["special", "general", "e_invoice", "receipt"]
    issue_date: date
    amount: float        # 价税合计
    tax_amount: float
    payer_entity: str    # 抬头
    seller_entity: str
    is_duplicate: bool   # Python 启动时维护全局去重表
    is_overdue: bool     # 是否超期（超 90/180 天）


@dataclass(frozen=True, slots=True)
class FileMeta:
    path: str
    kind: Literal["application_form", "invoice", "itinerary", "hotel_folio",
                  "pre_approval", "receipt", "other"]
    size_bytes: int
    mime_type: str


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str                                       # 如 expense.travel.004
    category: ExpenseCategory                          # 从文件顶层下沉
    description: str
    action: Literal["approve", "reject", "escalate"]   # 对齐 rule.schema.json
    priority: int
    confidence: Literal["high", "medium", "low"]
    conditions: dict                                   # max_amount / required_docs / applicable_roles / approval_level / frequency_limit
    original_text: str
    notes: str
    source_path: str                                   # knowledge/external/...
    source_title: str                                  # 从文件顶层 source.title 下沉
    source_excerpt: str                                # 章节定位


@dataclass(frozen=True, slots=True)
class AmountExtraction:
    """纯数值提取，不做任何"是否合规"判断。"""
    invoices_total: float           # 发票金额合计（Python 求和）
    claim_total: float              # 报销申请金额（来自表单）
    pre_approval_total: float | None  # 事前审批金额（来自附件，可能缺失）
    # 注意：不输出 variance_pct / exceeds_pre_approval 等判断字段。
    # 偏差是否合理由 Claude 结合规则判定。


@dataclass(frozen=True, slots=True)
class ApprovalSignatures:
    """只提取已签字节点的事实，不推导"应签什么"。"""
    actual_signed: tuple[str, ...]  # 实际已签字的节点（如 ("lead", "finance")）
    # 注意：不输出 required_nodes / missing_nodes。
    # 应签节点由 Claude 对照规则推导。


@dataclass(frozen=True, slots=True)
class PreCheckResult:
    """仅表达"能不能把这单发给 Claude"，不做业务判断。"""
    form_complete: bool
    missing_form_fields: tuple[str, ...]
    attachments_valid: bool
    invalid_attachments: tuple[str, ...]
    rule_library_ready: bool
    amount_extraction: AmountExtraction | None       # P1.3 填，P0 为 None
    approval_signatures: ApprovalSignatures | None   # P1.4 填，P0 为 None
    can_proceed_to_claude: bool   # False → 直接 manual_review，不发 Claude


@dataclass(frozen=True, slots=True)
class HistorySummary:
    applicant_claims_last_90d: int
    same_category_last_30d: int
    last_rejected_reason: str | None
    frequency_z_score: float      # 同申请人频率异常度


@dataclass(frozen=True, slots=True)
class AuditContext:
    case_id: str
    applicant: ApplicantInfo
    expense: ExpenseClaim
    invoices: list[ParsedInvoice]
    attachments: list[FileMeta]
    rules: list[Rule]                       # 已筛选
    pre_checks: PreCheckResult
    history: HistorySummary | None
```

### 3.2 AuditResult（Claude → Python）— schema 扩展

现有 `audit-result.schema.json` 保留向后兼容，**新增字段**：

```json
{
  "manual_review_reason": {
    "type": "string",
    "enum": [
      "missing_approval",        // 审批链缺节点
      "rule_gap",                // 规则库无覆盖
      "data_conflict",           // 金额/日期/实体冲突
      "insufficient_evidence",   // 证据不足
      "budget_exceeded",         // 超预算/超额度
      "invoice_invalid",         // 发票异常
      "pre_approval_mismatch"    // 事前申请与实际不符
    ]
  },
  "risk_dimensions": {
    "type": "array",
    "items": {
      "properties": {
        "name": { "enum": ["invoice", "amount", "approval", "budget", "anomaly"] },
        "score": { "type": "integer", "minimum": 0, "maximum": 10 }
      }
    }
  }
}
```

- `manual_review_reason`：`verdict == "manual_review"` 时必填
- `risk_dimensions`：各维度 0-10 分，由 **Claude 填**
- `risk_score`：0-100 整数，由 **Claude 填**（Python 不代算，保持"判断型工作归 Claude"原则）

---

## 4. 模块布局

```
server/
├── audit/                          # 新增目录（P0 已建 __init__/contracts/intake）
│   ├── __init__.py                 # P0 ✅
│   ├── contracts.py                # AuditContext dataclass  P0 ✅
│   ├── intake.py                   # Step 1 受理守门         P0 ✅
│   ├── extractor.py                # Step 2 资料数字化（PDF/OCR，纯搬运）  P1
│   ├── rules_loader.py             # Step 3 规则预加载 + 内存索引        P1
│   ├── amount_extract.py           # Step 4 金额提取（只读数值）         P1
│   ├── approval_signatures.py      # Step 5 签字提取（只列实际节点）     P1
│   ├── history.py                  # Step 9 历史摘要（仅数据搬运）       P2
│   ├── orchestrator.py             # 主编排：串 1→2→3→4→5→Claude→11    P1
│   └── prompt_builder.py           # 用 AuditContext 构造最小 prompt     P1
├── prompts/
│   ├── audit.md                    # 保留（回退路径）
│   └── audit_fast.md               # 新增：inline 版本，无工具           P1
```

**注意**：不再有 `amount_check.py` / `approval_chain.py` / `risk_score.py`，这些都是业务判断职责，归 Claude。

---

## 5. 关键决策

### 5.1 为何不一次性替换原 `/audit` 端点

- 现有 agentic 路径是已知稳定的（虽然慢），作为**回退**保留
- 新增 `POST /audit/fast` 使用重构后的编排
- 按材料大小 + 规则库就绪度自动路由（可切回）

### 5.2 为何 risk_score 由 Claude 算（原设计更正）

- 原设计曾计划让 Python 加权算 `risk_score`，违反"判断型工作归 Claude"原则
- Claude 4.7 的整数加权算术足够准确，风险评级本身是业务判断，不是纯算术
- Python 仅保留 `risk_weights.yaml` 作为**给 Claude 的参考权重**（prompt 里告知）
- 好处：审计链里所有判断都集中在 Claude，易于对账；Python 不藏任何业务决策

### 5.3 为何 `manual_review_reason` 强制 enum 而非自由文本

- 统计可观测（后续可看"最常被打回的原因"）
- 触发自动化补救（如 `missing_approval` 可推送提醒而非人工介入）
- 自由 explanation 仍保留，enum 做索引维度

### 5.4 规则库缺失时的行为

- Step 1 `PreCheckResult.rule_library_ready == False` → 直接 `manual_review`，`manual_review_reason = rule_gap`，**不发 Claude**
- 启动时 `rules_loader.load_all_rules()` 若发现空或损坏，`logger.error()` 并设置全局 flag
- `/ready` 端点反映 `rule_library_ready` 状态

---

## 6. 与现有代码的兼容

- `server/command_adapter.py:build_audit_prompt` 保留不动（agentic 回退）
- `server/core.py:validate_structured_output_semantics` 需新增 `manual_review_reason` 的条件校验（P0 ✅）
- `server/api.py` 新增 `/audit/fast` 端点（P1），老 `/audit` 不变
- `audit-result.schema.json` 通过 `additionalProperties: false` 控制；扩展字段需**同时更新 schema 和 validator**（P0 ✅）
- JSONL 日志结构不变（handoff 已规定不改目录层级）

### P0 已 commit 代码的命名校准（P1 第一个任务）

P0 `server/audit/contracts.py` 落地时定义了 `AmountPreCheck` 和 `ApprovalChain`，现边界校准后需重命名以反映真实职责（Python 只提取，不判断）：

| P0 已 commit 命名 | P1 重命名为 | 字段清理 |
|---|---|---|
| `AmountPreCheck` | `AmountExtraction` | 删除 `variance_pct` / `exceeds_pre_approval`（判断型） |
| `ApprovalChain` | `ApprovalSignatures` | 删除 `required_nodes` / `missing_nodes`（判断型），保留 `actual_signed` |
| `PreCheckResult.amount_check` | `.amount_extraction` | 类型随改 |
| `PreCheckResult.approval_chain` | `.approval_signatures` | 类型随改 |

P0 的 stub 均为 `None`，无调用方依赖这些字段，重命名风险低。P1 重命名 commit 前缀建议 `[audit-p1.0]`。

---

## 7. 回退策略

- 每一步都可独立回退：
  - `/audit/fast` 出错 → 调用方可降级回 `/audit`
  - `rules_loader` 异常 → 直接 manual_review + 告警
  - `extractor` 解析失败 → 跳过该附件，标记 `FileMeta.kind = "other"`，由 Claude 决定是否 manual_review
- 新老路径**并行运行至少 2 周**才下线老 `/audit`

---

## 8. 非目标

- ❌ 不引入向量检索 / RAG（规则库已结构化）
- ❌ 不做 OCR 厂商抽象（先用一家，够稳再抽象）
- ❌ 不改 `.claude/agents/` 和 `.claude/skills/` — 它们继续为老 `/audit` 路径服务
- ❌ 不改 JSONL 日志目录结构

---

## 9. 落地顺序

见 `.ai_state/todo-audit-refactor.md`。四周节奏：

| 周 | 阶段 | 核心交付 |
|---|---|---|
| 1 | P0 | 规则库初始化、受理预检、AuditContext 契约 |
| 2 | P1 | 资料数字化、规则预加载、金额预核、`/audit/fast` 端点 |
| 3 | P2 | manual_review_reason、风险聚合、历史摘要 |
| 4 | P3 | Skill 精简、跨域钩子（可选）、老 `/audit` 下线决策 |

---

## 10. 成功指标

- 一次审核对外 API 请求数：**5 → 1**
- p95 延迟：降低 ≥ 60%
- 成本：降低 ≥ 40%
- `manual_review` 原因可分类率：**100%**（强制 enum）
- 规则库覆盖度：`knowledge/expense/` 下 6 类规则全部非空
