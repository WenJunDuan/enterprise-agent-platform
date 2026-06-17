# 路由详规（L1 容器分诊）

`server/ocr/classify.py` 的判定依据与产物。原则：**能直读绝不 OCR**。

## 分流表

| 文件类型 | 进 OCR？ | route / handler | 处理 |
|---|---|---|---|
| Excel `.xlsx/.xlsm/.xls` | ❌ | native / excel | openpyxl 直读单元格/合并/公式 |
| 纯文本 `.txt/.csv/.md/.json/.tsv` | ❌ | native / text | 直读 |
| Word `.docx`（文本型） | ❌ | native / word | python-docx 抽文本+表 |
| Word `.docx`（图片/扫描型） | ✅ | ocr / word_scan | 内嵌图为主、正文近空 → 转 OCR |
| PDF（含文本层） | ❌ | native / pdf_text | pypdf 抽文本 |
| PDF（扫描） | ✅ | ocr / pdf_scan | 全 `/DCTDecode`、无字体 → PaddleOCR-VL |
| 图片 `.png/.jpg/.tif/.bmp/.webp` | ✅ | ocr / image | 只能 OCR |
| 其它 / 未知 / 损坏 | — | manual / unknown | 转人工，不猜 |

## 判定启发式

- **PDF 文本层**：`/Font` 计数 > 0 且 单页字节 < 200KB → 有文本层（直读）；
  含 `/DCTDecode|/JPXDecode|/CCITTFaxDecode` 且无字体 → 扫描（OCR）。
- **DOCX 文本 vs 图片**：解 zip，比较 `word/document.xml` 去标签后的文字数与 `word/media/` 图像数；
  文字 ≥ 200 字符 → 文本型；近空 + 有嵌入图 → 图片/扫描型。
- 阈值是经验值（`server/ocr/classify.py` 内常量 `PDF_SCANNED_KB_PER_PAGE` / `DOCX_MIN_TEXT_CHARS`），按真实样本 POC 调。

## 为什么 Excel 不转 PDF 再 OCR

1. **更慢**：原生读毫秒级；转 PDF→栅格化→VLM 逐页推理是其数量级倍。
2. **更不准**：数字经 OCR 会 `0/O`、`1/l`、`5/6` 混淆——直接砸"金额/日期高准确"硬指标。
3. **丢结构**：多 sheet、合并单元格、公式、单元格类型全丢；宽表打印分页还会把列切碎、跨页错行。

「统一成 PDF」这个直觉只用于 **OCR 分支内部**（扫描 PDF/图片/图片型 Word 归一后喂一个 OCR 引擎），不用来吞掉能直读的文件。
