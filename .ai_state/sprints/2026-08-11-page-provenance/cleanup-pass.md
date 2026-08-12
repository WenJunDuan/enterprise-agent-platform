---
sprint_slug: "2026-08-11-page-provenance"
created: "2026-08-12"
path: "System"
polish_worker: "polish_worker subagent (worktree agent-ad32a594fad71cd9a)"
program: "2026-08-11-tender-eval-hardening (H2)"
---

# Cleanup Pass — 2026-08-11-page-provenance (H2)

> 范围 = 本 sprint review 已确认的 P2 清单，逐项闭环。全量回归与基线逐条一致（见文末）。

## 已执行

### F7 — `summary["page_mismatch"]` 语义漂移 → 正名 `page_mismatch_detected`

`server/tender/evidence.py:_annotate_page` 在 `page_status` 刚返回 `page_mismatch` 时就计数，
但**这一档没有终态**：紧随其后每条都会被纠正成 `page_corrected`、或降级成 `page_unverified`
（页号不可靠文件 / 多处命中 / 定位不到唯一页）。旧键名 `page_mismatch` 读起来像"仍有 N 条错页
未处理"，实际与 `page_corrected + page_unverified` 重叠计数。

**处置**：键名改 `page_mismatch_detected`（"检出数"而非"终态数"），初始化处与递增处各加一行
说明。**不删该计数**——它是"回查闸到底纠了多少页"的唯一可观测量。
**未按"只在终态计数"改**：终态 `page_mismatch` 在当前分支结构下不可达，那样改等于永久写 0，
比语义漂移更坏（一个恒 0 的对外字段）。核实过 `extracted_data.evidence_resolution` 无
后端 / 前端 / 契约 / 测试消费者，改键名安全。

### F8 — 两处形态问题

1. **`pipeline._render_body` 兼容别名删除**。渲染实现早已搬到 `server/ocr/draft_render.py`，
   别名只服务存量引用。删别名 + 生产调用改直引 `render_body`；6 个测试文件改引
   `draft_render.render_body`；`server/ocr/{classify,native,boq,engine}.py` 与若干测试注释里的
   旧符号名一并更正（留着就是指向不存在符号的注释）。
2. **`corpus.split_head_tail_on_anchors` 的 `for reserve in (0, None)` 双轮循环展开**。
   循环变量只当"这是第几轮"用，第二轮在不需要重放锚时与第一轮同参、结果必然相同。
   抽 `_locate_tail(text, head_cut, anchors, budget)`，主函数写成"先定位一次求重放锚，
   需要时扣掉锚占位再定位一次"，收敛性写在注释里。`tail_n <= 0` 的早退提到循环外。

### N2 — `server/stores/rag_store.py:ensure_schema` docstring

补一行前提：本表仅用于 `:memory:` 连接，改持久化后列增删必须 drop + rebuild
（FTS5 虚拟表不支持 `ALTER TABLE`，老库会带旧列静默存活）。

### N3 — `.claude/skills/ocr-page/SKILL.md` 结构

「转换稿文件」整节原插在「读输出」列表中间，把 `- [错误] …` 这一项与它所属的列表切断。
该节整体后移到 `- [错误]` 项之后，两节各自完整。

commit `2f0d2b8`（含 F7/F8/N2/N3）。

## 已 defer（本轮不做，理由如下）

- **第二条 golden 用例**：需要一份新的真实标书底稿做 fixture（含转换稿锚 + 页号存疑文件），
  取材与脱敏成本远超 polish 窗口，且属于**新增覆盖**而非清理既有代码。留 backlog。

## 5 检查项结论（本 sprint diff 范围）

1. **临时代码 / 调试痕迹**：无。
2. **注释完整性**：新增 `_locate_tail` 带完整 Args/Returns；`ensure_schema` 补前提；
   所有指向已删符号的注释已更正。
3. **冗余 / 重复**：删掉一个纯转发别名；双轮循环合并为单一定位原语。
4. **低效模式**：`_locate_tail` 第二趟只在需要重放锚时才跑，比原来无条件跑两轮略省。
5. **过度设计**：`_locate_tail` 有两个真实调用点（同一函数内两趟），不是预留抽象；
   未新增配置项 / 分支。

## VERDICT

**PASS** — F7/F8/N2/N3 闭环，第二 golden 显式 defer。
