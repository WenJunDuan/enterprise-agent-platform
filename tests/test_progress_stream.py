"""思考流式：on_progress 回调链透传（command_adapter → run_agent_json）。

不调真 query；mock run_agent_json 断言 command_adapter 把 on_progress 透传下去，确保
「TextBlock → on_progress → 前端 progress」链不断，且 audit 不传时默认 None 零行为变化
（codex r4 P2 测试缺口）。
"""

from __future__ import annotations

import asyncio

import server.common.command_adapter as ca


def test_run_command_json_forwards_on_progress(monkeypatch):
    captured: dict = {}

    async def _fake_run_agent_json(prompt, **kwargs):
        captured.update(kwargs)
        return ({}, None)

    monkeypatch.setattr(ca, "run_agent_json", _fake_run_agent_json)

    def _cb(_s: str) -> None:
        pass

    asyncio.run(ca.run_command_json("tender-evaluate", "dir", schema_name="x", on_progress=_cb))
    assert captured.get("on_progress") is _cb


def test_run_command_json_on_progress_defaults_none(monkeypatch):
    captured: dict = {}

    async def _fake_run_agent_json(prompt, **kwargs):
        captured.update(kwargs)
        return ({}, None)

    monkeypatch.setattr(ca, "run_agent_json", _fake_run_agent_json)
    # audit 等调用方不传 on_progress → 透传 None，零行为变化（不影响非 tender 路径）。
    asyncio.run(ca.run_command_json("audit", "x", schema_name="x"))
    assert captured.get("on_progress") is None
