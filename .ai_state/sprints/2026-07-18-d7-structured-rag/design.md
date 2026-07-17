# D7 · 结构化 RAG（structured-rag, MVP）— design

> roadmap: 2026-07-doc-intelligence / Wave2 / D7 · path: **Feature（黄区，单模块新增）** · effort L
> depends_on: D6（✓ 2026-07-18 merge c874bd8，`server/ocr/docstructure.py` 已在 main）
> 实现者：codex sol-high（本 design = handoff 规格，隔离 worktree 实现）；主 agent review + merge。
> 用户拍板：**结构化检索先行**（SQLite FTS5/BM25，零新依赖，离线）；向量检索是二期 backlog（触发条件见
> `.ai_state/roadmap/2026-07-doc-intelligence/items.yaml` backlog 节）。

## 背景（WHY）

D6 给了文档级结构（章节树 + 语义标签 + 页锚 + 跨页表格），但结构只是**内存里的一次性 dict**——
没有落库、没有检索接口。后果：

- tender S1（取项目规则）目前只能让模型在几十万字底稿里"读"评标办法章，D6 的 `find_chapters_by_tag`
  只解决"定位到哪个 chapter 节点"，没解决"怎么把节点内容作为可查询的独立单元喂给消费者"。
- D8（底稿瘦身）要把 tender_worker 从"全量灌 32 万 token"改成"按 criteria 项检索相关章节"，前提是
  存在一个**检索原语**：给一个查询词/tag，返回带页锚出处的排序命中列表。没有这个原语，D8 无从谈起。
- 旧 roadmap S9（KB 补全 + 外部数据脚手架）被合并进本 item，但那是**后续消费者**，不是本 sprint 范围。

D7 的定位：**只交付检索原语本身**——把 `build_doc_structure` 的产物按章节切块、入库、可按语义
`tag` 过滤、可按关键词 BM25 排序检索，且每条命中必须带真实页锚出处。**不做**向量检索、不做 S9 KB
合并、不做外部数据真实接口、不改 tender S1 任何代码——这些都是"有了原语之后才谈得上"的下一步，
显式推迟（见"备选（放弃）"节末尾的 DEFER 清单）。

**为什么 FTS5/BM25 而不是向量**（用户已拍板，此处记录理由供 codex 与后续 reviewer 对齐）：SQLite
FTS5 是 Python stdlib `sqlite3` 自带的虚表扩展，零新依赖、零网络、部署机离线即可跑；招投标文本的
检索目标主要是"找到对应章节/条款"（结构化定位），不是"语义相似案例检索"（后者才需要向量）。向量
检索升级触发条件已在 roadmap backlog 记录："结构化检索命中率不足或需历史案例语义检索时触发"——
D7 上线后有真实命中率数据，才有资格评估是否需要二期。

## 输入 / 输出（契约）

**输入**：一份 `build_doc_structure(body) -> structure`（D6 产物，见
`.claude/contracts/ocr/doc-structure.schema.json`）+ **构建它所用的那份 `body` 原文**（同一字符串，
`index_document` 需要 `body` 重新定位每个章节标题所在行号，见方案节）。调用方必须保证两者匹配——
不匹配是调用方契约违反，`index_document` 内部会 fail-fast 抛错（见方案节 `_chunk_spans` 的一致性检查）。

**输出**：无新 JSON contract 文件（`rag-*.schema.json` 判断为**不需要**——见"备选（放弃）"节的理由）。
公开 API 是两个 Python 函数，签名固定如下（codex 严格照此实现，参数名/顺序不得改动）：

```python
# server/ocr/rag.py
def index_document(structure: dict, body: str, *, conn: sqlite3.Connection) -> int:
    """索引一份文档结构，返回写入的 chunk 数量。同 file 重复调用=幂等替换（先删后插）。"""

def search(
    query: str, *, conn: sqlite3.Connection, tag: str | None = None, limit: int = 10
) -> list[dict]:
    """BM25 关键词检索，返回按相关度降序的命中列表（见下方 hit 字段表）。"""
```

`search()` 返回的每个 hit 是一个 dict（不建 JSON schema，纯 Python 内部消费，见备选节理由），字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `chunk_id` | `str` | `f"{file}#{ordinal}"`，ordinal=章节树 DFS 前序索引，确定性 |
| `file` | `str` | 来源文件名（= `structure["file"]`） |
| `chapter_path` | `str` | 祖先→自身标题路径，`" > "` 连接，如 `"第三章 评标办法 > 二、综合评分法"` |
| `chapter_title` | `str` | 本节点自身标题 |
| `tag` | `str \| None` | 复用 D6 语义标签（`evaluation_method` 等） |
| `page_start` | `int \| None` | = 该章节点在 `structure` 中的 `page`（D6 已算好，直接复用，不重算） |
| `page_end` | `int \| None` | 本 chunk 文本跨度内出现过的**最大真实/carry 页号**（计算见方案节） |
| `page_anchor` | `str` | 人类可读出处：`"【第 10 页】"` / `"【第 10-12 页】"` / 页锚均缺时 `"页码未知"` |
| `text` | `str` | 索引/存储的 chunk 全文（= `chapter_path` + 该章节点子树跨度原文） |
| `score` | `float` | `-bm25(rag_chunks)`，越大越相关（对外翻转 bm25 越小越好的反直觉符号） |

**硬护栏（page-anchor 保真）**：`page_start`/`page_end` 只能是 `structure` 里真实出现过的
`【第 N 页】` 号或 `None`，绝不允许臆造。证明性质：`page_start` 取自 D6 已验证字段；`page_end`
的候选集合天然包含 `page_start` 本身（见方案节证明），因此 **`page_start` 非 None ⟹ `page_end`
非 None 且 `page_end >= page_start`**——这是一个可直接写测试断言的不变量。

## 方案（HOW，codex 实现锚点）

### 1. FTS5 表 schema（新 stores 模块，零侵入现有表）

新文件 `server/stores/rag_store.py`——**纯持久化层**，只做 schema + CRUD，不含分块业务逻辑
（业务逻辑在 `server/ocr/rag.py`）。层级：`stores/` 只能 import platform/stdlib
（`tests/test_layering.py::test_stores_only_import_platform` 现有守卫已锁），本模块甚至不需要
`server.platform`，只用 stdlib `sqlite3`——因为函数统一接受调用方传入的 `conn: sqlite3.Connection`
（依赖注入，不像其它 store 内置写死 `PLATFORM_DB_FILE`），这正是任务要求的"tests 用 tmp/内存
sqlite，不需要真 DB 文件"的来源。**MVP 不接入 `PLATFORM_DB_FILE`**——真实生产接线（哪个调用方传
哪个 conn）留给 D8/S1 wiring 决定，本 sprint 只交付原语（见 DEFER 清单）。

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks USING fts5(
    chunk_text,
    chunk_id UNINDEXED,
    file UNINDEXED,
    chapter_path UNINDEXED,
    chapter_title UNINDEXED,
    tag UNINDEXED,
    page_start UNINDEXED,
    page_end UNINDEXED,
    tokenize='trigram'
);
```

**为什么 `tokenize='trigram'` 而不是默认 `unicode61`**（已在本机 sqlite3 3.50.4 实测验证，证据见下）：
FTS5 默认 `unicode61` 分词器把连续中文字符当**一个 token**（因为没有空格分词边界），导致任何子串查询
**查不到任何结果**：

```
unicode61 query= 评标办法 -> []
unicode61 query= 资格审查 -> []
```

`trigram` 分词器（SQLite ≥3.34，本机 3.50.4 已确认支持，`sqlite3` stdlib 模块自带、零新依赖）按
3-字符 n-gram 切分，中文子串检索与 BM25 排序都正确：

```
trigram query= 评标办法 -> [(1, '...资格审查是评标办法...评标办法评分标准如下', -1.26e-06)]
```

**已知限制（写入设计，不是 bug）**：trigram 要求查询≥3 个字符才能生成 trigram，短于 3 字符的查询
（如 2 字符 `"业绩"`）稳定返回空列表，不抛异常——这是分词器固有行为，MVP 不做特殊处理（无真实
调用方需要 2 字符查询，出现时可在消费侧自行拼接上下文词）。

FTS5 的 `UNINDEXED` 列存储但不参与 `MATCH` 分词，可用普通 `WHERE col = ?` 过滤（已实测 `tag`/`file`
过滤与 `MATCH` 组合工作正常）——这就是 tag 过滤 + BM25 排序能在一条 SQL 里同时做到的原因，不需要
额外的辅助表或二次查询。

`rag_store.py` 三个函数（`ensure_schema` 幂等建表；其余两个调用前先 `ensure_schema(conn)`，允许
调用方传入全新连接）：

```python
TABLE_NAME = "rag_chunks"

def ensure_schema(conn: sqlite3.Connection) -> None: ...  # CREATE VIRTUAL TABLE IF NOT EXISTS（上面 DDL）

def delete_rows_for_file(conn: sqlite3.Connection, file: str) -> None: ...
    # ensure_schema(conn); DELETE FROM rag_chunks WHERE file = ?

def insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> None: ...
    # ensure_schema(conn); conn.executemany(INSERT ... VALUES (:chunk_text, :chunk_id, :file,
    #   :chapter_path, :chapter_title, :tag, :page_start, :page_end), rows)

def query_rows(
    conn: sqlite3.Connection, match_query: str, *, tag: str | None, limit: int
) -> list[sqlite3.Row]: ...
    # ensure_schema(conn)
    # cur = conn.cursor(); cur.row_factory = sqlite3.Row   # 只作用于本 cursor，不改调用方 conn 的
    #                                                        # row_factory（已实测验证无副作用）
    # sql = "SELECT chunk_id, file, chapter_path, chapter_title, tag, page_start, page_end,
    #         chunk_text, bm25(rag_chunks) AS rank FROM rag_chunks WHERE rag_chunks MATCH ?"
    # params = [match_query]
    # if tag is not None: sql += " AND tag = ?"; params.append(tag)
    # sql += " ORDER BY rank LIMIT ?"; params.append(limit)
    # return cur.execute(sql, params).fetchall()
```

`cursor.row_factory` 独立于 `conn.row_factory` 已实测确认（连接级默认不受影响），避免"调用方传入
的连接被 store 偷偷改了行为"这类隐藏副作用。

### 2. `docstructure.py` 最小导出（唯一触碰 D6 文件的改动，纯改名零行为变更）

分块需要两样 D6 内部已有、但当前是私有函数的能力：①按同一套标题正则重新定位标题所在**行号**
（D6 的 `parse_chapters` 内部已经这样做，只是没往外暴露行号）；②按同一套 page-carry 语义算任意
行区间的页号（D6 的 `_scan_page_context`）。**不复制这两段正则/进位逻辑到 rag.py**（P0 DRY——
铁律禁止同逻辑出现两次，且页锚进位是"硬护栏"逻辑，复制一份等于制造两处可能走偏的实现）。

任务 T1：在 `server/ocr/docstructure.py` 做**两个纯改名**（零行为变更，两个内部调用点同步改名）：

- `_chapter_title` → `chapter_heading`（签名/行为完全不变：`(raw: str) -> tuple[str, int] | None`）
- `_scan_page_context` → `scan_page_context`（签名/行为完全不变：
  `(lines) -> tuple[list[int | None], set[int]]`）

回归门：改名后 `tests/test_docstructure.py`（12 用例）+ `test_output_matches_draft07_contract`
必须**逐字节保持通过**（不是"重写测试通过"，是"一行不改，原样绿"——证明这确实是零行为变更）。

**备选（已考虑，放弃）**：让 `rag.py` 直接 `from server.ocr.docstructure import _chapter_title as
chapter_heading` 绕开改名——技术上可行（Python 不强制私有），但制造了"新模块依赖旧模块私有实现
细节"的隐藏耦合，且不出现在公开 API 表面，未来重构 docstructure 内部实现时容易被这层隐藏依赖
绊倒。两个纯改名 + 现有测试作回归网，风险和成本都更低，选它。

### 3. 分块算法（章节子树 → chunk，确定性、可测）

新文件 `server/ocr/rag.py`。核心规则：**每个章节树节点（任意 level）→ 一个 chunk，chunk 文本跨度
= 从该节点自身标题行，到"下一个 level ≤ 自身 level 的标题"之前（含其全部子孙内容）**——即"章节
子树整体入块"，不是"排除子节点的自身局部文本"。理由：tender S1 真实需求是"拿到 `tag=
evaluation_method` 整章内容"（含其嵌套的评分子项细则），如果切块排除子孙文本，父章节 chunk 只剩
一句引导语，检索出来没用。子树入块允许父子 chunk 内容重叠（同一段文字可能同时出现在父章节 chunk
和子章节 chunk 里）——这是有意为之的多粒度索引，不是 bug（tag 过滤 + BM25 排序会让消费者自然
命中最匹配粒度的那条）。

```python
def _flatten_tree(chapters: list[dict], ancestors: tuple[str, ...] = ()) -> list[dict]:
    """DFS 前序展平章节树；给每个节点算好 chapter_path（祖先路径+自身标题）。
    前序顺序 == parse_chapters 构建顺序 == 文档中标题的原始出现顺序（D6 已保证）。"""
    flat: list[dict] = []
    for node in chapters:
        path = ancestors + (node["title"],)
        flat.append({**node, "chapter_path": " > ".join(path)})
        flat.extend(_flatten_tree(node["children"], path))
    return flat


def _flatten_heading_lines(lines: list[str]) -> list[tuple[int, str, int]]:
    """重新扫描 body 原文定位每个标题所在行号，复用 docstructure.chapter_heading（不重造正则）。
    跳过 "### 文件:" 头行——与 parse_chapters 的跳过条件完全一致，保证两边顺序严格对齐。"""
    out: list[tuple[int, str, int]] = []
    for index, raw in enumerate(lines):
        if raw.strip().startswith("### 文件:"):
            continue
        heading = chapter_heading(raw)
        if heading is not None:
            title, level = heading
            out.append((index, title, level))
    return out


def _chunk_spans(structure: dict, body: str) -> list[dict]:
    lines = body.splitlines()
    page_of, _ = scan_page_context(lines)
    flat_nodes = _flatten_tree(structure["chapters"])
    flat_headings = _flatten_heading_lines(lines)
    if len(flat_nodes) != len(flat_headings):
        raise ValueError(
            "structure/body 不匹配：章节数与 body 中标题行数不一致——"
            "index_document 要求 body 必须是构建 structure 时用的同一份原文"
        )
    chunks: list[dict] = []
    for i, (node, (line_index, _title, level)) in enumerate(zip(flat_nodes, flat_headings)):
        end_line = len(lines)
        for next_line_index, _next_title, next_level in flat_headings[i + 1 :]:
            if next_level <= level:
                end_line = next_line_index  # 用已知行号，不用文本查找（标题可能重复，行号唯一可靠）
                break
        span_lines = lines[line_index:end_line]
        page_candidates = [p for p in page_of[line_index:end_line] if p is not None]
        chunks.append(
            {
                "chunk_id": f"{structure['file']}#{i}",
                "file": structure["file"],
                "chapter_path": node["chapter_path"],
                "chapter_title": node["title"],
                "tag": node["tag"],
                "page_start": node["page"],
                "page_end": max(page_candidates) if page_candidates else None,
                "chunk_text": node["chapter_path"] + "\n" + "\n".join(span_lines).strip(),
            }
        )
    return chunks
```

**`page_end` 计算的正确性证明**（写入设计供 reviewer 核验，也是测试断言的来源）：
`page_of[line_index]` 恒等于 `node["page"]`（= `page_start`，D6 的 `parse_chapters` 就是这样算
的），而 `line_index` 恒在 `range(line_index, end_line)` 内（节点至少含自己这一行），所以只要
`page_start` 非 `None`，`page_candidates` 至少含 `page_start` 本身 → `page_end` 保证非 `None` 且
`page_end >= page_start`。`page_start` 为 `None` 时（该章节前从未出现过页锚），`page_end` 一般也
为 `None`（除非子树内部后续出现了新页锚——这种情况下 `page_end` 变为真实页号完全合理，不违反
硬护栏：它就是子树跨度内真实出现的页号）。

`index_document` / `search` 组装：

```python
def index_document(structure: dict, body: str, *, conn: sqlite3.Connection) -> int:
    chunks = _chunk_spans(structure, body)
    rag_store.delete_rows_for_file(conn, structure["file"])  # 幂等替换：先清后插
    if chunks:
        rag_store.insert_rows(conn, chunks)
    conn.commit()
    return len(chunks)


def _escape_match_query(query: str) -> str:
    """把用户查询包成安全的 FTS5 短语字面量（转义内嵌双引号）。

    信任边界：query 是外部/调用方可控输入，直接拼进 MATCH 会被 FTS5 自己的查询语法解析
    （冒号=列过滤、AND/OR/NOT=布尔操作符、* =前缀）——含这些字符的自由文本会抛
    sqlite3.OperationalError（已实测复现：`评标:办法` → "no such column: 评标"）。
    包成短语字面量后语法错误消失（已实测验证），代价是放弃 FTS5 查询操作符——MVP 只要
    朴素相关度检索，不需要查询 DSL。
    """
    return '"' + query.replace('"', '""') + '"'


def _format_page_anchor(page_start: int | None, page_end: int | None) -> str:
    if page_start is None and page_end is None:
        return "页码未知"
    if page_end is None or page_start == page_end:
        return f"【第 {page_start} 页】"
    return f"【第 {page_start}-{page_end} 页】"


def search(
    query: str, *, conn: sqlite3.Connection, tag: str | None = None, limit: int = 10
) -> list[dict]:
    rows = rag_store.query_rows(conn, _escape_match_query(query), tag=tag, limit=limit)
    return [
        {
            "chunk_id": row["chunk_id"],
            "file": row["file"],
            "chapter_path": row["chapter_path"],
            "chapter_title": row["chapter_title"],
            "tag": row["tag"],
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "page_anchor": _format_page_anchor(row["page_start"], row["page_end"]),
            "text": row["chunk_text"],
            "score": -row["rank"],
        }
        for row in rows
    ]
```

### 4. 分层合规

`server/ocr/rag.py` 位于 ocr 服务层：`import server.stores.rag_store`（下行，合法）+
`import server.ocr.docstructure`（同层，合法）。**不 import server.tender / server.audit**——
`tests/test_layering.py::test_ocr_does_not_import_tender_or_audit` 是**扫描整个 `server/ocr/` 目录**
的现有守卫（`base = SERVER_DIR / "ocr"`，`rglob("*.py")`），新文件自动被覆盖，**不需要新写层级测试**。
`server/stores/rag_store.py` 只 import stdlib，天然满足
`test_stores_only_import_platform`（该测试的 forbidden 列表本就不含 stdlib）。

## 影响范围

**新增**：
- `server/stores/rag_store.py`（FTS5 schema + CRUD 原语）
- `server/ocr/rag.py`（分块算法 + `index_document` + `search` 公开 API）
- `tests/test_rag.py`（合成 fixtures，≥10 用例，见"测试"节）

**改动（唯一，纯改名零行为变更）**：
- `server/ocr/docstructure.py`：`_chapter_title` → `chapter_heading`，`_scan_page_context` →
  `scan_page_context`（2 处内部调用点同步改名），回归门 = 现有 12 个 D6 测试逐字节保持绿。

**明确不碰**（与 tender-schema-split 并行 sprint 零冲突，任何一个字符都不改）：
`server/common/contract.py` / `output_contracts.py` / `tender_output.py` / `evidence_resolution.py` /
`corpus.py`、任何 `server/tender/**` 文件。`.claude/contracts/` 目录**不新增文件**（见备选节理由，
本 sprint 判断不需要新 schema）。

**数据库**：`data/db/platform.sqlite3` 新增 **一张**虚表 `rag_chunks`（`CREATE VIRTUAL TABLE IF NOT
EXISTS`），不触碰任何既有表结构；测试全程用 `sqlite3.connect(":memory:")`，不落真实 DB 文件（任务
要求）。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 中文全文检索用错分词器（`unicode61` 对连续中文整体分一个 token，查询命中率为 0） | 用 `tokenize='trigram'`；已在本机 sqlite3 3.50.4 实测验证 `unicode61` 查询空结果、`trigram` 正确命中+正确 BM25 排序（见方案节证据） |
| trigram 查询短于 3 字符稳定返回空（非崩溃） | 文档化为已知限制，不做特殊处理（无真实调用方需要 2 字符查询） |
| FTS5 `MATCH` 查询字符串是用户可控输入，含 `:`/`"`/`AND` 等语法保留字会抛 `sqlite3.OperationalError`（信任边界问题，非 SQL 注入——已用参数化绑定） | `_escape_match_query` 把查询包成转义短语字面量，已实测验证抛错消失（security-checklist：用户输入进查询引擎前必须转义） |
| `structure` 与 `body` 不匹配（调用方传了不对应的一对）导致分块行号错位、静默产出错误页锚 | `_chunk_spans` 显式做长度一致性检查，长度不符 fail-fast 抛 `ValueError`，不静默降级（P0 反过度工程：信任边界内 fail-fast） |
| `docstructure.py` 改名影响已合并的 D6 产物 | 严格零行为变更（纯改名 + 内部调用点同步），12 个既有测试作回归门，逐字节验证保持通过 |
| 章节子树重叠索引（父章节 chunk 包含子章节内容）造成"重复命中"观感 | 有意设计（多粒度检索），非 bug；写入设计文档 + 用例覆盖，未来若命中率数据显示需要去重再迭代 |
| 页锚臆造（硬护栏） | `page_start` 直接复用 D6 已验证字段（不重算），`page_end` 数学上保证 `page_start` 非空时必非空且不小于 `page_start`（见方案节证明）；测试专断言此不变量 |
| 部署环境 sqlite3 编译时未启用 FTS5/trigram（极少见，Python 官方 macOS/Windows 构建默认带；某些精简 Linux 发行版系统库可能缺） | `ensure_schema` 建表失败会直接抛 `sqlite3.OperationalError`（fail-fast，不吞异常，不静默降级为"检索功能不可用"的隐藏分支）；本机已验证 3.50.4 支持，CI/开发环境一致 |

## 验收标准（codex 交付 = 全绿）

- [ ] `server/stores/rag_store.py`：`ensure_schema` / `delete_rows_for_file` / `insert_rows` /
      `query_rows` 四函数，只 import stdlib，`query_rows` 用 cursor 级 `row_factory`（不改调用方
      `conn` 的 `row_factory`）。
- [ ] `server/ocr/rag.py`：`index_document(structure, body, *, conn) -> int` +
      `search(query, *, conn, tag=None, limit=10) -> list[dict]`，签名与本设计完全一致；不 import
      `server.tender` / `server.audit`。
- [ ] `server/ocr/docstructure.py`：仅 `_chapter_title`→`chapter_heading`、
      `_scan_page_context`→`scan_page_context` 两处纯改名，零行为变更。
- [ ] `tests/test_rag.py`（合成 fixtures，≥10 用例，见下节）全绿。
- [ ] `tests/test_docstructure.py`（既有 12 用例）逐字节保持通过（改名回归门）。
- [ ] 页锚硬护栏不变量：`page_start` 非 `None` ⟹ `page_end` 非 `None` 且 `page_end >= page_start`
      ——至少一个测试显式断言。
- [ ] `_escape_match_query` 对含 `:`/`"`/`AND`/`*` 的查询不抛异常——至少一个测试覆盖。
- [ ] 全量 `uv run pytest -q` 绿（不劣化基线 **834 passed**；`test_rag.py` 预计新增约 10 例 →
      总数约 844，实际以 codex 最终用例数为准，但**不得低于基线 834**）。
- [ ] `uv run ruff check .` 净（line-length ≤100，py312，无新增 lint 违规）。
- [ ] `data/db/platform.sqlite3` 未被破坏性改动——本 sprint 测试全程用内存/tmp sqlite，不依赖也不
      污染真实 DB 文件。

## 测试（`tests/test_rag.py`，≥8 用例，实际给 10）

fixture 风格对齐 `tests/test_docstructure.py`（`_body()` 辅助函数拼 `"### 文件: ...\n" + text`，
每个测试内联构造 `build_doc_structure` 输入；DB 用 `sqlite3.connect(":memory:")` 每测试新建）。

1. `test_index_document_returns_chunk_count_and_search_finds_it` — 两章节文档，
   `index_document` 返回 2；`search("评标办法", conn=conn)` 命中含该词的章节，`hit["text"]` 含
   预期子串、`hit["chapter_title"]` 匹配。
2. `test_bm25_ranking_orders_more_relevant_chunk_first` — 两个 chunk，一个查询词重复多次、一个只
   出现一次；断言 `search(...)[0]["chunk_id"]` 是重复多次那个，且其 `score` 大于另一条。
3. `test_tag_filter_restricts_results_to_matching_tag` — 两章节都含查询词但 `tag` 不同；
   `search(query, tag="evaluation_method")` 只返回该 tag 的 chunk。
4. `test_hits_carry_page_anchor_provenance_and_invariant` — 不同页锚的多章节文档；断言每条 hit 的
   `page_start`/`page_end`/`page_anchor` 格式正确，且验证 `page_start` 非 None ⟹ `page_end >=
   page_start` 不变量。
5. `test_search_no_match_returns_empty_list` — 查询语料库中不存在的词，返回 `[]`。
6. `test_index_document_with_no_chapters_indexes_zero_chunks` — `build_doc_structure` 产物
   `chapters == []`（无标题的纯文本）；`index_document` 返回 0，随后 `search` 对该 file 返回 `[]`。
7. `test_chunk_boundary_excludes_sibling_but_includes_subtree` — 两个同级（level=1）兄弟章节：
   断言章节 A 的 chunk 文本不含章节 B 的内容；一个带嵌套子章节的 level=1 章节：断言其 chunk 文本
   **包含**子章节文本（子树入块语义）。
8. `test_reindex_same_document_is_idempotent_and_deterministic` — 对同一 `(structure, body)`
   调用 `index_document` 两次；两次返回值相同，`rag_chunks` 表行数不翻倍（无重复累积），两次
   `search` 命中的 `chunk_id` 集合与 `text` 完全一致。
9. `test_search_query_with_fts5_special_characters_does_not_raise` — 查询含 `:`、`"`、`AND`、`*`
   等 FTS5 语法保留字符；断言不抛异常，返回一个 list（允许为空）。
10. `test_search_respects_limit` — 索引 ≥3 条都匹配查询词的 chunk；`search(..., limit=2)` 精确返回
    2 条，且是相关度最高的前 2 条。

## Tasks（T1..T5，codex 从上到下实现，TDD red→green）

1. **T1 · docstructure 最小导出**：`server/ocr/docstructure.py` 内 `_chapter_title`→
   `chapter_heading`、`_scan_page_context`→`scan_page_context` 纯改名（2 处内部调用点同步）；跑
   `uv run pytest tests/test_docstructure.py -q` 确认既有 12 用例逐字节保持绿（回归门，先证明零
   行为变更再继续）。
2. **T2 · 先写测试（red）**：写完整 `tests/test_rag.py`（上节 10 用例），此时 `server/ocr/rag.py`
   与 `server/stores/rag_store.py` 均不存在，测试预期在 import/collection 阶段即失败（red 状态
   确认，TDD 起点）。
3. **T3 · `server/stores/rag_store.py`**：实现 `ensure_schema` / `delete_rows_for_file` /
   `insert_rows` / `query_rows`（DDL + cursor 级 row_factory，见方案节 1）。
4. **T4 · `server/ocr/rag.py`**：实现 `_flatten_tree` / `_flatten_heading_lines` / `_chunk_spans`
   / `_escape_match_query` / `_format_page_anchor` / `index_document` / `search`（见方案节 3）。
   跑 `uv run pytest tests/test_rag.py -q`，全部转绿。
5. **T5 · 全量绿 + lint 净**：`uv run pytest -q`（全仓，确认不劣化基线 834 passed）+
   `uv run ruff check .`（净，line-length ≤100）。两条命令的实际输出作为交付证据。

> roadmap `items.yaml` D7 状态回写与 `.ai_state/architecture/ARCHITECTURE.md` 更新由主 agent 在
> review + merge 后完成（对齐 D6/D2 实际流程：codex 只交付代码+测试，主 agent 通读验证后再做
> ai_state 收尾），不在 codex 的 T1-T5 任务范围内。

## 备选（放弃）

- **向量/embedding 检索作为一期方案**：放弃。用户已拍板结构化检索先行；向量检索需要额外模型/依赖
  （即使自托管 bge-m3 也要新增推理成本），且当前真实需求（tender S1 定位章节）是结构化定位问题，
  不是语义相似度问题。留作 roadmap backlog，触发条件已记录（结构化检索命中率不足时）。
- **`unicode61`（FTS5 默认分词器）**：放弃。已实测验证对连续中文文本查询命中率为 0（把整段中文
  当一个 token），不可用于本项目的中文招投标文本场景。
- **直接 `from docstructure import _chapter_title`（不改名，绕过私有）**：放弃。技术可行但制造
  跨模块隐藏耦合（依赖另一模块的私有实现细节，不出现在公开 API 表面）。两个零行为变更的纯改名 +
  既有测试回归网，风险更低、意图更清晰，选它。
- **独立 `.claude/contracts/ocr/rag-hit.schema.json` 契约文件**：放弃（本 sprint 判断"不需要"，
  对应任务提示里的条件句"if a structured result shape is warranted"）。理由：`search()` 返回值是
  纯 Python 内部消费（同进程调用，不跨 agent/HTTP 边界），不像 `doc-structure.schema.json` 那样
  服务"OCR pipeline → tender 消费"的跨层契约边界，也不经过 `apply_schema_semantics` 这类需要注册
  schema 的路径。等 D8/S1 真正接线出现跨进程/跨 agent 消费需求时，若确有必要再补 schema——现在加
  是无消费者的过度抽象（铁律[反过度工程]）。
- **叶子节点独占分块（子树内容不重复，父章节 chunk 排除子章节文本）**：放弃。会导致"整章内容"这个
  最核心的检索单元（tender S1 要读的评标办法整章，含其嵌套评分子项）无法通过一次检索拿到——父章节
  chunk 只剩标题+引导语，检索价值归零。子树入块（允许重叠）虽然索引体积略增，但直接匹配真实消费
  场景，MVP 选它。
- **DEFER（本 sprint 明确不做，留给后续 item）**：向量检索本身；旧 S9 KB 补全合并；外部数据脚手架
  （连真实接口）；tender S1 任何代码接线（消费 `search()`/`index_document()` 是下一个 item 的事）；
  `server/stores/rag_store.py` 接入 `PLATFORM_DB_FILE` 默认连接（等真实生产调用方出现再决定怎么
  接，本 sprint 只验证"给定任意 conn 能正确工作"）。

---
_参考：server/ocr/docstructure.py（D6，本 sprint 唯一改动的既有文件）、
.claude/contracts/ocr/doc-structure.schema.json（输入契约）、
.ai_state/sprints/2026-07-18-doc-understanding/design.md（D6 design，风格对齐样板）、
.ai_state/architecture/ARCHITECTURE.md（全局分层图 + 现有 stores 清单）、
tests/test_layering.py（ocr/stores 分层守卫，D7 新文件自动被现有守卫覆盖，无需新测试）、
.ai_state/roadmap/2026-07-doc-intelligence/items.yaml（D7 item + backlog 向量检索触发条件）。
本机实测证据（sqlite3 3.50.4，2026-07-18）：unicode61 中文子串检索失败 / trigram 正确命中+BM25
排序 / FTS5 特殊字符查询未转义抛 OperationalError、转义后不抛 / cursor 级 row_factory 不影响
connection 级默认值——均在设计阶段用一次性 Python 脚本验证，未落任何持久化产物。_
