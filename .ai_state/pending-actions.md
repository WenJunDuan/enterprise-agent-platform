# 待办 / 未完成动作

> 跨会话悬挂动作清单。新会话起手扫一眼。完成后从此处划掉。

## 🔴 安全（运维侧手动，代码侧已尽）

- [ ] **轮换 litellm 后端 key** —— `deploy/prod/litellm_config.yaml` 的旧 key `sk-hATxkq…`
      **仍在 git 历史里**（已 gitignore 真实文件 + 提供 .example 占位，但 gitignore 抹不掉历史）。
      需在 Qwen 后端轮换该 key。仅运维可做。来源 commit `7664697`、`.ai_state/sessions/2026-06-19-codex-review.md`。

## 🟡 用户侧 TODO（agent-capability-redesign 脚手架已就位，填值即用）

- [ ] **G3 企业信用 API**：拿到接口后，在 `enterprise-agent.env`（模板 `enterprise-agent.env.example`）填
      `CREDIT_API_URL` + `CREDIT_API_KEY`。代码已全做好；`python -m server.cli credit-check <企业名>` 自检。
      未填时 `requires_external_data`（企业信用）项保持 `manual_review`（人工）= 设计上正确行为。
- [ ] **G4 记忆 schema（部署侧，gitignored 不入库）**：改 `knowledge/_schema/case-memory.schema.json`：
      ① `domain` enum `["expense","hr","legal"]` → `["expense","tender","ocr"]`（去死域 + 加 tender，修 round4 F12）；
      ② 加字段 `valid_until` / `superseded_by` / `decided_under_rule_version`（支撑 memory-query SKILL 的复检/衰减/陈旧）。

## 🟢 代码 backlog（agent-capability-redesign 诚实延后，有架构约束）

> 详见 `sprints/2026-06-20-agent-capability-redesign/checklist.yaml` 的 backlog/deferred 字段。

- [ ] **evidence_chain source 解析 + 算术「重算」**（G1 深化）：需 Python 拿到本案输入文件清单/确定性数，
      撞 gotcha「审核判断在 Claude 侧、Python 不判断」——是真实架构张力，开工前先定「Python 做多深验证」。
- [ ] **worker/route 层泛型化**（G0b 续）：audit/tender 的 worker(~78%)/route(~64%) 仍有重复；域差异比 store 多，ROI 低。
- [ ] **G3 评标流程内自动注入信用**：投标人企业名在命令执行中途才抽出（鸡生蛋），需两遍流程或把工具暴露成 Claude skill。
- [ ] **G4/G5 全自动闭环**：distill 自动读 `override_store.list_pending_overrides()` → 写案例记忆 → `mark_distilled`；
      跨 Python/Claude 边界 + gitignored memory，需导出/呈现机制。

## ⚪ 低优先（暂留，已记理由）

- [ ] 存储测试 hermetic 化（旧 store 单例 import 期捕获 db_path，需重构；现 gitignore+随机 id 风险低）。
- [ ] 日志按天滚动 toggle（如需，现 size+gz）。
- [ ] `config.contract_max_retry` 命名：删 legal 后语义偏（实为通用 JSON 重试计数），下个 refactor 改 `json_parse_max_retry`（round4 review F4）。
