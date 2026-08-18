# Phase 0 施工中发现、但落在改动范围白名单之外的问题

> 纪律（施工文档第九节 #2）：白名单外的问题记在这里，不顺手改。
> 记录者：generator subagent（worktree agent-acc11005cf027e330），2026-08-18。
>
> **裁决记录（纠偏令 v2 二节，2026-08-18，用户已定）**：
> P1#1 批准偏离（sha256+bytes+pages 指纹），design AC1 措辞已回改；
> P1#2 授权纯搬运拆分 `eval/regression.py`，白名单追加该文件；
> P1#3 清理——真实编号/金额改合成值 + 评估守卫编号正则；
> （落库项）v1+v2 已提交 `.ai_state/claude/`。P2 两条未裁决，维持记录。

## P1 · design 的 AC1 与 AC2 互斥，已按 AC2 施工

design 要求 `corpus.pointer.yaml` 记「相对 `knowledge/external/` 的路径 + sha256 + 页数」，
同时要求它通过扩面后的 `tests/test_no_real_corpus.py`。**两者不可同时成立**：该语料的目录名与
文件名本身就是真实机构名，写进仓库既违反匿名化纪律，也直接被守卫的 `[一-龥]{2,8}学院`
形态命中。

已采取：pointer **不记路径**，改记 `sha256 + bytes + pages`，运行时在 `--corpus-root` 下
按字节数预筛再算哈希定位。它严格强于路径（改名/挪目录仍能定位；语料被换则显式报错）。
需主会话确认此偏离，并在 design 侧订正 AC1 的措辞。

## P1 · 脚本 1,080 行，超 coding-standards P0 的「文件 > 300 行必须拆分」

`scripts/eval_tender_regression.py` 内含五块内容：YAML 子集解析（无 PyYAML 又不准引新依赖）、
case 定义与校验、语料指纹定位、四指标判定、HTTP 驱动与报告。合理的切法是把纯逻辑下沉成
`eval/regression.py`，脚本只剩 CLI —— 但那需要白名单外的第 4 个源文件，故本轮未做。

两点上下文：design 自身的白名单写的是「新增 `eval/`」（整个目录），主会话下发时收窄成了
两个 yaml；且本仓既有模块普遍在 500–970 行同一注释密度（`server/ocr/engine.py` 970、
`server/tender/output.py` 717）。建议由主会话裁决：放行，或授权补一个 `eval/regression.py`
做纯搬运式拆分（有测试兜底，零行为变更）。

**追记（2026-08-18 晚，已执行）**：v2 授权后由 generator（worktree agent-aaae2a4d35e31495e）
纯搬运完成，commit `b3f3bb8` ff-merge 进 main；脚本 1,080 → 381 行，证据见 tdd-evidence T6。
**残留**：`eval/regression.py` 822 行仍超 300 行 P0 线——本次授权只到纯搬运，再切分是新的
决策；若下刀，generator 勘察给出的自然切线是 YAML 子集解析器（约 135 行，无业务耦合，
可独立成 `eval/yaml_subset.py`）与四指标判定分家。

## P1 · 存量真实语料残留：真实项目编号在测试 fixture 里（守卫抓不到的形态）

`tests/test_legacy_doc_table_recovery.py:43` 的 fixture 字符串里，**项目编号与预算金额
两项都是本 case 真实标书的原始值**（与 2026-08-17 参照实跑报告基本信息表逐字符相同）。
来源 commit `1a52e92`（2026-08-17，非本 sprint 引入）。

此处刻意不复制那两个串——把要清除的东西抄进状态档等于又写回一份（`.ai_state/` 同样入库）。
复核方式：拿参照报告基本信息表里的「项目编号」值去 grep `tests/`。

`test_no_real_corpus.py` 抓不到它——守卫只按「汉字 + 机构性后缀」的形态抓，项目编号与金额
在形态上与合成数据不可分（守卫 docstring 已自陈这个边界）。发现方式是我按参照报告里的
具体串反查，不是守卫。

建议：改成合成编号与合成金额（保住"字母-数字段"的结构性质即可），并在 compound 里记一条
「形态守卫抓不到编号类标识」的补充。**不在本轮白名单内，未改。**

**追记（2026-08-18 晚，已执行）**：fixture 两值已改合成（编号保住「字母段-6位数字段」结构，
DEMO 前缀明示虚构；合成编号故意落守卫网内并加白，验证守卫真实生效）。守卫新增编号形态
正则 `[A-Z]{2,6}-?\d{5,}`：选形依实测——5 位以上数字段全仓仅 2 命中（判别力足），4 位数字段
形态 19 串全为合成值或标准号（年份 / ISO9001 / `XX-2026-001` 本仓 mock 惯用形态），纳入
只添加白扰动，刻意不进网。金额类纯数字守卫覆盖不到 → 守卫文件头部已补人工纪律注释。
真红→绿证据见 tdd-evidence T7（red 精准命中本条所指的那处真实编号）。

## P2 · 仓内已有一套 golden-case 评测，design 的「已调研的现成方案」表未提及

`server/tender/eval.py` + `tests/eval_fixtures/tender/golden_manifest.json` 是既有的评标
golden 回归（in-process 跑 runner，比对 verdict / eligibility / scoring + repeat-N 一致性极差）。
它与本次的 HTTP 端到端四指标闸目标不同（那套测决策漂移，这套测准不准 + 墙钟），但
design 的调研表只列了 promptfoo / deepeval / ragas 与 pytest 参数化，**没有列仓内既有件**——
「造轮子前先调研现成方案」的检索面漏了自家仓库。

后果目前只是两套评测并存、各有 README，不构成阻塞。但 Phase 2 之后应明确二者分工，
否则会出现「改了 A 套的期望、B 套还在按旧期望绿」的双真相。

## P2 · `tests/eval_fixtures/tender/README.md` 记的硬门锁定 checklist 仍未完成

该 README 写明「跨次一致性阈值首版是警告模式，硬门锁定是 D4（L2 多模型路由）开工的前置
条件」。D4 相关工作已经在做（`2026-08-14-l2-model-routing` sprint 已存在），但该硬门似乎
仍是警告模式。本轮未核实其现状，仅记录线索。
