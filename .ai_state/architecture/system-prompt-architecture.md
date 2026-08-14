# 提示词架构 · 热路径下沉 / 预算门禁 / 语义单源

> ⚠️ **已回滚（2026-08-14）**：本档描述的「骨架 + 5 references」结构因生产事故整体回滚——
> 内网小窗口模型（DeepSeek Flash）上 `Prompt is too long` 四次评标无结论。文件瘦身 68% 的同时
> 单会话累计注入反增 13.8%（26KB 搬进 references 后在会话中原样读回 + 多 5 个文件），本档下方
> 「预算门禁」的单文件字节判据被证明**方向性错误**。真因与教训见
> `compound/2026-08-14-learning-prompt-budget-must-be-per-session.md`。
>
> **当前现状**：`tender-evaluate.md` = 38,754B 单文件形态（回滚至 eac2a16 版）+ SKILL.md tag
> 语义内联恢复；5 个 references 成孤儿文件留作重设素材；KD2 schema 单源（output.py 惰性 loader）
> 与 KD4 调度表修正仍有效。**改 `/tender-evaluate` 规则直接改命令文件本体**，不要按下文的
> 骨架/references 判据放置。下文保留作历史设计参考——重设结构时判据必须先改为
> 「单会话累计注入字节 vs 部署最小窗口模型」再动手。

<details><summary>以下为 2026-08-13 原档（已回滚，仅作历史参考）</summary>

> 原现状档（2026-08-13，sprint `2026-08-12-prompt-architecture` merge 后）。

## 1. tender-evaluate 热路径结构（骨架 + 5 references）

```
.claude/commands/tender-evaluate.md   骨架 12,442B（界前 38,754B），上界 15,000B
  └─ 每步开头一条确定性 Read →
.claude/skills/tender-eval/references/
  ├─ s1-locate-criteria.md       1,629B  S1 定位优先级/关键排除/自检
  ├─ s1-criteria-structuring.md  9,204B  S1 criteria 字段定义、通则层法规 Read、护栏
  ├─ evidence-citation.md        2,813B  证据书写细则（S2 读一次，S3/S4 沿用不重读）
  ├─ s3-scoring-modes.md         9,796B  五种 score_mode 裁决细则 + pending_reason 速查
  ├─ s4-verdict-summary.md       8,501B  废标/资格 gate、一致性二分、verdict 合成
  └─ output-json.md              2,642B  manual_review_reason 枚举全文 + JSON 合法性
```

- **Read 位置是确定性的、每文件恰一次**：S1 读 2 档（locate + structuring）、S2 读
  evidence-citation、S3 读 s3-scoring-modes、S4 读 s4-verdict-summary、产出 JSON 前读
  output-json。共 6 条 Read 指令。不是「模型自己决定要不要读」——渐进披露靠位置固定保证命中率。
- **骨架只留**：目标句、硬门、决断总纲、Read 行。裁决细则一律在 references。
- **fail-visible 语义（骨架内一行，不可删）**：细则文件 `Read` 失败属部署缺陷，**不得静默续判**
  → 整单降 `manual_review`（`rule_gap`），`explanation` 写明「评分细则文件缺失，本单按骨架规则
  保守评定」。容器内 `.claude/` 随部署同步，Read 失败即部署异常，必须可见。

### 放哪儿（新增/修改评标规则时的判据）

| 内容 | 去向 |
|---|---|
| 硬门、步骤目标、决断总纲（一句话能说完的纪律） | 骨架 |
| 逐档次/逐取值/逐字段的裁决细则、枚举全文、示例 | 对应 references 档 |
| 跨步骤复用的书写口径 | 单独一档，在首次使用步骤 Read 一次 |

- 往骨架加内容前先查该节字节余量（下节）。**「执行方式+S0」节余量仅 4B**（实测 746 / 上界 750），
  实质等于冻结——要动该节文案必须先走预算表修订流程。
- 新增 reference 档单档 ≤10,240B；超了拆档，不是抬上界。

## 2. 提示词预算门禁（棘轮）

`tests/test_prompt_budget.py` 是唯一的机械闸，三条断言：

1. `PROMPT_BUDGETS` 逐文件字节上界（tender-evaluate 15,000 / tender-compare 8,200 /
   tender-extract-info 6,800 / audit 5,300 / CLAUDE.md 9,600）。
2. `skills/**/references/*.md` 单档 ≤ `REFERENCE_FILE_CAP`(10,240B) — **递归**匹配，
   子 skill 下沉档不能靠多挪一层目录绕过。
3. CLAUDE.md 调度表引用的实体名必须解析到真实 command/skill/agent（防悬空路由）；
   实体名从 frontmatter 边界（首个 `---` 到下一个 `---`）里取 `name:`，不是固定前 N 行。

**棘轮修订流程（唯一合法入口）**：
`design.md` 的逐节预算表改数 → 同步 `evidence/section_budget.py` 的 cap → 再改
`test_prompt_budget.py` 常量。**禁止就地抬 cap 了事**；PR 须写明理由。
超界的默认解法是**下沉细则到 references**，不是抬常量——否则命令会被"每出一次事故加一段"
重新撑回 38KB。

sprint 内的核对脚本（一次性证据，不是常驻闸）在
`.ai_state/sprints/2026-08-12-prompt-architecture/evidence/`：
`section_budget.py`（逐节 8 节）、`containment_check.py`（下沉零语义丢失，含 STALE_WHITELIST
反向失效检测）。逐节 cap 的权威副本在 design 预算表。

## 3. pending_reason 语义单源链路

```
.claude/contracts/common/audit-result.json   ← 权威（枚举定义在此）
        ↓ 惰性读取（首用加载 + 模块级缓存 _PENDING_REASONS）
server/tender/output.py::_verify_pending_reason
        ↓ 人读速查（非权威，标注"权威=schema"）
skills/tender-eval/references/s3-scoring-modes.md
        ↓ 注释指向
web 前端 tender-review/types.ts
```

- 改枚举**只改 schema**；output.py 不硬编码取值，s3 速查表与前端类型只是副本并显式标注权威出处。
- `_verify_pending_reason` 的 schema 加载点在「`scoring` 确认为 list」的早退之后：
  expense 等无评分路径不触发文件读。
- 调用次序硬约束：必须在 `_verify_score_mode_consistency` **之后**跑——后者会把无依据的 0 分降级
  为 `null` 并自行补枚举，先跑本闸会漏检这些服务端新造的 null。
- 覆盖测试：`tests/test_tender_pending_reason.py`(11) + `tests/test_tender_pending_reason_source.py`(3)，
  后者直测 schema→loader 的单源性（tamper schema 即应改变行为）。

## 4. skill 现状（KD4 清理后）

- 已删两个占位空壳 `skills/common/SKILL.md`(406B) / `skills/system/SKILL.md`(273B)——它们只是
  分组目录的空壳，构成路由假选项；**其下 7 个子 skill（common-* 5 个 / system-rule-init /
  system-memory-distill）有真实消费者，不得连带删除**。
- CLAUDE.md system 域调度入口写 `/init-rules`、`/distill-memory`（command），不再写空壳 skill 名。

## 遗留（部署机窗口）

runtime-verify 4 项待验（6 条 Read 各恰一次 / `validate_tender_result` 无重试 / turn 数 vs
`AUDIT_MAX_TURNS=30` / 撤 reference 须降 `manual_review(rule_gap)`）+ AC7 eval 基线 A/B。
明细见 `sprints/2026-08-12-prompt-architecture/evidence/runtime-verify-defer.md`。
</details>
