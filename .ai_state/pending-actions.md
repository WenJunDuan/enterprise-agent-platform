# 待办 / 未完成动作

> 跨会话悬挂动作清单。新会话起手扫一眼。完成后从此处划掉。

## 🔴 安全（运维侧手动，代码侧已尽）

- [ ] **轮换 litellm 后端 key** —— `deploy/prod/litellm_config.yaml` 的旧 key `sk-hATxkq…`
      **仍在 git 历史里**（已 gitignore 真实文件 + 提供 .example 占位，但 gitignore 抹不掉历史）。
      需在 Qwen 后端轮换该 key。仅运维可做。来源 commit `7664697`、`.ai_state/sessions/2026-06-19-codex-review.md`。

## 🟡 功能（待开工）

- [ ] **合同库实现**（随合同审计开工）—— `data/contracts/<id>/`（source/clauses/payment_nodes/meta）
      持久库 + `stores/contract_store.py` + 结论 evidence_chain 回链 contract_id。
      设计就绪：`.ai_state/sprints/2026-06-19-logging-and-storage/design-data-storage.md §C`。

## ⚪ 低优先（暂留，已记理由）

- [ ] 存储测试 hermetic 化（旧 store 单例 import 期捕获 db_path，需重构；现 gitignore+随机 id 风险低）。
- [ ] 日志按天滚动 toggle（如需，现 size+gz）。
