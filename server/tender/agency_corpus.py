"""把双侧上传目录的语料汇集到**本次评标** case 的 ``corpus/``（A.2 补证面的可 grep 面）。

**为什么要汇集**（sprint proposals P1 首条）：Phase A 的 corpus 落在 ``doc_pipeline`` 处理的
招标/投标**上传目录**（``<tenant>/tender/<project>/<上传 request_id>/corpus/``），而评标会话
拿到的 ``corpus_root`` 是**评标提交目录**——两个不同路径。不汇集，生产 doc-layer 路径下
``TENDER_AGENCY=1`` 时模型 grep 的就是一个空目录，开关等于空转。

**为什么是复制而不是软链**：路径闸（``agent_bridge._validate_corpus_path``）对每个路径做
``os.path.realpath`` 后要求仍落在 ``corpus_root`` 内——软链到上传目录会解析到闸外，被一律
拒绝（该闸有专门的 symlink 逃逸测试）。汇集面必须由**真文件**构成。

**为什么不把 corpus_root 指到项目公共父目录**：同一项目下各家投标的上传目录是兄弟目录，
指到父目录 = A 家评标会话能 grep 到 B 家报价。本模块只取**当前 bid_id** 那一家。

**派生物纪律**（照 ``corpus_materialize`` 模块 docstring）：汇集面同样落在 case 目录内，
每次先清后建；评标 inline OCR 回落那条路径在扫描本目录前也必须先清（见 ``runner``）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server.platform.paths import PROJECT_ROOT
from server.tender import doc_layer
from server.tender.corpus_materialize import MANIFEST_NAME, clear_corpus, corpus_dir

logger = logging.getLogger(__name__)

# 汇集面的两个子目录名。分侧而不是拍平：模型可以把 Grep 的 path 指到单侧只查一半
# （子目录仍在路径闸内），噪声减半；拍平后同名文件还要改名，页锚归属就更难对。
TENDER_SIDE = "tender"
BID_SIDE = "bid"
_SIDE_LABEL = {TENDER_SIDE: "招标文件", BID_SIDE: "本投标文件"}


@dataclass(frozen=True)
class AgencyCorpus:
    """一次汇集的结果。

    Attributes:
        root: 本次评标的语料根目录（``<eval case>/corpus/``），即传给路径闸的 ``corpus_root``。
        sides: 真正落了语料的侧（``tender`` / ``bid``，按此顺序）。
        file_count: 落地的语料文件数。
    """

    root: Path
    sides: tuple[str, ...]
    file_count: int


def _source_corpus(case_path: str | None) -> Path | None:
    """doc 行里的 ``case_path`` → 该上传目录已落盘的语料目录；不可用时 ``None``。

    ``case_path`` 是 ``serialize_case_path`` 产的**项目相对串**（落在项目外时才是绝对路径），
    与 ``remove_submission_dir`` 同款还原，不依赖进程 cwd。
    """
    if not case_path:
        return None
    path = Path(case_path)
    case_dir = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    source = corpus_dir(case_dir)
    return source if source.is_dir() else None


def _overlaps(root: Path, source: Path) -> bool:
    """汇集目标与来源是否互相包含（此时清空重建会把源语料一并抹掉）。

    directory 模式允许直接提交一个已存在的目录，它可能**就是**某侧的上传目录。
    """
    return source.is_relative_to(root) or root.is_relative_to(source)


def _copy_side(source: Path, target: Path) -> list[str]:
    """复制一侧的 ``.txt`` 语料，返回落地文件名（按名排序）。

    只认常规 ``.txt`` 文件：``manifest.json`` 由本模块合并重写，符号链接一律跳过——源目录
    虽是自家派生物，其文件名却来自用户上传件（信任边界同 ``corpus_materialize`` 落盘端）。
    """
    names: list[str] = []
    for entry in sorted(source.iterdir()):
        if entry.is_symlink() or not entry.is_file() or entry.suffix != ".txt":
            continue
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry, target / entry.name)
        names.append(entry.name)
    return names


def _source_manifest(source: Path) -> dict[str, dict[str, Any]]:
    """源 manifest 按 ``corpus_file`` 索引（每页字数与 text/image/blank 从这里带过来）。"""
    manifest = source / MANIFEST_NAME
    if not manifest.is_file():
        return {}
    parsed = json.loads(manifest.read_text(encoding="utf-8"))
    return {
        entry["corpus_file"]: entry
        for entry in parsed.get("files") or []
        if isinstance(entry, dict) and entry.get("corpus_file")
    }


def _write_merged_manifest(root: Path, *, case_name: str, files: list[dict[str, Any]]) -> None:
    """写汇集面的 ``manifest.json``：与单侧落盘同名同形，只多一个 ``side`` 且 ``corpus_file``
    带子目录前缀（补证指引承诺过 root 下有这份清单，双侧汇集后它必须仍指得到真文件）。"""
    merged = {"case": case_name, "files": files}
    (root / MANIFEST_NAME).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def assemble_case_corpus(
    eval_case_root: str | Path, *, tender_case_path: str | None, bid_case_path: str | None
) -> AgencyCorpus | None:
    """把招标侧 + 本投标侧的语料汇集到 ``<eval case>/corpus/{tender,bid}/``。

    Args:
        eval_case_root: 本次评标的 case 目录（``corpus_root`` 的父目录）。
        tender_case_path: 招标层 doc 行的上传目录。
        bid_case_path: **当前被评标那一家**投标层 doc 行的上传目录。

    Returns:
        :class:`AgencyCorpus`；双侧都没有可用语料、或汇集目标与来源重叠时返回 ``None``
        （此时**不建目录**——宁可没有补证面，也不给模型一个空目录的承诺）。
    """
    root = corpus_dir(eval_case_root)
    sources = [
        (side, source)
        for side, case_path in ((TENDER_SIDE, tender_case_path), (BID_SIDE, bid_case_path))
        if (source := _source_corpus(case_path)) is not None
    ]
    if not sources:
        return None
    if any(_overlaps(root.resolve(), source) for _, source in sources):
        logger.warning(
            "tender_agency_corpus_source_is_target",
            extra={"corpus_root": str(root), "sources": [str(s) for _, s in sources]},
        )
        return None
    clear_corpus(eval_case_root)  # 幂等重建：上一轮残留不得混进本轮
    files: list[dict[str, Any]] = []
    sides: list[str] = []
    for side, source in sources:
        names = _copy_side(source, root / side)
        if not names:
            continue
        sides.append(side)
        indexed = _source_manifest(source)
        files.extend(
            {**indexed.get(name, {"source": name}), "side": side, "corpus_file": f"{side}/{name}"}
            for name in names
        )
    if not files:
        return None
    _write_merged_manifest(root, case_name=Path(eval_case_root).name, files=files)
    logger.info(
        "tender_agency_corpus_assembled",
        extra={"corpus_root": str(root), "sides": sides, "n": len(files)},
    )
    return AgencyCorpus(root=root, sides=tuple(sides), file_count=len(files))


async def prepare_agency_corpus(
    project_id: str | None, bid_id: str | None, tenant: str, eval_case_root: str | Path
) -> AgencyCorpus | None:
    """读 doc 层双侧行拿上传目录，汇集本案补证语料。

    只取**当前 bid_id** 那一家：定位不到当前家时宁可没有补证面，也绝不退而求其次拼别家语料
    （跨投标人可见性是废标级事故）。

    Args:
        project_id: 招标项目 ID；缺失（散单/legacy）时不汇集。
        bid_id: 当前被评标的投标文件 ID；缺失时不汇集。
        tenant: 租户作用域。
        eval_case_root: 本次评标的 case 目录。

    Returns:
        :class:`AgencyCorpus`，或不可用时 ``None``。
    """
    if not project_id or not bid_id:
        return None
    try:
        project_doc, bid_doc = await doc_layer.read_doc_rows(project_id, bid_id, tenant)
        return await asyncio.to_thread(
            assemble_case_corpus,
            eval_case_root,
            tender_case_path=(project_doc or {}).get("case_path"),
            bid_case_path=(bid_doc or {}).get("case_path"),
        )
    except Exception:
        # DB/文件系统边界：补证语料是增量能力，汇集失败只该少一个工具面，绝不拖垮评标。
        logger.warning(
            "tender_agency_corpus_failed",
            extra={"project_id": project_id, "bid_id": bid_id},
            exc_info=True,
        )
        return None


def agency_layout_block(corpus: AgencyCorpus) -> str:
    """双侧布局说明，追加在通用补证指引之后。

    通用指引（``corpus_materialize.agency_context_block``）说的是"每份一个 .txt"，那是单侧
    落盘时的形态。汇集面按侧分了子目录，不讲清楚模型会去 Read 根目录下并不存在的文件名，
    每一次都要白吃一记 hook deny。
    """
    sides = "、".join(f"{side}/（{_SIDE_LABEL[side]}）" for side in corpus.sides)
    return (
        f"该目录按来源分子目录：{sides}；{MANIFEST_NAME} 的 corpus_file 即相对本目录的路径"
        "（形如 tender/xxx.txt）。\n"
        "Grep 的 path 可指到某个子目录只查一侧；Read 的 file_path 必须带上子目录。\n"
    )
