"""X2：bid_id 透传链（command_adapter → run_agent_json），仿 test_progress_stream.py。

不调真 query；mock run_agent_json 断言 command_adapter 把 bid_id 透传下去（显式具名参数，
不走 **opts，防漂进 build_options 被当 SDK 选项——同 project_id/on_progress 先例）；
audit 等调用方不传 bid_id 时默认 None，零行为变化。
"""

from __future__ import annotations

import asyncio
import inspect

import server.common.command_adapter as ca
import server.common.json_bridge as jb


def test_run_command_json_bid_id_is_explicit_param_not_opts():
    """硬红线②：bid_id 必须是显式具名参数，不走 **opts（防漂进 build_options 报未知 SDK 选项）。"""
    params = inspect.signature(ca.run_command_json).parameters
    assert "bid_id" in params
    assert params["bid_id"].default is None


def test_run_agent_json_bid_id_is_explicit_param_not_opts():
    params = inspect.signature(jb.run_agent_json).parameters
    assert "bid_id" in params
    assert params["bid_id"].default is None


def test_run_command_json_forwards_bid_id(monkeypatch):
    captured: dict = {}

    async def _fake_run_agent_json(prompt, **kwargs):
        captured.update(kwargs)
        return ({}, None)

    monkeypatch.setattr(ca, "run_agent_json", _fake_run_agent_json)

    asyncio.run(
        ca.run_command_json("tender-evaluate", "dir", schema_name="x", bid_id="bd-0001")
    )
    assert captured.get("bid_id") == "bd-0001"


def test_run_command_json_bid_id_defaults_none(monkeypatch):
    captured: dict = {}

    async def _fake_run_agent_json(prompt, **kwargs):
        captured.update(kwargs)
        return ({}, None)

    monkeypatch.setattr(ca, "run_agent_json", _fake_run_agent_json)
    # audit 等调用方不传 bid_id → 透传 None，零行为变化（不影响非 tender 路径）。
    asyncio.run(ca.run_command_json("audit", "x", schema_name="x"))
    assert captured.get("bid_id") is None
