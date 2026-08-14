"""criteria 的注入块与结论回执（KD1 版本可回溯）。

从 ``server/tender/runner.py`` 纯移动而来（2026-08-14，runner.py 419 行拆分）：整函数搬家 +
import 接线，函数体、命名、注释语义逐字未改。

一个变更理由：**项目权威 criteria 的版本语义**——注入给模型的块（``_criteria_context_block``）
与结论上确定性打的 ``criteria_ref``（``_stamp_criteria_ref``）是同一件事的两端，横比闸按该 ref
判本次评标用的是哪版规则，必须一起改。
"""

from __future__ import annotations

import json
from typing import Any

from server.tender.compare_input import build_criteria_ref


def _criteria_context_block(criteria: dict[str, Any], version: str | None) -> str:
    """注入给模型的权威 criteria 块（含 KD1 版本号，供结论回引与人工回溯）。"""
    readable = json.dumps(criteria, ensure_ascii=False, indent=2)
    return (
        f"\n\n=== 已解析评分标准 criteria（版本 {version}，S1 直接采用，勿重新解析）===\n"
        f"{readable}\n"
        f"（本次评标依据的项目规则版本 criteria_version={version}；"
        "结论请照此版本判分，服务端会按该版本做跨投标人横比。）"
    )


def _stamp_criteria_ref(payload: Any, injected_version: str | None) -> None:
    """在结论上**确定性**打 ``extracted_data.criteria_ref``（KD1，不依赖模型回声）。

    注入过项目权威版本 → ``source=project``（即便模型转录快照漂移，判据也只看 ref）；
    未注入 → 按模型自解析副本记 ``self_parsed``（横比时排除并提示重评）。
    归档发生在 ``run_command_json`` 内部、早于本次打标，故 results 行里的 ref 由
    ``tender.worker`` 随后补写一次（见 ``worker._persist_criteria_ref``）。
    """
    if not isinstance(payload, dict):
        return
    extracted = payload.get("extracted_data")
    if not isinstance(extracted, dict):
        return
    ref = build_criteria_ref(injected_version, extracted.get("criteria"))
    if ref is not None:
        extracted["criteria_ref"] = ref
