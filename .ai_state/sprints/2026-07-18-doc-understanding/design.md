# D6 · 文档级结构化（doc-understanding）— design

> roadmap: 2026-07-doc-intelligence / Wave2 / D6（提前拉起，与 D2 并行，交 codex sol-high 实现）
> path: **Feature（黄区，单模块新增）** · effort L · depends_on: D1（✓ eval 回归闸已在 main）
> 实现者：codex sol-high（本 design = handoff 规格）；主 agent review + merge。

## 背景（WHY）

2026-07-02 架构评估：OCR 有**页级**理解（VL 输出 Markdown+JSON，`pipeline.build_extraction_block`
组装成带 `【第 N 页】` 锚点的内联底稿），但**无文档级结构**——没有章节树 / 目录 / 语义标签 / 跨页
表格合并 / 关键实体。后果：
- tender S1（取项目规则）靠模型在几十万字底稿里"找评标办法章"，不稳、耗上下文。
- 底稿全量灌 prompt（ZJ 32 万 token > 128K 窗口），D8 底稿瘦身没有结构可依。

D6 建**确定性文档结构化层**：从既有底稿文本解析出章节树 + 语义标签 + 实体 + 跨页表格合并，
**页锚全程保真**，产出新契约。直接服务 tender S1（按 `tag=evaluation_method` 定位评标办法章页范围）
与 D8（按章节检索喂模型）。`server/ocr/boq.py` 是**领域感知确定性抽取的先例**（纯函数、无模型、
`【第 N 页】` 锚点保真、page-carry 行距上限）——D6 沿用其范式，泛化到通用文档结构。

## 输入 / 输出（契约）

**输入**：`pipeline.build_extraction_block` 的产物文本（或单文件 body）。关键格式约定（已核实 pipeline.py）：
- 每文件以 `### 文件: {name} (kind=..., route=...)` 头开始（`_FILE_HEADER_PREFIX = "### 文件:"`）。
- 页锚点独占一行：`【第 N 页】`，正则 `^\s*【第\s*(\d+)\s*页】\s*$`（**复用 boq.py `_PAGE_RE`，不要另造**）。
- 页锚后跟该页 markdown（OCR pages 路径）或 blocks 文本（native pdf_text 路径）；表格可能是
  `[表: name]` + 制表符分隔行（`_render_tables`），也可能是 markdown 表格。
- 识别失败行以 `[识别失败]` 打头（`OCR_ERROR_PREFIX`）；空块占位 `（无识别内容）`。

**输出**：新契约 `.claude/contracts/ocr/doc-structure.schema.json`（draft-07，风格对齐 ocr/extract-result.schema.json）。
每文件一个结构对象：

```jsonc
{
  "file": "ZJ招标文件.pdf",           // 来自 ### 文件: 头
  "page_count": 120,                    // 底稿中出现的最大页锚号（null 若无锚点）
  "chapters": [                         // 章节树（嵌套）
    {
      "title": "第三章 评标办法",
      "level": 1,                       // 1=章 2=节 3=条/小节
      "page": 18,                       // 最近在先的页锚号（无锚→null）
      "tag": "evaluation_method",       // 语义标签枚举，可 null
      "children": [ /* 同结构递归 */ ]
    }
  ],
  "entities": [                         // 关键实体（页锚+出处保真）
    {"type": "amount", "value": "12,345,678.00", "page": 2, "source": "投标总价: 12,345,678.00"},
    {"type": "date", "value": "2026-05-20", "page": 1, "source": "开标时间：2026年5月20日"},
    {"type": "cert_no", "value": "苏B2-20240xxx", "page": 45, "source": "..."},
    {"type": "person", "value": "张三", "page": 60, "source": "项目负责人：张三"}
  ],
  "tables": [                           // 跨页合并后的表格
    {"name": "分部分项工程量清单", "start_page": 5, "end_page": 7, "columns": ["序号","名称","金额"],
     "row_count": 240, "merged_from_pages": [5,6,7]}
  ]
}
```

## 方案（HOW，codex 实现锚点）

新模块 `server/ocr/docstructure.py`（**纯函数、无模型、无网络**，与 boq.py 同层同范式；ocr 服务层，
可被 tender import[features→ocr 合法]，**禁 import tender/audit**——test_layering 单向守卫已锁）。

主入口：`build_doc_structure(block_or_body: str, *, file_name: str | None = None) -> dict`
（返回符合上面 schema 的 dict）。内部拆成可单测的纯函数：

1. **页锚扫描**：遍历行，`_PAGE_RE` 匹配更新 `cur_page`；沿用 boq 的 **page-carry 行距上限**思想
   （无锚长尾段页号失效→None，防串页）。**硬护栏：绝不臆造/丢失页号；无锚内容 page=null，不猜。**

2. **章节树 `parse_chapters(lines) -> list[chapter]`**（确定性启发式）：
   - 标题识别正则（按优先级）：① markdown `^#{1,6}\s+(.+)` （level=井号数，clamp 到 1..3）；
     ② 中文章节 `^\s*第[一二三四五六七八九十百千0-9]+[章节篇部分]\s*(.*)`（level=1）；
     ③ `^\s*[一二三四五六七八九十]+、\s*(.+)`（level=2）；④ `^\s*（[一二三四五六七八九十0-9]+）\s*(.+)`（level=3）。
   - 每命中一个标题→节点 `{title, level, page=cur_page, tag, children:[]}`；按 level 建父子栈（更深 level 入
     当前节点 children，更浅/相等回栈）。非标题行忽略（不进树，正文留给 entities/tables）。
   - **不做语义理解**——纯形式识别，避免误报靠 level 结构兜底。

3. **语义标签 `tag_chapter(title) -> str | None`**（关键词映射，服务 tender S1）：
   枚举 `qualification_review / evaluation_method / performance / commercial / technical / bid_form / general`。
   关键词表（title 命中即打，多命中取表内优先序）：
   - `evaluation_method`：评标办法 / 评分标准 / 评分细则 / 评审办法
   - `qualification_review`：资格审查 / 资格评审 / 资格要求 / 初步评审 / 符合性审查 / 响应性审查
   - `performance`：业绩 / 类似项目 / 类似工程
   - `bid_form`：投标函 / 投标报价 / 开标一览
   - `commercial`：商务 / 合同条款 / 付款
   - `technical`：技术方案 / 技术标 / 施工组织
   - 其余 → `general`（或 null）。**关键词表作模块常量，便于扩展**（反过度工程：先覆盖 tender 实测需要的几类）。

4. **实体 `extract_entities(lines, page_of) -> list[entity]`**（正则 + 页锚，每条带 source 片段）：
   - `amount`：**复用 boq 的金额正则**（`_AMOUNT_STRICT`；不要重造），去千分位保精度。
   - `date`：`\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*日?` → 归一 `YYYY-MM-DD`。
   - `cert_no`：资质/证书编号（`(?:证书|资质|注册)编号[:：]?\s*([A-Za-z0-9\-]{6,})` 等 label 锚定，避免抓噪音）。
   - `person`：`(?:项目经理|项目负责人|技术负责人|法定代表人)[:：]?\s*([一-龥]{2,4})` label 锚定。
   - 每实体 `{type, value, page, source}`；page=该行 page_of；source=该行去空原文（截断 ≤120 字符）。
   - **label 锚定优先**（减误报）；抓不到不猜。去重（同 type+value+page 合一）。

5. **跨页表格合并 `merge_tables(...) -> list[table]`**（MVP 保守）：
   - 识别表格段（`[表: name]` 头或连续制表符/markdown `|` 行）。
   - 合并判据（保守，避免错并）：相邻表格段被单个 `【第 N 页】` 分隔、且**列数一致**（或后段无表头）→
     视为跨页续表，rows 拼接，`start_page`=首段页、`end_page`=末段页、`merged_from_pages` 记全。
   - 列数不一致 / 中间夹正文标题 → 不合并（各自独立表）。**宁可不合并也不错并**（范畴错误比漏合更贵）。

6. **辅助消费函数** `find_chapters_by_tag(structure, tag) -> list[{title, page, ...}]`（深度遍历树，供
   tender S1 定位；本 sprint 只提供纯函数 + 测试，**不改 tender S1 代码**——S1 接线留 D6 之后的薄 follow-up，
   避免碰 tender 包，与 D2 worktree 零冲突）。

## 影响范围

- **新增**：`server/ocr/docstructure.py`、`.claude/contracts/ocr/doc-structure.schema.json`、
  `tests/test_docstructure.py`（+ 合成 fixtures，仿 test_boq.py 的 synthetic full_body 手法，不需真 PDF）。
- **不改**：pipeline.py / boq.py / tender 包 / 任何现有契约（纯新增，零回归面）。**与 D2 worktree 完全不冲突**
  （D2 只动 server/tender + routes/tender + test_layering；D6 只动 server/ocr + 新 schema + 新 test）。
- 分层：docstructure 在 ocr 服务层，`import server.ocr.boq`（同层复用金额正则）合法；**禁 import server.tender/audit**。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 章节误识别（正文行像标题） | level 结构栈兜底 + 保守正则（label/章节词锚定）；测试覆盖误报样本 |
| 跨页表格错并（不同表被合） | 列数一致 + 单页锚分隔才合并；宁漏不错；测试含"不该合"用例 |
| 页锚丢失/臆造（硬护栏） | 复用 `_PAGE_RE`；无锚 page=null 不猜；测试专断言页锚保真 + null 语义 |
| 实体噪音（抓到编号/序号） | label 锚定优先 + 复用 boq 金额档；测试含噪音行不误抓 |
| 与 tender S1 耦合超范围 | 本 sprint 只出纯函数 + `find_chapters_by_tag`，不接 S1 代码 |

## 验收标准（codex 交付 = 全绿）

- [ ] `server/ocr/docstructure.py`：`build_doc_structure` + 5 内部纯函数，无模型/网络，ruff 净。
- [ ] `.claude/contracts/ocr/doc-structure.schema.json`：draft-07，`build_doc_structure` 产物经 jsonschema 校验通过。
- [ ] `tests/test_docstructure.py`（合成 fixtures，≥ 10 用例）覆盖：章节树嵌套、语义标签（evaluation_method/
      qualification_review 至少）、四类实体带正确页锚、跨页表格合并 + "不该合"负例、**页锚保真 + null 语义**、
      `find_chapters_by_tag`。
- [ ] 分层：`docstructure` 不 import server.tender/audit（test_layering 现有守卫覆盖 ocr→features 已锁）。
- [ ] 全量 `uv run pytest -q` 绿（不劣化基线 816 passed / 5 fitz env fail）+ `uv run ruff check .` 净。
- [ ] 页锚硬护栏：任何结构节点/实体的 page 要么是底稿真实 `【第 N 页】` 号、要么 null，**绝不臆造**。

## 备选（放弃）

- 让模型做结构化（LLM 解析章节）：慢/贵/不可回归，与确定性底稿校验链冲突（同 boq 决策）。放弃，D5 决策点
  agent 化时再按需在低置信分支补 LLM，不在 D6。
- 向量/语义章节分割：越权 D7 结构化 RAG 范围。D6 只做确定性形式结构。

---
_参考：server/ocr/boq.py（确定性抽取先例）、server/ocr/pipeline.py（底稿格式）、
.claude/contracts/ocr/extract-result.schema.json（schema 风格）、.claude/contracts/tender/criteria.schema.json（S1 消费侧）、
roadmap/2026-07-doc-intelligence/items.yaml D6。_
