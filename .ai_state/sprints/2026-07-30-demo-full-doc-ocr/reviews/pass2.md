# Review Pass 2 — demo-full-doc-ocr

## Reviewer (代码层 findings)

### P0

- **F1 · 页像素上限在分配后检查**：`page_render_worker.py` 先调用 `get_pixmap()`，再计算并校验
  `OCR_MAX_PAGE_PIXELS`；畸形或超大页面会在拒绝前完成高内存分配，违背 AC4a 的资源硬边界。

### P1

- **F2 · 成品镜像无法执行 runbook smoke**：两个后端 Dockerfile 均未 `COPY scripts/`，同步清单也
  未包含该目录；runbook 的 smoke 管道缺 `pipefail` 或显式退出码检查，失败可能被 `tee` 掩盖。

### P2

- **F3 · framed 渲染协议未 fail-fast**：父进程未校验 page frame 的 `type == "page"`，且在读取
  payload 前未验证 `1 <= length <= remaining_bytes`，异常长度可能造成无意义等待或超预算读取。

### 总评

**REWORK**：Pass1 F1-F6 的行为修复方向已关闭，但 F1 是新的未修复 P0；F2/F3 亦需在复审前收口。

## Spec Compliance (spec-compliance, 2026-07-30)

### MISSING (做少了)

- **M1 · 真实 canonical fixture 矩阵证据缺失**：已有 smoke 入口，但尚无全部 canonical 后缀经
  上传校验→分类→native/convert/OCR→非空底稿的实际执行记录。
- **M2 · LibreOffice 宏安全实证缺失**：尚无真实含宏 fixture 的“宏无副作用、无子孙/残留进程、
  临时 profile 清理”执行证据。
- **M3 · Pass1 RED→GREEN 审计链不完整**：checklist 记录了测试标识，但未落档 F1-F6 对应的失败输出、
  修复提交/变更点和同一回归转绿结果，AC7 尚不可审计复核。

### 总评

**REWORK**：AC1a、AC3、AC7 仍缺可复核证据；T5 仍 in_progress、T6 仍 pending，尚不可 ship。

## Evaluator

## VERDICT (evaluator, pass2)

**判定**: FAIL

### 评分依据 (4 维)

| 维度 | 得分 (0-5) | 说明 |
|---|---:|---|
| Functionality | 3.5 | 主格式/OCR/criteria 路径已有完整实现和全量回归，但 F1 使超大 PDF 页资源门禁失效 |
| Spec Compliance | 2.6 | M1-M3 导致 AC1a/AC3/AC7 缺少真实、可审计验收证据，T5/T6 未完成 |
| Craft | 3.6 | 模块分层和测试基线良好；镜像 smoke 可达性与 framed 协议校验尚未闭环 |
| Robustness | 2.4 | F1 可在拒绝前触发高内存分配，F3 对恶意/损坏 frame 未 fail-fast |

总评: **3.0 / 5.0**

### 触发判定的关键 findings

- F1 (P0)：像素限额在 `get_pixmap()` 分配后才检查，未修复 P0 按规则触发 FAIL。
- F2 (P1)：成品镜像缺 smoke scripts，且管道可能掩盖失败，阻断可部署验收。
- F3 (P2)：frame type/length 缺少读取前校验，需在同轮 rework 收口。
- M1-M3：真实格式矩阵、宏无副作用/无残留、Pass1 RED→GREEN 证据均缺失。

### 行动建议

- 必须立即修：F1，并补“超大页面不调用 `get_pixmap`”的先红后绿测试。
- 同轮修：F2、F3；把 smoke scripts 纳入镜像/同步清单并确保管道传播失败退出码。
- 复审前补齐：M1-M3 的真实执行日志、fixture 来源/许可和可审计 RED→GREEN 记录。

### Sisyphus 完整性检查

- [ ] design.md 中所有 Task 完成（T5 in_progress，T6 pending）
- [ ] 所有 Task 验收标准过测试（AC1a/AC3/AC7 实证缺失）
- [ ] System 路径准备进入 polish stage（未修复 P0，不满足）

**next_action**: `rework_impl`；关闭 F1-F3 并补齐 M1-M3 证据后执行 Pass3。
