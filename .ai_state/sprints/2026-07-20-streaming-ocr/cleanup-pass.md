# D9 streaming-ocr · Polish / Cleanup Pass

> stage=polish · 2026-07-20 · System 路径强制 polish（skip_polish=false）
> 输入：review pass2 的 2 个 P2 + doc-style/security-checklist 扫描。

## 处理项

### P2-a [已修] `_extract_one_raw` docstring 过时
`server/ocr/pipeline.py:407-415` 原描述「native pdf_text 走 buffer-then-fire（页结果在 FITZ_LOCK 内收集锁外回放）」——F1 修复后 native pdf_text 改为**读后从最终 blocks 发**（`_dispatch_native_pdf_text`→`_emit_pages_from_blocks`），buffer-then-fire 仅存于 OCR 侧 paddle pipeline。docstring 已重写为准确的三分支描述（native 读后发 / OCR buffer-then-fire / 文件级兜底）。35 ocr 测试零破坏。

### P2-b [defer，文档化] `native.read_pdf_text` 的 on_page 被生产路径旁路
F1 修复后 `_dispatch_extract` 恒以 `_call_native_read(path, None)` 调用 → `read_pdf_text` 的 `on_page` 参数 + buffer-then-fire 逻辑在**生产路径不再被触达**，仅 T1 单测（`test_read_pdf_text_on_page_*`）为真实调用方。
**决定：保留，不删**。理由：
1. 有测试覆盖、无害（死路径不参与生产控制流，零运行时成本）。
2. 它是 critic round1 F2「回调锁外触发」的原始 buffer-then-fire 安全实现；若未来对超大 native PDF 重启「边读边流」（read-then-emit 对数千页 BOQ 有内存/时延权衡），此能力可直接复用，删了要重加。
3. 移除会级联触及 `native_read`/`_call_native_read` 的 on_page 分支 + 2 个测试（~30 行），收益（消 6 行死参数）不抵重构面与回归风险，polish 不宜过度重构。
→ 记入 backlog：**「native streaming 二期」触发时一并决定 read_pdf_text.on_page 去留**（与「识别-评标流水线重叠」流式二期同批评估）。符合反过度工程「无现实需求不重构、但保留有明确近未来用途的已测能力」的双向判据。

## 扫描结果（无 finding）
- **security-checklist**：新增 `ocr_jobs.py`/`ocr_job_worker.py`/`ocr_job_store.py` 无硬编码密钥/token；无 console/print 泄漏；路径服务端派生禁客户端传入（G2②）；multipart 复用 sanitize_upload_name+validate_upload_bytes 先例；SQL 参数化+表名白名单。
- **doc-style**：公开端点/worker 有 docstring；无裸 TODO/FIXME（无 issue 号）；无注释掉的代码块；无过长行尾注释。
- **前端**：Tabs 双模式，四态显式（loading/partial/success/error），null/404 终态停轮询，reducer 跨模式隔离——ui-guidelines 状态可见性满足。

## 架构档
`architecture/ARCHITECTURE.md` 已新增「OCR 流式任务层（D9）」条目（/ocr/jobs + worker + ocr_jobs 独立表 + units.jsonl 边车 + 回调接缝 + 前端双模式）。ocr 单向服务层约束不变。

## 结论
2 个 P2 处理完毕（P2-a 修、P2-b 文档化 defer）；security/doc 扫描净。全量回归 955 passed/2 skip、ruff 净（P2-a 后复跑）。polish 完成 → 下一步 runtime-verify（实跑 /ocr/jobs + 前端点击流，需起服务，待用户定本机 vs 部署机）→ ship 契约。
