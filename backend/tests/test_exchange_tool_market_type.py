"""MARKET_TYPE (spot/futures) dynamism for the public market-data + paper paths.

Covers the gaps where data collection and paper simulation ignored MARKET_TYPE:
price/klines host selection, futures-only funding/LS ratio, the screener's
spot-vs-perpetual source+filter, and the paper reference price.

No network: httpx.AsyncClient is replaced with a fake whose .get() is driven by URL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest

from app.agents.tools import exchange_tool


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    """Async-context-manager stand-in for httpx.AsyncClient.

    ``handler(url, params) -> _FakeResponse`` decides each response; every call is
    recorded on ``calls`` for URL assertions.
    """

    calls: list[tuple[str, dict | None]] = []

    def __init__(self, handler: Callable[[str, dict | None], _FakeResponse]) -> None:
        self._handler = handler

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    async def get(self, url: str, params: dict | None = None) -> _FakeResponse:
        type(self).calls.append((url, params))
        return self._handler(url, params)


def _patch_httpx(handler: Callable[[str, dict | None], _FakeResponse]):
    _FakeClient.calls = []
    return patch.object(exchange_tool.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))


# ── _public_market_base ──────────────────────────────────────────────────────


def test_public_market_base_futures_returns_fapi_host() -> None:
    with patch.object(exchange_tool, "MARKET_TYPE", "futures"):
        base, is_spot = exchange_tool._public_market_base()
    assert base == "https://fapi.binance.com/fapi/v1"
    assert is_spot is False


def test_public_market_base_spot_returns_spot_host() -> None:
    with patch.object(exchange_tool, "MARKET_TYPE", "spot"):
        base, is_spot = exchange_tool._public_market_base()
    assert base == "https://api.binance.com/api/v3"
    assert is_spot is True


# ── get_market_data ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_market_data_futures_uses_fapi_price_endpoint() -> None:
    def handler(url: str, params: dict | None) -> _FakeResponse:
        if "ticker/price" in url:
            return _FakeResponse(200, {"price": "100.5"})
        if "premiumIndex" in url:
            return _FakeResponse(200, {"lastFundingRate": "0.0001"})
        return _FakeResponse(200, [{"longShortRatio": "1.2"}])

    with patch.object(exchange_tool, "MARKET_TYPE", "futures"), _patch_httpx(handler):
        data = await exchange_tool.get_market_data("ETHUSDT")

    price_url = _FakeClient.calls[0][0]
    assert price_url.startswith("https://fapi.binance.com/fapi/v1/ticker/price")
    assert data["price"] == 100.5
    assert "funding_rate" in data
    assert "long_short_ratio" in data


@pytest.mark.anyio
async def test_get_market_data_spot_skips_funding_and_ls_ratio() -> None:
    def handler(url: str, params: dict | None) -> _FakeResponse:
        assert "fapi.binance.com" not in url  # spot must never touch the futures host
        return _FakeResponse(200, {"price": "100.5"})

    with patch.object(exchange_tool, "MARKET_TYPE", "spot"), _patch_httpx(handler):
        data = await exchange_tool.get_market_data("ETHUSDT")

    assert _FakeClient.calls[0][0].startswith("https://api.binance.com/api/v3/ticker/price")
    assert len(_FakeClient.calls) == 1  # only the price call — no funding/LS fetch
    assert data["price"] == 100.5
    assert "funding_rate" not in data
    assert "long_short_ratio" not in data


# ── screen_usdt_symbols ──────────────────────────────────────────────────────


_TICKER_24HR = [
    {"symbol": "ETHUSDT", "quoteVolume": "9000000", "priceChangePercent": "5", "lastPrice": "100"},
    {"symbol": "XRPUSDT", "quoteVolume": "8000000", "priceChangePercent": "3", "lastPrice": "1"},
]


@pytest.mark.anyio
async def test_screen_usdt_symbols_futures_filters_perpetual_contracts() -> None:
    info = {
        "symbols": [
            {
                "symbol": "ETHUSDT",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
            },
            # Quarterly (non-perpetual) must be excluded under futures.
            {
                "symbol": "XRPUSDT",
                "baseAsset": "XRP",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "contractType": "CURRENT_QUARTER",
            },
        ]
    }

    def handler(url: str, params: dict | None) -> _FakeResponse:
        assert url.startswith("https://fapi.binance.com/fapi/v1")
        return _FakeResponse(200, info if "exchangeInfo" in url else _TICKER_24HR)

    with patch.object(exchange_tool, "MARKET_TYPE", "futures"), _patch_httpx(handler):
        result = await exchange_tool.screen_usdt_symbols(top_n=5, min_quote_volume=1_000_000)

    symbols = {c["symbol"] for c in result}
    assert "ETHUSDT" in symbols
    assert "XRPUSDT" not in symbols  # non-perpetual dropped


@pytest.mark.anyio
async def test_screen_usdt_symbols_spot_filters_spot_trading_allowed() -> None:
    info = {
        "symbols": [
            {
                "symbol": "ETHUSDT",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
            },
            {
                "symbol": "XRPUSDT",
                "baseAsset": "XRP",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": False,
            },
        ]
    }

    def handler(url: str, params: dict | None) -> _FakeResponse:
        assert url.startswith("https://api.binance.com/api/v3")
        return _FakeResponse(200, info if "exchangeInfo" in url else _TICKER_24HR)

    with patch.object(exchange_tool, "MARKET_TYPE", "spot"), _patch_httpx(handler):
        result = await exchange_tool.screen_usdt_symbols(top_n=5, min_quote_volume=1_000_000)

    symbols = {c["symbol"] for c in result}
    assert "ETHUSDT" in symbols
    assert "XRPUSDT" not in symbols  # isSpotTradingAllowed=False dropped


# ── _paper_execute ───────────────────────────────────────────────────────────


def test_paper_execute_blocks_when_price_unresolved() -> None:
    result = exchange_tool._paper_execute(
        symbol="ETHUSDT",
        side="buy",
        amount=1.0,
        price=None,
        stop_loss=None,
        take_profits=None,
    )
    assert result["execution_status"] == "BLOCKED"
    assert "no reference price" in result["error"]


def test_paper_execute_uses_provided_price_no_magic_number() -> None:
    result = exchange_tool._paper_execute(
        symbol="SOLUSDT",
        side="buy",
        amount=2.0,
        price=150.0,
        stop_loss=None,
        take_profits=None,
    )
    assert result["execution_status"] == "SUCCESS"
    assert result["executed_price"] == 150.0
