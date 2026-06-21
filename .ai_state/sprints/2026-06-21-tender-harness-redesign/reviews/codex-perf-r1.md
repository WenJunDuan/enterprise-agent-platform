# Codex 性能 review · OCR 并行+缓存+线程安全（r1）

> reviewer: codex exec review。对象:extract_dir 并行 + fitz 锁 + cache.py。178k tokens。
> **VERDICT: REWORK → 已全修**

## P1（全修）
- **P1-1 fitz 锁不全**:`_FITZ_LOCK` 只覆盖 native.read_pdf_text,但 engine `_render_pdf_pages` 渲染扫描 PDF 也调 `fitz.open()` 并发 → 崩。**修**:抽出共享 `server/ocr/locks.py` 的 `FITZ_LOCK`,native 直读 + engine 渲染共用同一把锁。
- **P1-2 缓存 key 缺指纹**:key 只含 content+purpose+seal,换 OCR 后端/模型会复用旧缓存。**修**:`_engine_fingerprint`(cache version+OCR_CLOUD+model+pipeline) 进 key。
- **P1-3 put_cached 窄 catch 会 abort**:只 catch OSError,但 json.dump 对 Paddle layout 抛 TypeError → ThreadPoolExecutor.map 重抛 abort 整批。**修**:catch 宽异常 + 清临时文件 + 总返回结果。+测试。
- **P1-4 本地 paddle 并发无锁**:本地 PaddleOCR/seal 并发 predict OOM/GPU race。**修**:`PADDLE_LOCK` 串行化本地 pipeline + 印章。

## P2
- **P2-5 workers 未校验**(已修):`_ocr_max_workers` 防御解析 + clamp ≥1。+测试。
- **P2-9 read_excel 句柄泄漏**(已修):try/finally close。
- **P2-10 测试缺口**(已修):+写失败不 abort、run_seal key 分离、workers clamp 测试。

## P2 backlog（更大改造，不阻塞实测，留后续轮）
- **P2-6** 全局 OCR 信号量(跨请求)+ 云 429/5xx 重试 backoff(现并发只 per-call,多请求叠加可能触发云限流)。
- **P2-7** 流式 hash 一次,digest 贯穿抽取路径(现 miss 路径多次重读大文件)。
- **P2-8** 缓存 TTL/size cap 淘汰(现 data/ocr-cache 无上限会涨满)。
