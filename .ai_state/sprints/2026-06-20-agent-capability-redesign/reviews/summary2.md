# Review 汇总 · 第二批 G3/G0b/G1full/G2/G4/G5（交叉审查）

> 范围 `c9e09da..HEAD`。reviewer + spec-compliance 并行（read-only）。

## VERDICT: REWORK(条件) → 修复后 **PASS**

| 审查者 | 结论 | 要点 |
|---|---|---|
| reviewer | 健康，无 P0 | F1/F2/F3 P1、F4 P2，**全已修** |
| spec-compliance | REWORK(条件) | 主因 M1/D1：evidence_chain source 解析漏记 backlog → **已诚实补 backlog**；M2/D2 已澄清/修正 |

## findings 处置

| # | 级别 | 问题 | 处置 |
|---|---|---|---|
| F1 | P1 | override-result 未校验 human_verdict 枚举 | **已修**：非 approved/rejected/manual_review → typer.BadParameter |
| F2 | P1 | CreditApiSettings 默认 repr 泄露 CREDIT_API_KEY | **已修**：自定义 `__repr__` 掩码 `key='***'` |
| F3 | P1 | TaskStore `_SAFE_TABLE` 白名单无直接测试 | **已修**：新建 test_task_store.py（非法/大写表名→ValueError，合法→构造） |
| F4 | P2 | CREDIT_API_TIMEOUT_SECONDS float 无兜底 | **已修**：`_credit_timeout_seconds` 非法值兜底 10s |
| M1/D1 | spec | evidence_chain source 解析（design §脊椎一与 policy_refs 并列）未做且未记 backlog | **已修**：checklist g1_backlog 诚实记录（需 Python 知本案输入文件，架构张力，留 backlog） |
| M2 | spec | G4 schema 在 gitignored，git 不可验收 | **已修**：G4 加 verify 字段（验收=用户部署侧确认，非 git diff） |
| D2 | spec | G0b route 相似度 72%→实测 64% 高报 | **已修**：改 worker~78%/route~64% |
| D3 | spec | G1c 算术重算 deferred，design 未预告拆分 | 已并入 g1_backlog（诚实理由） |

## 收口

- 修复后 **287 passed / ruff clean / 6 分层守卫不退化**。expense/tender/ocr 真实路径零误伤（spec 确认）。
- 范围诚实性：spec 确认门控/gitignored/backlog 均未把「未完成」包装成 done。

## 本 sprint 总览（G0-G5 全部触达）

- **完整 done**：G0a 删死域、G0b 泛型化 store、G1(schema+policy+ref门控+scoring)、G2 plan 契约、G3 信用工具脚手架、G5 override 记录回路。
- **部分/门控/backlog（诚实）**：G1 evidence_chain 解析+算术重算（架构张力，backlog）、G3 流程内自动注入（鸡生蛋，backlog）、G4 schema 字段（gitignored，用户侧）、G4/G5 全自动闭环（跨 Python/Claude 边界，backlog）、worker/route 泛型化（backlog）。
