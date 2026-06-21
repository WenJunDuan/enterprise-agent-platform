"""OCR 本地原生调用的并发锁——OCR 并行（extract_dir 线程池）时保护非线程安全的本地库。

PyMuPDF(fitz)、本地 PaddleOCR/PaddleX pipeline 官方均【非线程安全】。所有 fitz / 本地 paddle
调用经这里的共享锁串行化（渲染/直读快，串行无妨）；慢的云 OCR(HTTP)不经此锁，仍并行——
这是"线程安全 + 保住云并行收益"的折中（codex perf review P1-1/P1-4）。

放独立模块（非 native/engine 内）使二者共享【同一把】fitz 锁——否则两模块各自一把锁，
扫描 PDF 渲染(engine)与文本层直读(native)仍可能并发调 fitz 而崩。
"""

import threading

# 所有 fitz.open 调用：native 文本层直读(read_pdf_text) + engine 扫描页渲染(_render_pdf_pages)。
FITZ_LOCK = threading.Lock()

# 本地 PaddleOCR/PaddleX pipeline + 印章识别（全局 predictor / GPU / runtime 资源，并发会 OOM/race）。
PADDLE_LOCK = threading.Lock()
