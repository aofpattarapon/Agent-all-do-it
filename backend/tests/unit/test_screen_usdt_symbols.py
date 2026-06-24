"""Unit tests for screen_usdt_symbols — HTTP calls mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.tools.exchange_tool import screen_usdt_symbols

_EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        },
        {
            "symbol": "ETHUSDT",
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        },
        {
            "symbol": "SOLUSDT",
            "baseAsset": "SOL",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        },
        # Leveraged token — must be excluded.
        {
            "symbol": "BTCUPUSDT",
            "baseAsset": "BTCUP",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        },
        # Stablecoin base — must be excluded.
        {
            "symbol": "USDCUSDT",
            "baseAsset": "USDC",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        },
        # Non-USDT quote — must be excluded.
        {
            "symbol": "ETHBTC",
            "baseAsset": "ETH",
            "quoteAsset": "BTC",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        },
        # Not trading — must be excluded.
        {
            "symbol": "FOOUSDT",
            "baseAsset": "FOO",
            "quoteAsset": "USDT",
            "status": "BREAK",
            "isSpotTradingAllowed": True,
        },
    ]
}

_TICKER_24HR = [
    {
        "symbol": "BTCUSDT",
        "quoteVolume": "1000000000",
        "priceChangePercent": "2.0",
        "lastPrice": "65000",
    },
    {
        "symbol": "ETHUSDT",
        "quoteVolume": "500000000",
        "priceChangePercent": "5.0",
        "lastPrice": "3500",
    },
    {
        "symbol": "SOLUSDT",
        "quoteVolume": "1000000",
        "priceChangePercent": "10.0",
        "lastPrice": "150",
    },  # below min volume
    {
        "symbol": "BTCUPUSDT",
        "quoteVolume": "999999999",
        "priceChangePercent": "1.0",
        "lastPrice": "30",
    },
    {
        "symbol": "USDCUSDT",
        "quoteVolume": "999999999",
        "priceChangePercent": "0.0",
        "lastPrice": "1",
    },
]


def _resp(data: object) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=data)
    return resp


class _FakeClient:
    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, *args: object, **kwargs: object) -> MagicMock:
        if "exchangeInfo" in url:
            return _resp(_EXCHANGE_INFO)
        return _resp(_TICKER_24HR)


@pytest.mark.anyio
async def test_screen_filters_and_ranks() -> None:
    # Fixtures describe the spot market (isSpotTradingAllowed); pin MARKET_TYPE=spot.
    with (
        patch("app.agents.tools.exchange_tool.MARKET_TYPE", "spot"),
        patch("app.agents.tools.exchange_tool.httpx.AsyncClient", return_value=_FakeClient()),
    ):
        result = await screen_usdt_symbols(top_n=5, min_quote_volume=5_000_000)

    symbols = [c["symbol"] for c in result]
    # Leveraged, stablecoin, non-USDT, non-trading, and low-volume pairs excluded.
    assert symbols == ["BTCUSDT", "ETHUSDT"]
    assert "BTCUPUSDT" not in symbols
    assert "USDCUSDT" not in symbols
    assert "ETHBTC" not in symbols
    assert "SOLUSDT" not in symbols  # below min volume


@pytest.mark.anyio
async def test_screen_respects_top_n() -> None:
    with (
        patch("app.agents.tools.exchange_tool.MARKET_TYPE", "spot"),
        patch("app.agents.tools.exchange_tool.httpx.AsyncClient", return_value=_FakeClient()),
    ):
        result = await screen_usdt_symbols(top_n=1, min_quote_volume=5_000_000)
    assert len(result) == 1
    assert result[0]["symbol"] == "BTCUSDT"  # highest liquidity x momentum score


@pytest.mark.anyio
async def test_screen_blacklist_excludes_symbol() -> None:
    with (
        patch("app.agents.tools.exchange_tool.MARKET_TYPE", "spot"),
        patch("app.agents.tools.exchange_tool.httpx.AsyncClient", return_value=_FakeClient()),
    ):
        result = await screen_usdt_symbols(
            top_n=5, min_quote_volume=5_000_000, blacklist=["BTCUSDT"]
        )
    symbols = [c["symbol"] for c in result]
    assert "BTCUSDT" not in symbols
    assert symbols == ["ETHUSDT"]
