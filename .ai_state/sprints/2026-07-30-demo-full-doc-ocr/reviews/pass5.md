# Pass 5 Review — 2026-07-30-demo-full-doc-ocr

## Reviewer (代码层 findings, pass5)

### F1 [P1] OpenAI-compatible 响应异常不能稳定进入 Tesseract fallback

- `server/ocr/engine.py:445-460` 将响应体按严格 UTF-8 解码，但捕获列表不含
  `UnicodeDecodeError`；非法 UTF-8 会越过 `OcrDependencyError` 退化边界。
- `message.content` 只做路径取值、不验证为字符串；实测 list 内容被原样返回，而上层切片后仍是
  list，不会触发当前仅捕获 `OcrDependencyError` 的 Tesseract fallback。
- 核验：构造 `content=["not-a-string"]` 得到 `list`；构造 `b"\xff"` 得到
  `UnicodeDecodeError` 且 `isinstance(exc, OcrDependencyError) == False`。
- 影响：远端返回结构漂移或编码异常时，AC4 的 outage fallback 不成立，扫描文件仍可能识别失败。

### F2 [P1] 成品镜像格式 smoke 未硬证明缓存隔离及 VLM/Tesseract 两条路径

- `scripts/smoke_document_formats.py:65-107` 直接以固定 purpose 调用 `extract_one`，未禁用/清空 OCR
  cache，也未断言 `from_cache=false`；已有缓存可让矩阵绕过成品镜像里的真实引擎。
- 脚本只执行一轮矩阵并记录当次 `engine/degraded`，没有分别对可达 VLM 与故意不可达 VLM 运行两轮，
  也没有 hard gate 断言至少一个真实 VLM 成功和至少一个真实 Tesseract degraded 成功。
- `deploy/TROUBLESHOOTING.md` 虽写明两条路径都必须证明，但 JSON gate 仅断言
  `payload["status"] == "ok"`，说明文字没有转成机器门禁。
- 影响：AC5/AC9 可能在 OCR 引擎未实际运行、或仅跑一条路径时被误报通过。

### F3 [P1] criteria 语义闸接受负数、NaN 与 Infinity 满分

- `server/tender/doc_pipeline.py:118-121` 将任意非 bool 的 `int/float` 视为合法数值，没有要求
  `math.isfinite(max_score)` 且 `max_score >= 0`。
- 该函数刻意不执行整份 jsonschema，因此 schema 的 `minimum: 0` 不能替代服务端承重闸。
- 核验：`criteria_looks_usable` 对 `max=-1`、`max=nan`、`max=inf` 均返回 `True`。
- 影响：非法满分可进入存储、汇总和 API，污染总分/排名，并可能产生非标准 JSON。

## Spec Compliance (spec-compliance, pass5)

### MISSING (做少了)

- 无新的实现缺失。AC5、AC8、AC9、AC10 属于 T6 的 Debian ARM64 成品镜像/部署验收，当前按设计
  defer；不能在 T6 完成前标为验收通过。

### EXTRA (做多了)

- 无不合理 scope creep。

### DEVIATED (做偏了)

#### D1 [P1] 两个展示组件仍自行重算分类满分，偏离 KD4 单一派生源

- design KD4 明确要求评分摘要由统一的 `knownMaxTotal / unknownMaxCount / maxTotal` 契约贯通，
  并禁止 `scoring-overview-panel.tsx`、`scoring-detail-table.tsx` 各自用 reduce 重新解释 null。
- `scoring-overview-panel.tsx:283-303` 的 `summarizeByCategory` 仍自行 reduce `item.max`；
  `scoring-detail-table.tsx:359-369` 的 `groupScoringItems` 也再次计算 `knownMax/unknownMaxCount/score`。
- 当前算法大体复刻 model 语义，但不是 design 要求的单一派生源；后续舍入、null 或分类规则变化会
  产生组件间漂移。

### 其他说明

- 其余实现未发现 MISSING；架构总入口及 `system-document-ingestion.md` 按 System 路径留到强制
  polish 更新，当前不记为缺失。
- Spec Compliance 总评：**REWORK**（D1 为明确 DEVIATED）。

## VERDICT (evaluator, pass5)

**判定**: REWORK

### 评分依据 (4 维)

| 维度 | 得分 (0-5) | 说明 |
|---|---:|---|
| Functionality | 3.4 | 主格式/OCR/criteria 路径已实现并有大规模回归，但 F1、F3 可直接破坏识别或评分语义，T6 尚未验收 |
| Spec Compliance | 3.3 | 多数 AC 已覆盖；D1 明确偏离 KD4，AC5/8/9/10 仍待目标镜像与部署实证 |
| Craft | 3.8 | 分层、边界测试和证据总体完整；F2 的 smoke hard gate 与前端派生复用仍不足 |
| Robustness | 2.8 | 响应类型/编码、非有限数值、缓存隔离和双 OCR 路径证明均存在真实边界缺口 |

总评: **3.3 / 5.0**

### 触发判定的关键 findings

- F1 (P1)：OpenAI-compatible 异常绕过 Tesseract fallback。
- F2 (P1)：部署 smoke 可命中缓存，且未硬证明 VLM/Tesseract 两轮。
- F3 (P1)：criteria 接受负数/NaN/Infinity。
- D1 (P1, DEVIATED)：评分组件仍各自重算摘要，违反 KD4 单一派生源。
- 三个以上 P1 已触发至少 CONCERNS；D1 是明确 design deviation，按 review 门禁升级为 REWORK。

### 行动建议

- 必须立即修：F1、F2、F3、D1；补对应 RED→GREEN 回归。
- 修复后创建全新的 Pass6 reviewer + spec-compliance + evaluator，不复用本轮审查者。
- Pass6 通过后进入 System 强制 polish，更新 cleanup、architecture 与 compound 文档；随后执行 T6。
- AC5/8/9/10 继续留给 T6 的 Debian ARM64 成品镜像和 demo 部署实证，不得提前宣称完成。

### Sisyphus 完整性检查

- [ ] design.md 中所有 Task 完成（T5 in_progress；T6 pending）
- [ ] 所有 Task 验收标准过测试（AC5/8/9/10 尚待 T6）
- [ ] (Refactor/System 路径) 准备进入 polish stage（需先闭环 F1-F3、D1 并通过 Pass6）
