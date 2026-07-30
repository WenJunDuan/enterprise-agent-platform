# Review Pass 3 — demo-full-doc-ocr

## Reviewer (代码层 findings)

### P0

- **F1 · 前端重造被后端阻断的排名语义**：后端已将 blocked 的
  `total_score/rank/recommended` 置空；`model.ts:424-453` 却补成 `0/index+1`，
  `model.ts:523-537` 再重排，卡片遂显示虚假 0 分和第 N 名，违反 KD4/AC6。

### P1

- **F2 · 图像校验 fail-open/Base64 内存风险**：`engine.py:324-340` 解析异常后继续 OCR；
  `read_bytes`、Base64 字符串和 JSON 请求体又造成多份驻留，压缩炸弹可绕过像素闸，违反 AC4a。

### 总评

**REWORK**：F1 是跨层正确性 P0，F2 是图像输入资源边界 P1；修复并补针对性测试后再审。

## Spec Compliance (spec-compliance, 2026-07-30)

### MISSING (做少了)

- **M1**：有 24 个真实 fixture 和 smoke 入口，但无本机 `run_smoke` 全格式 `status=ok` 记录，
  AC1a 尚未实证。
- **M3**：当前针对性 GREEN 已核对（后端 F1/F2：`8 passed`；前端 F3：`1 passed`），但三个反例
  均在 Pass1 finding 后才补，须记录当前 GREEN，并诚实保留“未先 RED”的过程偏差。

### CLOSED / 合理延后

- Pass2 F1-F3、M2 已关闭；AC5/8/9/10 合理 deferred 到 T6，ship 前仍须实跑。

### 总评

**REWORK**：M1/M3 仍使 AC1a/AC7 不可完整审计；T5 in_progress、T6 pending，Sisyphus 未完成。

## Evaluator

## VERDICT (evaluator, pass3)

**判定**: FAIL

### 评分依据 (4 维)

| 维度 | 得分 (0-5) | 说明 |
|---|---:|---|
| Functionality | 2.8 | F1 将 fail-close 结果重新显示成 0 分和名次 |
| Spec Compliance | 3.0 | M1 缺真实 smoke；M3 缺完整 TDD 审计链 |
| Craft | 3.3 | null 排名被强制收窄并二次派生 |
| Robustness | 2.7 | F2 fail-open，Base64 峰值无硬边界 |

总评: **3.0 / 5.0**

### 触发判定的关键 findings

- F1 (P0)：覆盖 blocked null 并重排；未修复 P0 触发 FAIL。
- F2 (P1)：解析异常继续 OCR，Base64 请求放大内存。
- M1/M3：真实 smoke 与完整审计链未闭环。

### 行动建议

- 立即修 F1；同轮修 F2。
- 复审前补本机 24 格式 smoke，并按 M3 落档，禁止补写历史 RED。
- T6 实跑 AC5/8/9/10。

### Sisyphus 完整性检查

- [ ] design.md 中所有 Task 完成（T5 in_progress，T6 pending）
- [ ] 所有 Task 验收标准过测试（F1/F2、M1/M3 未闭环）
- [ ] System 路径准备进入 polish stage（存在未修复 P0，不满足）

**next_action**: `rework_impl`
