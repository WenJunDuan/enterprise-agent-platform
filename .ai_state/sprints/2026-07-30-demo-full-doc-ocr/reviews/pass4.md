# Review Pass 4 — demo-full-doc-ocr

## Reviewer (代码层 findings)

### P0

- 无。

### P1

- **F1 · 图像资源门禁未覆盖所有 OCR 后端**：`_read_image_with_resource_limits()` 仅在
  OpenAI-compatible 图像路径调用；`OCR_CLOUD=1` 直接进入云 job multipart，且
  `_post_multipart()` 再次 `read_bytes()`，显式本地 Paddle 路径也未统一经过字节、像素、magic
  门禁。攻击面和资源上限随运行参数变化，违反 AC4a 的统一 fail-close 边界。

### P2 / INFO

- 无新增阻塞项。

### 总评

**CONCERNS**：0 P0 / 1 P1。Pass3 F1/F2 的原始问题已关闭，但 F1 仍需在进入 polish 前统一修复并补
云、本地 Paddle 分支的回归测试。

## Spec Compliance (spec-compliance, 2026-07-30)

### MISSING / DEVIATED

- **D1 · 成品镜像证据脚本无法如实标记执行范围**：
  `scripts/smoke_document_formats.py` 与 `scripts/verify_office_macro_safety.py` 的
  `execution_scope` 写死为本机/要求在 T6 重跑；即使在 Debian ARM64 成品镜像执行，产物仍会声称
  需要在部署镜像重跑。T6 当前仍为 pending，脚本也无法产出可审计的 AC5/AC9 容器范围证据。
- **D2 · 宏安全证据与当前 fixture 不一致**：当前 `macro-on-open.odt` SHA-256 为
  `5f41578f38041ef7d38f861465b0bece957faccf12777fd1fc84688d8f7c9c9c`，已有证据 JSON 记录
  `2b1a14759e48c152b135949dfb9aabfad4cafe7356f91ca5bbbfb7d578af7635`；该证据不能证明当前 fixture
  的宏无副作用/无残留验收。

### CLOSED / 合理延后

- Pass3 M1/M3 已关闭：24 格式 smoke 与 RED/GREEN 过程记录已落档。
- AC5/AC8/AC9/AC10 随 T6 到演示环境实跑本身属合理 deferred；D1/D2 修复后才能形成可信证据。

### 总评

**REWORK**：D1/D2 使 AC3/AC5/AC9 的成品镜像证据链不可审计；T5 in_progress、T6 pending，
Sisyphus 尚未完整。

## Evaluator

## VERDICT (evaluator, pass4)

**判定**: REWORK

### 评分依据 (4 维)

| 维度 | 得分 (0-5) | 说明 |
|---|---:|---|
| Functionality | 3.8 | Pass3 功能阻塞已关闭，但 F1 令图像边界随 OCR 后端漂移 |
| Spec Compliance | 2.8 | D1/D2 使容器范围与宏安全证据不可采信 |
| Craft | 3.7 | 主路径实现与回归较完整，后端分支尚缺统一入口门禁 |
| Robustness | 2.9 | 云上传再次整文件读取，本地 Paddle/云路径未共用 fail-close 校验 |

总评: **3.3 / 5.0**

### 触发判定的关键 findings

- F1 (P1)：统一图像门禁未覆盖 `OCR_CLOUD=1` 和本地 Paddle，云 multipart 再次读取整文件。
- D1 (DEVIATED)：证据脚本执行范围写死，无法在 T6 产出如实的成品镜像证据。
- D2 (DEVIATED)：宏安全证据 SHA 与当前 fixture 不一致。

### 行动建议

- 必须立即修 F1：所有图像 OCR 后端在分派前共用一次 fail-close 门禁，并覆盖云/本地 Paddle 测试。
- 必须立即修 D1/D2：执行范围按实际宿主/显式验收 scope 生成，重跑当前宏 fixture 并校验 SHA。
- 修复后进行 Pass5；AC5/AC8/AC9/AC10 继续保留到 T6 演示环境实跑，不虚报完成。

### Sisyphus 完整性检查

- [ ] design.md 中所有 Task 完成（T5 in_progress，T6 pending）
- [ ] 所有 Task 验收标准过测试（F1、D1、D2 未闭环）
- [ ] System 路径准备进入 polish stage（Pass4 REWORK，不满足）

**next_action**: `rework_impl`
