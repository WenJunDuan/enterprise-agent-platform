# D8 · 底稿瘦身（transcript-slimming）— design

> roadmap: `2026-07-doc-intelligence` / Wave2 / D8 · path: **Feature（黄区，单模块）** · effort M
> depends_on: D2（✓ 2026-07-18 merge 260a140，`server/tender/` feature 包已在 main）、
> D7（✓ 2026-07-18 merge 3b686d1，`server/ocr/rag.py` 检索原语已在 main）
> 实现者：codex sol-high（本 design = handoff 规格，隔离 worktree 实现）；主 agent review + merge。
> 基线：main 850 tests green（2026-07-18 `uv run pytest -q --collect-only` 实测确认）。

## 背景（WHY）

`server/tender/runner.py::run_tender_evaluation` 今天把「招标文件底稿 + 当前家投标文件底稿」
**无差别全量拼接**成一个字符串塞进模型 context（`_load_doc_layer_context`，见方案节 1）。真实案例
（张謇标）实测 ~32 万 token，远超绝大多数模型的上下文窗口（`logs/s7-model-compare/REPORT.md`：
"底稿32万token>>128K，杠杆在精简底稿"，见 `items.yaml` D8 source.evidence）。

D6（`build_doc_structure`）交付了章节树+页锚+语义标签，D7（`index_document`/`search`）交付了
FTS5/BM25 检索原语——但两者都还没接到 tender 评标路径上（D7 merge note 原话："DEFER: tender S1
接线"）。本 sprint 就是把这条线接上：**招标文件底稿不再无差别全量灌注，改为按本项目 criteria
（资格审查项 + 评分项）检索相关章节，只喂检索命中的切片**。

**为什么现在能做、且能安全做**：招标项目的 `criteria`（`.claude/contracts/tender/criteria.schema.json`
结构）在评标发生前通常已经就绪——要么由 R1 `tender-extract-info` 流水线在上传时抽取
（`server/tender/doc_pipeline.py`，写 `tender_project_docs.criteria` + `criteria_status=ready`），
要么由评标 worker 首次评标后回填（`server/tender/worker.py::_backfill_criteria`，首写者赢）。
**criteria 本身就是"招标文件里哪些章节重要"的现成索引**——`eligibility_rules[].check` 对应资格
审查章节，`items[].item`/`category` 对应评标办法/评分标准章节。用 criteria 当检索 query，天然
比"整份文档全量灌注"更贴合"模型这次评标真正要看什么"。

**MVP 范围收窄（显式声明，不做的部分见备选节 DEFER）**：本 sprint 只精简**招标文件**侧底稿。
投标文件（S2 事实抽取消费的那份）**保持全量不变**——招标文件全文每次评标都被重复注入（哪怕
criteria 已知、模型已被告知"S1 直接采用勿重新解析"），这是当前 token 浪费的大头，也是本 sprint
能在不动 S2/investigation 逻辑的前提下独立交付、独立验证的最小闭环；投标文件按 criteria 检索
（真正的"S2 也检索"）留给后续 item（backlog，见备选节）。

## 输入 / 输出（契约）

**输入**：`project_doc["ocr_text"]`（招标文件底稿原文字符串，`server/stores/tender_doc_store.py`
`tender_project_docs.ocr_text` 字段，已就绪即 `ocr_status="ready"`）+ 该项目已存的
`project_doc["criteria"]`（JSON 字符串，可能为 `None`——R1 抽取失败/未完成，或历史散单从未评标过）。

**输出**：一个新的纯函数 `server/tender/context_slim.py::build_slim_tender_context`，签名固定：

```python
def build_slim_tender_context(
    tender_text: str, criteria: dict, *, file_name: str
) -> str | None:
    """按 criteria 的 eligibility_rules/items 检索招标文件底稿相关章节，组装精简 context。

    返回精简后的字符串（含显式页锚，见护栏）；任一检索项零命中，或 criteria 不含任何可用于
    检索的条目、或招标文件没有可识别章节 → 返回 None（调用方据此改用全量原文，绝不静默丢项）。
    """
```

不新增 `.claude/contracts/` schema——`build_slim_tender_context` 的输出是纯字符串（拼进
`context` 供模型读取的自由文本），不是跨进程/跨 agent 消费的结构化契约，同 D7 `search()` 的
"纯 Python 内部消费不建 schema"先例（design.md 备选节）。

## 方案（HOW，codex 实现锚点）

### 1. 现状代码定位（读代码得出，不是猜测）

`server/tender/runner.py`：

- `run_tender_evaluation`（129-263 行）是评标核心，其中 **context 组装段落在 151-183 行**：
  ```python
  doc_layer_text: str | None = None
  if _tender_read_doc_layer_enabled() and project_id:
      if bid_id:
          await _wait_doc_layer_ready(project_id, bid_id, tenant)
      doc_layer_text = await asyncio.to_thread(
          _load_doc_layer_context, project_id, bid_id, tenant
      )
  if doc_layer_text is not None:
      ocr_block = doc_layer_text
  else:
      ocr_block = await asyncio.to_thread(
          ocr_preprocess_block, directory_path, purpose=TENDER_OCR_PURPOSE
      )
  context = (
      f"=== OCR/直读底稿（确定性预处理，优先用此文本，无需再 Read 文件）===\n{ocr_block}"
      if ocr_block else None
  )
  ```
- `_load_doc_layer_context`（69-104 行）是唯一一处**能干净拆出"招标文件底稿"与"投标文件底稿"
  两段独立文本**的地方（`project_doc["ocr_text"]` vs `bid["ocr_text"]`）：
  ```python
  parts: list[str] = [
      f"=== 招标文件底稿 ===\n{project_doc['ocr_text']}",
      f"=== 投标文件（{bidder}）底稿 ===\n{bid['ocr_text']}",
  ]
  return "\n\n".join(parts)
  ```
  `ocr_preprocess_block`（P4 回落分支，走串行 OCR 时）没有这个切分——它对整个目录一次性 OCR，
  产出一坨混合文本，招标/投标文件边界不再显式可分。**本 sprint 的切入点只能选在
  `_load_doc_layer_context` 这一层**，P4 回落分支保持不变（本就是兜底/legacy 路径，token 体量
  也不是本 sprint 目标，见影响范围"不碰"清单）。
- `stored_criteria` 目前在 185-207 行**另一次** `get_project_doc` 调用里被读出、解析、拼成
  "已解析评分标准 criteria（S1 直接采用，勿重新解析）"的展示块追加在 `context` 尾部——这段
  代码**保持不动**（见方案节 3 的取舍说明），本 sprint 新增一条**独立**的 criteria 读取路径
  服务于检索式精简。

### 2. 新增 `server/tender/context_slim.py`

新文件，只依赖 `server.ocr.docstructure` / `server.ocr.rag`（tender→ocr 单向合法，同
`runner.py` 现有 `from server.ocr.pipeline import ocr_preprocess_block` 先例）。

```python
"""D8 底稿瘦身：按项目 criteria 检索招标文件相关章节，替代全量灌注。

criteria.eligibility_rules[] 对应招标文件的"资格审查"章节（docstructure 语义标签
qualification_review），criteria.items[] 对应"评标办法/评分标准"章节（语义标签
evaluation_method）——两者都是 D6 docstructure._TAG_KEYWORDS 现成的固定标签，criteria
本身在抽取时就是从这两类章节里解析出来的（见 .claude/commands/tender-evaluate.md S1），
用它做检索 query 天然贴合真实定位需求。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from server.ocr.docstructure import build_doc_structure
from server.ocr.rag import index_document, search

_ELIGIBILITY_TAG = "qualification_review"
_EVALUATION_TAG = "evaluation_method"
# 每条 criteria 项检索几个 chunk：给到"整章+相邻子节"的量级，过大会让去重后仍逼近全量。
_CHUNKS_PER_QUERY = 3


def _criteria_queries(criteria: dict[str, Any]) -> list[tuple[str, str, str]]:
    """把 criteria 的 eligibility_rules/items 转成 (query_text, tag, label) 三元组列表。"""
    queries: list[tuple[str, str, str]] = []
    for rule in criteria.get("eligibility_rules") or []:
        text = " ".join(filter(None, [rule.get("check"), rule.get("requirement")])).strip()
        if text:
            queries.append((text, _ELIGIBILITY_TAG, f"资格审查:{rule.get('check', '')}"))
    for item in criteria.get("items") or []:
        text = " ".join(filter(None, [item.get("item"), item.get("category")])).strip()
        if text:
            queries.append((text, _EVALUATION_TAG, f"评分项:{item.get('item', '')}"))
    return queries


def build_slim_tender_context(
    tender_text: str, criteria: dict[str, Any], *, file_name: str
) -> str | None:
    """按 criteria 检索招标文件相关章节，组装精简 context；无法安全精简时返回 None。

    None 的三种触发条件（调用方一律回退全量原文，绝不静默丢项）：
    1. criteria 不含任何可用于检索的 eligibility_rules/items 文本；
    2. tender_text 没有可识别的章节（build_doc_structure 产物 chapters 为空）；
    3. 任一检索项零命中——宁可整份回退全量，不做"部分精简、部分静默缺失"。
    """
    queries = _criteria_queries(criteria)
    if not queries:
        return None

    structure = build_doc_structure(tender_text, file_name=file_name)
    if not structure["chapters"]:
        return None

    conn = sqlite3.connect(":memory:")
    index_document(structure, tender_text, conn=conn)

    collected: dict[str, dict[str, Any]] = {}
    for query_text, tag, _label in queries:
        hits = search(query_text, conn=conn, tag=tag, limit=_CHUNKS_PER_QUERY)
        if not hits:
            conn.close()
            return None
        for hit in hits:
            collected.setdefault(hit["chunk_id"], hit)

    conn.close()
    blocks = [f"{hit['page_anchor']}\n{hit['text']}" for hit in collected.values()]
    return "\n\n".join(blocks)
```

**页锚保真硬护栏（红线，务必照此实现）**：每个组装出的 block 显式以 `hit["page_anchor"]`
（`rag.search()` 已算好的 `"【第 N 页】"` / `"【第 N-M 页】"`）打头，**不依赖**章节跨度原文里
恰好包含内联 `【第N页】` 标记——章节标题所在页的锚点行完全可能落在该章节 span 之外（锚点在
标题前一行）。显式前缀是双保险：内联锚点仍会随 `hit["text"]` 原样带出（未被改写一个字），
显式前缀确保**即使内联锚点缺失，模型也总能看到该 chunk 的页码出处**。这是"检索式精简不能丢
证据可溯源性"的唯一强制要求，测试须显式覆盖（见测试节 1-2）。

**去重**：多条 criteria 项经常命中同一章节（如"技术方案"与"技术标"多个评分子项都落在同一个
"评标办法"章）——`collected` 用 `chunk_id` 做 dict key、`setdefault` 保留首次命中顺序，同一
chunk 只出现一次。

**限制（写入设计，不是 bug）**：`_ELIGIBILITY_TAG`/`_EVALUATION_TAG` 映射依赖招标文件章节
标题命中 D6 `docstructure._TAG_KEYWORDS` 的固定关键词集合（资格审查/评标办法等常见措辞）。若
某招标文件的章节标题用词生僻到未命中任何关键词，`tag_chapter()` 会打成 `"general"`，本函数
按 `tag=evaluation_method`/`qualification_review` 过滤会查到 0 命中 → 触发条件 3 → 安全回退
全量，**不会产出错误内容，只是这份标书不吃到精简收益**——这是保守而非激进的取舍，符合"绝不
静默丢项"优先于"最大化精简率"的护栏要求。

### 3. `server/tender/runner.py` 改动（新增 + 3 行派发，flag off 零字节变化）

```python
# 顶层新增一行标准库 import（原文件已有多处局部 `import json as _json`，本处用顶层 import
# 供新增的 _parse_stored_criteria 使用，不改动既有局部 import 写法/既有代码路径）
import json
```

```python
def _tender_slim_context_enabled() -> bool:
    """D8 底稿瘦身开关。TENDER_SLIM_CONTEXT=1 时，已知 criteria 的招标文件底稿改按 criteria
    检索相关章节喂模型；=0（默认）保持现状全量灌注——默认关闭直到部署机 harness 验证成本/
    质量不劣化（见本 design"部署机 Runbook"节）。每次动态读 env，支持灰度切换 + 测试
    monkeypatch，仿 `_tender_read_doc_layer_enabled` 先例。"""
    return os.getenv("TENDER_SLIM_CONTEXT", "0").lower() in {"1", "true", "yes"}


def _parse_stored_criteria(raw: str | None) -> dict | None:
    """解析 project_doc 里存的 criteria JSON 字符串，容忍缺失/损坏（服务 D8 精简路径专用；
    186 行附近既有的 criteria 展示注入块有自己独立的 json.loads，本函数不复用/不改动那段
    已上线且有测试覆盖的代码，降低本次改动的回归面）。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _load_doc_layer_context_slim(project_id: str, bid_id: str | None, tenant: str) -> str | None:
    """TENDER_SLIM_CONTEXT=1 时使用的变体：与 `_load_doc_layer_context` 相同的就绪性/回落
    契约（同样的 None 触发条件、同样的 try/except 安全网），额外在项目 criteria 已知时，把
    招标文件底稿替换成按 criteria 检索的精简版；投标文件底稿不变。criteria 尚未就绪
    （R1 抽取未完成/失败，或历史散单从未评标过）→ 保持招标文件全量文本，与
    `_load_doc_layer_context` 输出完全一致。"""
    if not bid_id:
        return None
    try:
        project_doc = get_project_doc(project_id, tenant)
        if project_doc is None or project_doc.get("ocr_status") != "ready":
            return None
        bid = get_bid_doc(project_id, bid_id, tenant)
        if bid is None or bid.get("ocr_status") != "ready" or not bid.get("ocr_text"):
            return None
        bidder = bid.get("bidder_name") or bid["bid_id"]
        tender_text = project_doc["ocr_text"]
        criteria = _parse_stored_criteria(project_doc.get("criteria"))
        if criteria is not None:
            slim_text = build_slim_tender_context(tender_text, criteria, file_name=project_id)
            if slim_text is not None:
                tender_text = slim_text
        parts: list[str] = [
            f"=== 招标文件底稿 ===\n{tender_text}",
            f"=== 投标文件（{bidder}）底稿 ===\n{bid['ocr_text']}",
        ]
        return "\n\n".join(parts)
    except Exception:
        logger.warning("_load_doc_layer_context_slim failed, falling back", exc_info=True)
        return None
```

调用点改动（`run_tender_evaluation` 151-160 行附近，**唯一行为分支点**）：

```python
doc_layer_text: str | None = None
if _tender_read_doc_layer_enabled() and project_id:
    if bid_id:
        await _wait_doc_layer_ready(project_id, bid_id, tenant)
    loader = _load_doc_layer_context_slim if _tender_slim_context_enabled() else (
        _load_doc_layer_context
    )
    doc_layer_text = await asyncio.to_thread(loader, project_id, bid_id, tenant)
```

`TENDER_SLIM_CONTEXT` 未设/=0 时，`loader` 恒等于 `_load_doc_layer_context`（同一个函数对象，
不是"重新实现一遍相同逻辑"）——这就是"flag off = 现有行为字节级不变"的证明方式：不是靠
"两条代码路径逻辑碰巧一样"，而是根本没有第二条路径被执行。`tests/test_tender_read_layer.py`
现有 7 个测试全部通过 `monkeypatch.setattr(runner, "_load_doc_layer_context", fake)` 注入桩，
在 flag 默认关闭下无需任何改动即应继续通过（回归证据，见验收标准）。

新增 `import` 顶部追加：

```python
from server.tender.context_slim import build_slim_tender_context
```

`get_project_doc` / `get_bid_doc` 已在文件顶部导入（27 行 `from server.stores.tender_doc_store
import get_bid_doc, get_project_doc`），新函数直接复用，无需新增导入。

### 4. 分层合规

`server/tender/context_slim.py` 只 `import server.ocr.docstructure` / `server.ocr.rag`——
tender→ocr 单向合法（`tests/test_layering.py::test_ocr_does_not_import_tender_or_audit` 只
禁止反方向，本次新增文件不触碰该守卫）。不新增/修改任何 layering 测试。

### 5. 为什么不做的三个"看起来更完备"的方案（提前说明，避免 codex 自行加戏）

- **不持久化索引**：`build_slim_tender_context` 每次评标调用都新建 `:memory:` 连接、
  重新 `build_doc_structure` + `index_document`。D7 design 曾把"`rag_store.py` 接入
  `PLATFORM_DB_FILE`、跨请求复用索引"标为"等真实生产调用方出现再决定"——本 sprint 就是那个
  调用方，但结论是**仍不做**：`build_doc_structure`/`index_document` 是纯 CPU 确定性解析，
  百页文档量级是毫秒到低个位秒级，相对评标本身的模型调用（分钟级）可忽略。加持久化索引要
  解决"跨评标复用"，但要新增缓存失效（招标文件是否变过）、多进程/多请求并发写同一 project_id
  索引等复杂度——无实测数据支持"重建索引是瓶颈"之前不加（铁律[反过度工程]）。
- **不做部分回退**（某一 criteria 项零命中时只补该项全量、其余项仍精简）：整份回退全量最简单
  最安全——一旦有一项要读全量，token 开销已经和整份全量相差无几，"混合精简+局部全量"的拼接
  逻辑复杂度换不来实质收益。
- **不引入第二个 env 开关调 `_CHUNKS_PER_QUERY`**：目前只有一个真实消费者（本函数自身），
  没有任何运维场景要求把它做成可配置项；硬编码为模块常量，需要时再按 D9/D10 先例升级为 env
  （铁律[反过度工程]：无第二消费者不加参数）。

## 影响范围

**新增**：
- `server/tender/context_slim.py`（检索式精简核心：`build_slim_tender_context` + 内部
  `_criteria_queries`）
- `tests/test_tender_context_slim.py`（`context_slim.py` 单元测试，合成 fixtures）
- `tests/test_tender_context_slim_wiring.py`（`runner.py` 接线/派发测试）

**改动**：
- `server/tender/runner.py`：顶层新增 `import json` 一行；新增
  `_tender_slim_context_enabled` / `_parse_stored_criteria` / `_load_doc_layer_context_slim`
  三个函数；`run_tender_evaluation` 内 loader 派发处约 3 行改动（见方案节 3）。

**明确不碰**（硬约束，任何一个字符都不改）：
- `server/common/contract.py` / `server/common/output_contracts.py` / `server/tender/output.py` /
  `server/tender/evidence.py` / `server/common/corpus.py`（tender-schema-split 刚落地的契约层）
- `server/tender/worker.py`（调度壳，不涉及 context 组装）
- `.claude/contracts/tender/criteria.schema.json`、`.claude/commands/tender-evaluate.md`
  （模型侧 S1-S4 指令不变——精简只改模型"读到什么"，不改模型"该怎么读/怎么判"）
- `server/ocr/docstructure.py` / `server/ocr/rag.py` / `server/stores/rag_store.py`（D6/D7 已
  交付的原语按当前公开签名直接复用，零改动）
- `server/tender/runner.py` 185-207 行既有的 criteria 展示注入块（保持不动，见方案节 3 取舍）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 页锚丢失，导致证据回查闸（S1/S3 引用页码）失真 | 每个组装 block 显式以 `hit["page_anchor"]` 打头（不依赖章节跨度原文恰好含内联锚点），双保险；测试显式断言（测试节 1-2） |
| 某一 criteria 项检索不到相关章节，被静默忽略 | 任一 query 零命中 → 整份返回 `None`，调用方回退招标文件全量文本，绝不"精简出一份缺项的假底稿" |
| criteria 尚未就绪（R1 抽取失败/进行中，或历史散单从未评标）时误用检索 | `_load_doc_layer_context_slim` 显式判断 `criteria is None` 才跳过精简，走全量——与 `_load_doc_layer_context` 输出完全一致 |
| 章节标题措辞生僻，未命中 `docstructure._TAG_KEYWORDS` 固定关键词、被打成 `general` | 已知限制，写入方案节"限制"说明；后果是该标书吃不到精简收益（回退全量），不是产出错误内容——保守而非激进 |
| flag on 后模型输出契约更易写坏（底稿改变、格式跑偏） | 已有观测手段，零新增机制：`meta.retry_count`（D1 M1 埋点）+ `server/tender/eval.py` 回归闸的运维指标——若 D8 让重试变多，指标会体现，属"部署机 Runbook"验证范围 |
| `test_tender_read_layer.py` 既有 4 类测试被新代码路径破坏 | flag 默认关闭 → `loader` 恒等于原函数对象引用，不是"重写一份相同逻辑"；既有测试逐字节不改即应通过（回归证据，见验收标准） |
| 经验性收益（成本/时延/一致性/policy_refs 合规率）codex 无法验证 | 明确列为部署机 Runbook（见下节），design 与验收标准均显式声明不在 codex 交付范围内，codex 不得在报告中声称"成本已验证下降" |

## 验收标准（codex 交付 = 全绿）

- [ ] `server/tender/context_slim.py::build_slim_tender_context(tender_text, criteria, *,
      file_name)` 签名与本设计一致；三种 `None` 触发条件（无可用 query / 无章节 / 任一检索
      零命中）全部实现且有测试覆盖。
- [ ] 每个组装出的 block 以显式 `page_anchor` 打头；至少一个测试断言精简结果包含预期
      `【第 N 页】`/`【第 N-M 页】` 锚点字符串。
- [ ] `server/tender/runner.py` 新增的三个函数 + loader 派发按方案节 3 实现；
      `TENDER_SLIM_CONTEXT` 未设或非真值时，`run_tender_evaluation` 调用的 loader 是
      `_load_doc_layer_context` 本体（同一对象，非重写逻辑）。
- [ ] `tests/test_tender_read_layer.py` 现有测试**一行不改**、全部通过（回归门，证明 flag off
      零行为变更）。
- [ ] `tests/test_tender_context_slim.py`（≥6 用例，见测试节）全绿。
- [ ] `tests/test_tender_context_slim_wiring.py`（≥5 用例，见测试节）全绿。
- [ ] 全量 `uv run pytest -q` 绿，不低于基线 **850 passed**（新增约 11 例 → 预计 861，实际
      以 codex 最终用例数为准，但不得低于 850）。
- [ ] `uv run ruff check .` 净（line-length ≤100，py312，无新增 lint 违规）。
- [ ] `server/common/contract.py` / `output_contracts.py` / `server/tender/output.py` /
      `evidence.py` / `corpus.py` / `criteria.schema.json` / `tender-evaluate.md` 均未改动
      （`git diff --stat` 核验）。
- [ ] 本 design 的"部署机 Runbook"节内容**未被 codex 声称已执行/已验证**——codex 报告只能
      说"单测证明精简算法本身正确"，不得说"成本/时延已下降"。

## 测试

### `tests/test_tender_context_slim.py`（`context_slim.py` 单元测试，≥6 用例）

fixture 风格对齐 `tests/test_rag.py`（`_body()` 拼 `"### 文件: ...\n" + text`，每测试内联构造
`criteria` dict）。

1. `test_includes_expected_chapters_and_excludes_irrelevant` — 三章节招标文件（评标办法/资格
   审查/商务条款各含独有关键词），criteria 只含引用前两章的 eligibility_rule + item；断言
   `build_slim_tender_context` 返回值含前两章独有关键词，不含"商务条款"章的独有关键词。
2. `test_preserves_page_anchors` — 多页多章节 fixture（各章不同 `【第 N 页】`）；断言返回值
   包含各命中章节对应的 `page_anchor` 字符串（复用 `test_rag.py` 的页锚断言风格）。
3. `test_returns_none_when_any_query_finds_nothing` — criteria 含一个查询词在文档中完全不
   存在的评分项；断言返回 `None`（而不是返回一份缺项的部分结果）。
4. `test_returns_none_when_document_has_no_chapters` — 招标文件纯文本无章节标题；断言返回
   `None`。
5. `test_returns_none_when_criteria_has_no_usable_queries` — criteria 的 `items`/
   `eligibility_rules` 均为空列表；断言返回 `None`。
6. `test_dedupes_chunk_shared_by_multiple_criteria_queries` — 一个 eligibility_rule 与一个
   item 的查询词都命中同一章节；断言该章节内容在返回值中只出现一次（不重复拼接）。

### `tests/test_tender_context_slim_wiring.py`（`runner.py` 接线，≥5 用例）

fixture/monkeypatch 风格对齐 `tests/test_tender_read_layer.py`（同一批 `_fake_meta` /
`_make_fake_run_command` 辅助函数可直接复用或复制一份等价版本）。

7. `test_flag_off_dispatches_original_loader` — `TENDER_SLIM_CONTEXT` 未设；
   monkeypatch `runner._load_doc_layer_context` 返回哨兵文本，monkeypatch
   `runner._load_doc_layer_context_slim` 为一旦被调用就 `raise AssertionError`；断言最终
   `context` 含哨兵文本（证明 slim loader 完全未被触碰）。
8. `test_flag_on_dispatches_slim_loader` — `monkeypatch.setenv("TENDER_SLIM_CONTEXT", "1")`；
   monkeypatch `runner._load_doc_layer_context_slim` 返回哨兵精简文本，monkeypatch
   `runner._load_doc_layer_context` 为一旦被调用就 `raise AssertionError`；断言 `context`
   含哨兵精简文本。
9. `test_load_doc_layer_context_slim_falls_back_to_full_when_criteria_missing` —
   monkeypatch `runner.get_project_doc`/`get_bid_doc` 返回 `criteria: None`、真实完整
   `ocr_text`；断言 `_load_doc_layer_context_slim` 返回值的"招标文件底稿"段落 = 原始完整
   `ocr_text`（未被精简，因为 criteria 未知）。
10. `test_load_doc_layer_context_slim_falls_back_to_full_when_slim_builder_returns_none` —
    provide 就绪 `criteria`（JSON 字符串）但工程构造成检索必然零命中（或直接
    `monkeypatch.setattr(runner, "build_slim_tender_context", lambda *a, **kw: None)`）；断言
    "招标文件底稿"段落仍是完整原文，投标文件段落不受影响。
11. `test_load_doc_layer_context_slim_uses_slim_text_when_criteria_present` — 提供真实小型
    `ocr_text`（含可识别章节）+ 真实 `criteria` dict（json 序列化存入 mock 的
    `project_doc["criteria"]`），**不** monkeypatch `build_slim_tender_context`（走真实实现）；
    断言"招标文件底稿"段落变短且不含无关章节内容，"投标文件"段落与原始 `bid["ocr_text"]`
    完全一致（未受影响）。

### 回归（不新增测试文件，跑既有文件确认不劣化）

- `tests/test_tender_read_layer.py`：全部既有用例逐字节不改，全绿。
- `uv run pytest -q`（全仓）：≥850（现基线）+ 新增 11 例。

## Tasks（T1..T6，codex 从上到下实现，TDD red→green）

1. **T1 · 先写 context_slim 单测（red）**：写完整 `tests/test_tender_context_slim.py`
   （测试节 1-6）。此时 `server/tender/context_slim.py` 不存在，测试在 collection 阶段即失败
   （red 状态确认，TDD 起点）。
2. **T2 · 实现 `server/tender/context_slim.py`**：按方案节 2 实现 `build_slim_tender_context` +
   `_criteria_queries` + 两个 tag 常量 + `_CHUNKS_PER_QUERY`。跑
   `uv run pytest tests/test_tender_context_slim.py -q` 全绿。
3. **T3 · 先写 runner 接线单测（red）**：写完整 `tests/test_tender_context_slim_wiring.py`
   （测试节 7-11）。此时 `runner.py` 尚无 `_tender_slim_context_enabled` /
   `_load_doc_layer_context_slim`，测试在 monkeypatch 目标属性时即失败（`AttributeError`，
   red 状态确认）。
4. **T4 · 改 `server/tender/runner.py`**：按方案节 3 新增顶层 `import json`、
   `_tender_slim_context_enabled` / `_parse_stored_criteria` / `_load_doc_layer_context_slim`
   三个函数，改 `run_tender_evaluation` 内 loader 派发（约 3 行）。跑
   `uv run pytest tests/test_tender_context_slim_wiring.py tests/test_tender_read_layer.py -q`
   全绿（新测试转绿 + 既有 read-layer 测试逐字节保持绿，证明 flag off 零行为变更）。
5. **T5 · 全量绿 + lint 净**：`uv run pytest -q`（全仓，确认不低于基线 850）+
   `uv run ruff check .`（净）。两条命令的实际输出作为交付证据。
6. **T6 · 自查文档/规范**：新增公开函数（`build_slim_tender_context`）docstring 完整（含
   返回值语义、None 触发条件）；确认无裸 magic number（`_CHUNKS_PER_QUERY` 等均已命名常量）；
   确认无新增 blanket `try/except`（`_load_doc_layer_context_slim` 复用既有"整函数一个
   try/except、异常即回退"模式，不逐层包裹）；行宽 ≤100。

> roadmap `items.yaml` D8 状态回写与 `.ai_state/architecture/ARCHITECTURE.md` 更新由主 agent
> 在 review + merge 后完成（对齐 D6/D7/D2 实际流程），不在 codex 的 T1-T6 任务范围内。

## 部署机 Runbook（明确排除在 codex 交付范围之外，codex 不得声称已完成）

roadmap `items.yaml` D8 原定验收标准是"复跑 `logs/s7-model-compare` harness 对比：成本、
时延、评分一致性跨度、`policy_refs` 合规率四指标均不劣化且成本显著下降"——这需要真实模型
网关调用（分钟级、每次几毛到几块钱成本），codex 在无网关凭证的隔离 worktree 里**做不到**，
也不应该做（不是"技术上难"，是"这类经验性验证本质上需要真实环境+真实成本，属于部署机
runbook，不是可以 headless 复核的确定性测试"）。

**codex 范围内**：证明"精简算法本身逻辑正确"——给定 structure + criteria，精简结果包含
预期章节、排除无关章节、页锚保真、flag off 不影响现状（本 design 全部测试节覆盖的内容）。

**用户/部署机范围**（D8 merge 后单独执行，产出另记）：
1. 在部署机 `.env` 设 `TENDER_SLIM_CONTEXT=1`，用 D1 `tender_golden_manifest.json` 对应的
   真实标书重跑评标（同一批标书跑一次 flag off 基线、一次 flag on 对照）。
2. 用 `server/tender/eval.py` 既有评分核对比四指标：成本（`cost_usd`）、时延、评分一致性
   跨度（`score_consistency`）、`policy_refs` 合规率。
3. 若四指标均不劣化且 token/成本显著下降，再考虑把 `TENDER_SLIM_CONTEXT` 默认值从 `0` 改成
   `1`（另开一个后续任务，本 sprint 不做）；若一致性跨度劣化或 `meta.retry_count`
   系统性上升，保持默认关闭，回头看是否 `_CHUNKS_PER_QUERY` 太小或 tag 映射覆盖率不足。

## 备选（放弃）

- **对投标文件（S2 侧）也做检索式精简**：放弃（本 sprint 不做，非"以后都不做"）。本 sprint
  的 MVP 范围明确限定招标文件侧——招标文件全文被每次评标重复注入是当前 token 浪费的大头
  （criteria 已知却仍整份重读），先吃这块独立可交付、独立可测的收益；投标文件因每家内容不同、
  criteria 到投标文件章节的映射不如"资格审查/评标办法"这两个 docstructure 固定标签清晰，
  复杂度更高，留 backlog（`items.yaml` 可在 D8 完成后视效果决定是否立新 item）。
- **持久化索引（真实 sqlite 文件、跨评标复用同一招标项目的索引）**：放弃，见方案节 5——
  索引构建是毫秒级 CPU 开销，相对模型调用可忽略；无实测数据支持这是瓶颈之前不加复杂度。
- **部分回退（检索不到的单项单独想办法，而非整份回退全量）**：放弃，见方案节 5——增加
  "残留全量文本该插在哪里"的拼接复杂度，收益有限（一旦有一项要全量，token 开销已经和整份
  全量相近）。
- **新增 env 控制 `_CHUNKS_PER_QUERY`**：放弃，见方案节 5——无第二消费者/无真实运维场景
  要求可调，硬编码模块常量更简单。
- **用 `TenderSlimSettings` dataclass（仿 `TenderEvalSettings`）封装开关**：放弃。本 sprint
  只有一个 bool 开关，不构成"多字段配置组"；直接一个模块级函数镜像
  `_tender_read_doc_layer_enabled` 现有先例，风格更一致、代码更少。
- **复用/重构 186-207 行既有的 criteria 展示注入块，让它和新的 `_parse_stored_criteria`
  共享同一次 `json.loads`**：放弃。那段代码已上线且有测试覆盖，其解析产出用途是"生成给模型看
  的可读展示字符串"，与本 sprint"需要 dict 对象去构造检索 query"用途不同，强行合并会让两处
  独立关注点耦合、增加对已有测试的回归风险；两次对同一小段 JSON 字符串的 `json.loads`
  性能开销可忽略。保持两条路径独立、互不影响，是本次改动"只碰精简路径本身"最小 blast radius
  的直接体现。
- **DEFER（本 sprint 明确不做，留给后续 item/部署机）**：投标文件侧检索式精简（见上）；
  S7 harness 四指标真实复测（见"部署机 Runbook"节）；`TENDER_SLIM_CONTEXT` 默认值从 0 改 1
  （待 Runbook 验证达标后再开新任务）；`_CHUNKS_PER_QUERY` 可配置化（待有真实调参场景）。

---
_参考：server/tender/runner.py（本次唯一改动的既有文件）、server/ocr/docstructure.py +
server/ocr/rag.py（D6/D7，本次复用不改动）、.claude/contracts/tender/criteria.schema.json
（检索 query 的数据来源结构）、.claude/commands/tender-evaluate.md（S1 criteria 抽取语义，
本次不改）、tests/test_tender_read_layer.py（回归门 + monkeypatch 风格样板）、
tests/test_rag.py（context_slim 单测 fixture 风格样板）、
.ai_state/roadmap/2026-07-doc-intelligence/items.yaml（D8 item + D1/D6/D7 依赖状态）、
.ai_state/sprints/2026-07-18-d7-structured-rag/design.md（D7 design，风格对齐样板，
"等真实生产调用方出现再决定怎么接"的持久化索引决策在本 design 方案节 5 首次回应）。_
