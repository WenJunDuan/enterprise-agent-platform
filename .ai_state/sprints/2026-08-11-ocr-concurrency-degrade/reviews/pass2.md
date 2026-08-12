# Review Pass 2 — 2026-08-11-ocr-concurrency-degrade (H3)

审对象：返工 4 commits（8817ca9/831a7cb/2a4b41b/c560144，14 文件 +682/-169）。
reviewer 实测：ruff 净；关键测试 110 passed（14 failed 均为 worktree venv 缺 fitz 的既有失败面）。

## pass1 核验

CLOSED：F1（重试预算真收敛+断言有鉴别力，Tesseract 路径无影响）、F2（ticker 先于信号量+首 touch
立即+排队测试必红鉴别、无泄漏）、F4（ValueError 重抛成对测试防反向漂移）、F5（编排归位
prewarm_scheduler，doc_pipeline 489）、F6（problem_files 保序去重+穿透接缝测试确认没绕）、
F8、F9（残留仅测试 docstring 一处，归 polish）、evidence 口径（16+7 构成如实转录）。
NOT_CLOSED：F3（预算与去重成立，但恢复路径引入 N1/N2）、spec-D2（形式闭合行为未闭合，见 N3）。

## pass2 新增 findings

- **N1 [P0] 补跑失败覆写可用底稿为 NULL**（doc_layer.py:293-295 + doc_pipeline 失败分支
  `update_*_doc_ocr(ocr_text=None, status="failed")` 无条件 SET）：`_rerun()` 内部吞异常正常返回
  → restore 不执行 → degraded 底稿被清空、评标退回 inline 全量重 OCR，inline 再失败证据归零。
  与 :249-252 docstring 自述不变量直接矛盾。修法：重跑前快照 text+status，结束后仅在不劣于旧值
  时保留否则连 text 回滚；补"重跑失败后 text 与 status 均为重跑前值"测试。
- **N2 [P1] 部分成功+部分超时回滚过宽**（doc_layer.py:286-311）：project 已 ready、bid 超时 →
  project 被无条件刷回 degraded。修法：逐段完成标记，只回滚未完成段。
- **N3 [P1] spent_sec 无生产调用方**：唯一该非零的场景（等待之后的补跑）仍按 0 算，D2 没真堵住，
  参数落反过度工程过度侧。修法（取 a）：wait_doc_layer_ready 记 t0，实测 elapsed 透传
  rerun_budget_sec；补"等满上限后补跑预算显著收缩"测试。
- **N4 [P1→评估可升 P0] doc_layer.py 新建文件 361>300 硬线**：新文件无基线借口，且读层/补跑写层
  两职责混居。修法：补跑四函数（约 90 行）拆 server/tender/doc_rerun.py，读层回 ~270，
  也为 N1/N2 修复留空间。**不按迁移期豁免放行**。
- N5 [P2] pipeline.py 净增 61 超上界 1 行：压 docstring 1 行机械闭合，不开豁免先例。
- N6 [P2] restore 自身失败 → 行永久卡 running，前端轮询不终止（pass1-F1 锁死形态的另一入口，
  进程重启中断补跑同形态）：至少补 restore 路径断言测试；读层/前端把陈旧 running 视作可终止态
  另议。
- N7 [P2] 补跑超时后信号量归还但线程仍在跑，闸短暂超额（design 非目标的已知边界，第一条常态
  触发路径）：TROUBLESHOOTING 记一句话。
- N8 [INFO] ocr_failed_files 列语义已扩为"失败+降级"，列名不改，记录防误解。

## 定向核验（主 agent 点名）

ticker 无泄漏；mark_doc_rerunning×touch WHERE 交互为正向修复（副作用即 N6）；budget_sec 不影响
Tesseract 路径。

## 结论

pass1 十项中八项 CLOSED；F3/D2 的收口在 pass2 引入 N1(P0)/N2/N3，另有 N4 行数硬线。
需 pass3 返工（N1-N5 必修 + N6 测试 + N7 一句话），evaluator 待 pass3。
