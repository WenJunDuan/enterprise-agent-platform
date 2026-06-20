"""G3 外部企业信用工具：未配置跳过 / 配置成功 / 坏响应拒 / HTTP 错优雅降级。

不打真实外部 API——_fetch_raw 被 monkeypatch；未配置路径走 env。
"""

from __future__ import annotations

import asyncio

from server.ops import credit_api
from server.platform.config import CreditApiSettings


def _settings(url: str = "https://credit.example/api", key: str = "k") -> CreditApiSettings:
    return CreditApiSettings(url=url, key=key, timeout_seconds=10.0)


def _valid_credit() -> dict:
    return {
        "company_name": "甲方建设有限公司",
        "unified_social_credit_code": "91320000MA1234567X",
        "operating_status": "在营",
        "is_abnormal": False,
        "risk_flags": [],
    }


def test_not_configured_returns_none(monkeypatch):
    # 无 url/key → 跳过(返 None)，调用方据此保持 manual_review。
    monkeypatch.delenv("CREDIT_API_URL", raising=False)
    monkeypatch.delenv("CREDIT_API_KEY", raising=False)
    assert asyncio.run(credit_api.lookup_company_credit("甲方建设")) is None


def test_credit_api_available_reflects_config():
    assert credit_api.credit_api_available(_settings()) is True
    assert credit_api.credit_api_available(_settings(url="", key="")) is False


def test_configured_success_returns_validated(monkeypatch):
    async def fake_fetch(settings, query):
        return _valid_credit()

    monkeypatch.setattr(credit_api, "_fetch_raw", fake_fetch)
    out = asyncio.run(credit_api.lookup_company_credit("甲方建设", settings=_settings()))
    assert out is not None
    assert out["unified_social_credit_code"] == "91320000MA1234567X"


def test_configured_bad_response_returns_none(monkeypatch):
    async def fake_fetch(settings, query):
        return {"company_name": "X"}  # 缺 required → 契约校验不过

    monkeypatch.setattr(credit_api, "_fetch_raw", fake_fetch)
    assert asyncio.run(credit_api.lookup_company_credit("X", settings=_settings())) is None


def test_configured_http_error_returns_none(monkeypatch):
    async def fake_fetch(settings, query):
        raise RuntimeError("upstream 503")

    monkeypatch.setattr(credit_api, "_fetch_raw", fake_fetch)
    # 网络/HTTP 错 → 优雅降级返 None(不 crash)，调用方保持 manual_review。
    assert asyncio.run(credit_api.lookup_company_credit("X", settings=_settings())) is None
