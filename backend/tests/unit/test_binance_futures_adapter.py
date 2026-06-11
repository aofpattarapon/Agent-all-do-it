"""Unit tests for BinanceFuturesAdapter — HTTP calls mocked."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com")
os.environ.setdefault("BINANCE_ENVIRONMENT", "TESTNET")
os.environ.setdefault("BINANCE_TESTNET_API_KEY", "test-key")
os.environ.setdefault("BINANCE_TESTNET_API_SECRET", "test-secret")
os.environ.setdefault("LIVE_TRADING_ENABLED", "false")

from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter  # noqa: E402


def _make_adapter() -> BinanceFuturesAdapter:
    adapter = BinanceFuturesAdapter.__new__(BinanceFuturesAdapter)
    adapter._base = "https://demo-fapi.binance.com"
    adapter._api_key = "test-key"
    adapter._secret = "test-secret"
    adapter._client = MagicMock()
    return adapter


async def _mock_response(data: object) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=data)
    return resp


@pytest.mark.anyio
async def test_ping_returns_empty_dict() -> None:
    adapter = _make_adapter()
    adapter._client.get = AsyncMock(return_value=await _mock_response({}))
    result = await adapter.ping()
    assert result == {}
    adapter._client.get.assert_called_once()


@pytest.mark.anyio
async def test_get_server_time_returns_server_time() -> None:
    adapter = _make_adapter()
    payload = {"serverTime": 1700000000000}
    adapter._client.get = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.get_server_time()
    assert result["serverTime"] == 1700000000000


@pytest.mark.anyio
async def test_get_mark_price_returns_mark_price() -> None:
    adapter = _make_adapter()
    payload = {"symbol": "BTCUSDT", "markPrice": "65000.0"}
    adapter._client.get = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.get_mark_price("BTCUSDT")
    assert result["markPrice"] == "65000.0"


@pytest.mark.anyio
async def test_get_klines_returns_list() -> None:
    adapter = _make_adapter()
    payload = [[1700000000000, "65000", "66000", "64000", "65500", "100"]]
    adapter._client.get = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.get_klines("BTCUSDT", "4h", 100)
    assert isinstance(result, list)
    assert len(result) == 1


@pytest.mark.anyio
async def test_place_market_order_sends_correct_params() -> None:
    adapter = _make_adapter()
    payload = {"orderId": 12345, "status": "FILLED", "avgPrice": "65000.0"}
    adapter._client.post = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.place_market_order("BTCUSDT", "BUY", 0.001)
    assert result["orderId"] == 12345
    call_params = adapter._client.post.call_args
    params = call_params[1]["params"] if "params" in call_params[1] else call_params[0][1]
    assert params.get("symbol") == "BTCUSDT"
    assert params.get("side") == "BUY"
    assert params.get("type") == "MARKET"


@pytest.mark.anyio
async def test_place_stop_market_order_is_reduce_only() -> None:
    adapter = _make_adapter()
    payload = {"orderId": 99999, "type": "STOP_MARKET"}
    adapter._client.post = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.place_stop_market_order("BTCUSDT", "SELL", 0.001, 60000.0, reduce_only=True)
    assert result["orderId"] == 99999
    call_params = adapter._client.post.call_args
    params = call_params[1]["params"] if "params" in call_params[1] else call_params[0][1]
    assert params.get("reduceOnly") == "true"
    assert params.get("stopPrice") == 60000.0


@pytest.mark.anyio
async def test_get_account_balance_requires_signature() -> None:
    adapter = _make_adapter()
    payload = [{"asset": "USDT", "balance": "1000.0"}]
    adapter._client.get = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.get_account_balance()
    assert isinstance(result, list)
    call_params = adapter._client.get.call_args
    params = call_params[1]["params"] if "params" in call_params[1] else call_params[0][1]
    assert "signature" in params
    assert "timestamp" in params


@pytest.mark.anyio
async def test_cancel_all_open_orders() -> None:
    adapter = _make_adapter()
    payload = {"code": 200, "msg": ""}
    adapter._client.delete = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.cancel_all_open_orders("BTCUSDT")
    assert result["code"] == 200


def test_live_url_blocked_when_live_disabled() -> None:
    with patch.dict(os.environ, {"BINANCE_FUTURES_BASE_URL": "https://fapi.binance.com", "LIVE_TRADING_ENABLED": "false"}):
        with pytest.raises(RuntimeError, match="LIVE_TRADING_ENABLED"):
            BinanceFuturesAdapter()
