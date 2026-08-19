"""项目名 / 项目编号的**代码侧**确定性核对（纠偏令 v2.1 三节实施补充）。

用户裁决④要求结论含"应标一致性校验"（投标声称响应的项目 ↔ 本次招标，不一致 = 投错标 =
重大发现）。该项属**确定性核对**，同时下沉到代码侧：服务端 grep 双侧底稿各自抽项目名/编号
并比对，结果注入上下文，与模型侧判定**互为校验**——单发弱模型漏此项的代价是废标级，不容单点。

三条边界：

- **抽不到就说抽不到**：标签 + 分隔符的关键行定位 + 取值形态校验。跨行、无分隔符、无数字段的
  编号一律不认。宁可如实写"未抽到"，也不猜——猜错的一条会被当成废标依据。
- **它是双保险不是闸**：任何抽取/读取失败都只让这段消失，评标照跑（见
  :func:`build_facts_precheck_block`）。
- **只读落盘底稿**：双侧文本取自 doc 层的整份底稿，不取注入用的 ``ocr_block``——证据层开启时
  后者是按项检出的**片段**，拿它抽项目名等于在残片上做废标级判断。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from server.common.corpus import normalize_text, parse_corpus
from server.tender import doc_layer

logger = logging.getLogger(__name__)

# 关键行标签。招标侧多写"项目编号"，投标函多写"招标编号"——同一事实的两种常见写法都要认。
NAME_LABELS = ("采购项目名称", "招标项目名称", "项目名称", "工程名称", "标段名称")
CODE_LABELS = ("采购项目编号", "项目编号", "招标编号", "采购编号", "工程编号", "标段编号", "项目编码")
_ALL_LABELS = NAME_LABELS + CODE_LABELS

# 标签与取值之间必须有显式分隔符：冒号、表格竖线/制表符，或两个以上空格（表格单元格间隙）。
# 只隔一个空格不算——"项目名称 及编号见下表"那样的行会被当成抽到了名称。
_SEPARATOR_RE = re.compile(r"[:：]\s*|[|｜\t]+\s*|\s{2,}")
# 取值到此为止：表格进入下一单元格，或同一行里紧接着下一个标签。
_VALUE_STOP_RE = re.compile(r"\s{2,}|[|｜\t]")
_VALUE_STRIP = " 　\"'“”‘’,，;；。、"

# 取值形态。上界防的是把整行表格当成名称，下界防的是"见前"这类占位。
_NAME_LEN = (4, 80)
_CODE_LEN = (3, 60)
_DIGIT_RE = re.compile(r"\d")
# 包含式判同一项目的最短规范化长度（防两三个字的短名互相包含）。
_MIN_CONTAINMENT_CHARS = 4


@dataclass(frozen=True)
class SideFacts:
    """一侧（招标 / 投标）抽到的项目标识事实。

    Attributes:
        name: 项目名称原文；未抽到为 ``None``。
        code: 项目编号原文；未抽到为 ``None``。
        name_source: 名称出处（文件 + 页锚），未抽到为 ``None``。
        code_source: 编号出处，未抽到为 ``None``。
    """

    name: str | None = None
    code: str | None = None
    name_source: str | None = None
    code_source: str | None = None


def _clean_value(raw: str) -> str:
    """取值清洗：切到单元格/下一标签边界，再剥装饰性标点。"""
    value = _VALUE_STOP_RE.split(raw.strip(), maxsplit=1)[0].strip(_VALUE_STRIP)
    hits = [pos for pos in (value.find(label) for label in _ALL_LABELS) if pos > 0]
    return value[: min(hits)].strip(_VALUE_STRIP) if hits else value


def _value_after(line: str, labels: tuple[str, ...]) -> str | None:
    """行内 ``标签 + 分隔符 + 取值`` 的取值；标签后没有分隔符则视为没写取值。"""
    for label in labels:
        index = line.find(label)
        if index < 0:
            continue
        rest = line[index + len(label) :]
        separator = _SEPARATOR_RE.match(rest)
        if separator is None:
            continue
        value = _clean_value(rest[separator.end() :])
        if value:
            return value
    return None


def _valid_name(value: str) -> bool:
    return _NAME_LEN[0] <= len(value) <= _NAME_LEN[1]


def _valid_code(value: str) -> bool:
    """编号必带数字段且不含空格——"详见招标公告"之类的占位不得被当成编号。"""
    return (
        _CODE_LEN[0] <= len(value) <= _CODE_LEN[1]
        and _DIGIT_RE.search(value) is not None
        and " " not in value
    )


def _provenance(segment: dict[str, Any]) -> str:
    """出处串：文件名 + 页锚页号（无可靠页号时只报文件，不编页）。"""
    page = segment.get("page")
    return f"{segment['file']} 第 {page} 页" if page else str(segment["file"])


def extract_side_facts(draft_text: str) -> SideFacts:
    """从一侧底稿抽项目名称 / 项目编号及其出处。

    按底稿协议切段（``parse_corpus`` 是文件头与页锚的唯一解析单点），逐行找关键标签；
    **先出现者胜**——名称与编号都在封面/公告页，越往后越可能是引用别的项目。

    Args:
        draft_text: 一侧的整份底稿（带 ``### 文件:`` 头与页锚）。

    Returns:
        :class:`SideFacts`；抽不到的字段为 ``None``（如实报，不猜）。
    """
    name = code = name_source = code_source = None
    for segment in parse_corpus(draft_text or ""):
        source = _provenance(segment)
        for line in segment["text"].splitlines():
            if name is None:
                value = _value_after(line, NAME_LABELS)
                if value is not None and _valid_name(value):
                    name, name_source = value, source
            if code is None:
                value = _value_after(line, CODE_LABELS)
                if value is not None and _valid_code(value):
                    code, code_source = value, source
        if name is not None and code is not None:
            break
    return SideFacts(name=name, code=code, name_source=name_source, code_source=code_source)


def _match(
    tender_value: str | None, bid_value: str | None, *, allow_containment: bool
) -> bool | None:
    """双侧同一事实是否一致；任一侧未抽到 → ``None``（"没结论"≠"不一致"）。

    名称允许包含式（投标常写"…项目（第二标段）"，按字面不等判不一致是废标级假警报）；
    编号**只认相等**——它是标识符，``ZB-2026-0011`` 与 ``ZB-2026-001`` 是两个标。
    """
    if not tender_value or not bid_value:
        return None
    left, right = normalize_text(tender_value), normalize_text(bid_value)
    if not left or not right:
        return None
    if left == right:
        return True
    if not allow_containment or min(len(left), len(right)) < _MIN_CONTAINMENT_CHARS:
        return False
    return left in right or right in left


def _as_dict(facts: SideFacts) -> dict[str, Any]:
    return {
        "name": facts.name,
        "code": facts.code,
        "source": {"name": facts.name_source, "code": facts.code_source},
    }


def compare_project_facts(tender_text: str, bid_text: str) -> dict[str, Any]:
    """双侧抽取 + 比对。

    Args:
        tender_text: 招标侧整份底稿。
        bid_text: 投标侧整份底稿。

    Returns:
        ``{"tender": {name, code, source}, "bid": {...}, "match": {"name": bool|None,
        "code": bool|None}}``；``match`` 为 ``None`` 表示有一侧未抽到、无法比对。
    """
    tender = extract_side_facts(tender_text)
    bid = extract_side_facts(bid_text)
    return {
        "tender": _as_dict(tender),
        "bid": _as_dict(bid),
        "match": {
            "name": _match(tender.name, bid.name, allow_containment=True),
            "code": _match(tender.code, bid.code, allow_containment=False),
        },
    }


_MATCH_TEXT: dict[bool | None, str] = {
    True: "一致",
    False: "**不一致**（重大发现：可能投错标，须在结论中显式处置）",
    None: "无法比对（有一侧未抽到）",
}


def _fact_text(value: str | None, source: str | None) -> str:
    return f"{value}（出处 {source}）" if value else "未抽到"


def _side_line(side: dict[str, Any]) -> str:
    return (
        f"项目名称={_fact_text(side['name'], side['source']['name'])}；"
        f"项目编号={_fact_text(side['code'], side['source']['code'])}"
    )


def facts_precheck_block(result: dict[str, Any]) -> str:
    """把核对结果渲染成注入块；双侧都抽不到时返回空串（不占注入预算）。

    投标侧取值来自**攻击者可控**的投标件，因此 :func:`_valid_name` / :func:`_valid_code`
    的形态校验兼作注入面收窄：取值恒为单行且有长度上界，行尾位置只可能是编号（必带数字段、
    不含空格）——伪造不出 ``=== 招标文件底稿 ===`` 这类块分隔标记去骗预算闸的分段。
    放宽这两条校验前先想清楚这一层。
    """
    if not any(result[side][field] for side in ("tender", "bid") for field in ("name", "code")):
        return ""
    return (
        "=== 项目一致性·代码侧核对（服务端确定性抽取，供与你的判定互验）===\n"
        f"招标侧：{_side_line(result['tender'])}\n"
        f"投标侧：{_side_line(result['bid'])}\n"
        f"比对：名称{_MATCH_TEXT[result['match']['name']]}；"
        f"编号{_MATCH_TEXT[result['match']['code']]}\n"
        "口径：本节由服务端正则抽取，抽不到即写「未抽到」，**不代表文件里没有**；"
        "以你在底稿/补证中的实际发现为准，与本节不符时以文件为准并说明分歧。\n\n"
    )


async def build_facts_precheck_block(
    project_id: str | None, bid_id: str | None, tenant: str
) -> str:
    """读双侧落盘底稿 → 核对 → 渲染注入块；任何不可用情形返回空串。

    Args:
        project_id: 招标项目 ID；缺失时不核对。
        bid_id: 当前被评标的投标文件 ID；缺失（散单/legacy）时不核对。
        tenant: 租户作用域。

    Returns:
        注入块文本；无法核对时空串——它是双保险不是闸，**绝不阻塞评标**。
    """
    if not project_id or not bid_id:
        return ""
    try:
        project_doc, bid_doc = await doc_layer.read_doc_rows(project_id, bid_id, tenant)
        result = await asyncio.to_thread(
            compare_project_facts,
            (project_doc or {}).get("ocr_text") or "",
            (bid_doc or {}).get("ocr_text") or "",
        )
    except Exception:
        # DB/解析边界：核对失败只该少一条互验事实（模型侧判定仍在），不得让评标失败。
        logger.warning(
            "tender_facts_precheck_failed",
            extra={"project_id": project_id, "bid_id": bid_id},
            exc_info=True,
        )
        return ""
    logger.info(
        "tender_facts_precheck",
        extra={"project_id": project_id, "bid_id": bid_id, "match": result["match"]},
    )
    return facts_precheck_block(result)
