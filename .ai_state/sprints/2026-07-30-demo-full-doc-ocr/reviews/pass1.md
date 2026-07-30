# Review Pass 1 — demo-full-doc-ocr

## Reviewer (代码层 findings)

### P0

- **F1 · compare_worker 未逐投标人 fail-closed**：`collect_compare_input` 只从第一份
  `criteria_seen` 派生 `price_item`/`price_comparison_blocked`；若第一家价格满分为数值、第二家为
  `manual/null`，只会标记 `criteria_inconsistent`，仍允许价格横比与排名，违反 AC6/KD4。
- **F2 · criteria manual/null 结构闸接受缺失 tag**：`criteria_looks_usable` 使用
  `item.get("tag") != "scored"`，因此 `score_mode=manual,max=null` 且没有 `tag` 也会 ready；这弱于
  设计约定的显式非 scored tag，无法证明该项适合 unknown-max 语义。
- **F3 · 前端横比把部分未知分值折为 0**：`buildCompareRow` 只要数组中存在一个数值，就用
  `toNumber(value) ?? 0` 构造全部 cells；同一行另一投标人的 null 被展示为 0，违反 KD4/AC6 的
  “未设分值/待确认”保真要求。

### P1

- **F4 · 页级流已发出后缺 terminal error unit**：`extract_one` 在 `page_emitted=true` 后若后续页
  OCR 失败，最终 `kind=error` 不再触发文件级 error unit，消费者可能只看到若干成功页而不知道任务失败。
- **F5 · 页渲染超时不是可中断超时**：当前仅在 `get_pixmap/tobytes` 返回后比较耗时；渲染卡住时
  无法在 `OCR_PAGE_TIMEOUT_SEC` 到点终止，AC4a 的单页超时上限未真正成立。
- **F6 · 后端上传边界未执行 manifest 后缀/magic 校验**：上传物化层只做文件名清理与字节上限，
  未拒绝清单外后缀，也没有按声明类型校验文件 magic；前端 accept 不是安全或契约边界。
- **F7 · AC1a/AC3 的真实验证不足**：现有测试证明清单形状、生成物和 Dockerfile 文本，但没有对
  清单每个后缀执行“上传→分类→native/convert/OCR→非空底稿”；LibreOffice 也以 fake process 为主，
  未证明真实转换、宏无副作用、TERM→KILL 后无残留及并发上限。

### P2 / INFO

- 已完成的 native 格式分流、VLM→Tesseract 基本续跑、缓存降级标识、双 Containerfile 依赖声明与
  前端大部分 null 展示语义方向正确；这些不足以抵消上述承重路径缺陷。

## Spec Compliance (spec-compliance, 2026-07-30)

### MISSING (做少了)

- AC1a：缺清单逐后缀的真实非空底稿矩阵；上传端也缺 manifest 后缀/magic 契约测试。
- AC3：缺宏副作用、强制 KILL、子孙/残留进程、真实并发闸与槽释放的完整测试。
- AC4/AC4b：缺图片 VLM→Tesseract fallback、锁外网络/进程/回调的显式联合断言，以及降级不缓存后
  远端恢复重新调用 VLM 的联合回归。
- AC6：虽有 9 项对象级和前端派生测试，但缺 prompt/schema→存储/API→前端的真实 7 numeric +
  2 manual/null 往返，并缺“第二家 null 价格项”横比门禁测试。
- KD6/部署教训：`deploy/TROUBLESHOOTING.md` 尚未修改，部署/回滚/配置保留经验未形成 runbook。

### EXTRA (做多了)

- 未发现需要回退的明显 scope creep；`server/platform/config.py` 的上传上限和相关展示组件调整属于
  本次格式/OCR/null 契约的合理配套。

### DEVIATED (做偏了)

- F1/F2/F3 使 criteria null 的后端准入、横比门禁和前端展示三处偏离 KD4/AC6。
- F4/F5/F6 使流式终态、超时硬边界和上传信任边界偏离 KD2/KD3/AC1a/AC4a。

### 尚待部署阶段验证

- AC5、AC8、AC8a、AC9、AC10 必须在 ARM64 demo 构建/部署阶段完成；当前留待 T6 合理，但在取得
  镜像 import/smoke、目标配置零漂移、格式实跑、导出 SHA/可加载证据前不得 ship。

### 总评

**REWORK**：实现面存在 MISSING/DEVIATED，且 checklist 中 T5 仍 in_progress、T6 仍 pending。

## Evaluator

## VERDICT (evaluator, pass1)

**判定**: FAIL

### 评分依据 (4 维)

| 维度 | 得分 (0-5) | 说明 |
|---|---:|---|
| Functionality | 2.4 | 多格式/OCR 主骨架已实现，但 F1/F3 可产出错误横比语义，F4/F5 破坏失败终态与超时保证 |
| Spec Compliance | 2.1 | AC1a/AC3/AC4b/AC6 有关键缺口，部署 runbook 与远端验收尚未完成 |
| Craft | 3.1 | 分层和命名总体清楚、测试量可观，但 F1/F2/F3 是跨层契约未收口，关键测试未覆盖反例 |
| Robustness | 1.9 | 上传信任边界、可中断超时、流式终态及多投标人 fail-closed 均不完整 |

总评: **2.4 / 5.0**

### 触发判定的关键 findings

- F1 (P0)：只检查首份 criteria，后续 manual/null 价格项仍可能参与横比 → 触发 FAIL。
- F2 (P0)：缺 tag 的 manual/null 被错误准入 ready → 触发 FAIL。
- F3 (P0)：部分 null 横比分值被折为 0 → 触发 FAIL。
- F4-F7 (P1)：流式错误终态、硬超时、上传边界和真实验收证据不足，进一步确认不可进入 polish/ship。

### 行动建议

- 必须立即修：F1、F2、F3，并先补对应失败测试（第二家 null 价格项、缺 tag、混合 null cell）。
- 同轮 rework 修：F4、F5、F6；补齐 F7 所列 AC1a/AC3/AC4b/AC6 回归与真实 smoke。
- re-review PASS 后方可进入 polish；随后完成架构档、`deploy/TROUBLESHOOTING.md` 和 T6 远端验收。

### Sisyphus 完整性检查

- [ ] design.md 中所有 Task 完成（T5 in_progress，T6 pending）
- [ ] 所有 Task 验收标准过测试（AC1a/AC3/AC4b/AC6 证据不完整）
- [ ] System 路径准备进入 polish stage（P0 未清零，不满足）

**next_action**: `rework_impl`；修复 P0/P1 并补足缺失验收后生成 `reviews/pass2.md` 复审。
