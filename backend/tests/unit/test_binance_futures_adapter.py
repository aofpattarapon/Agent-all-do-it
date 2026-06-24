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

from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter


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


def _post_path_and_params(adapter: BinanceFuturesAdapter) -> tuple[str, dict]:
    """Extract (path, params) from the last mocked _client.post call.

    `_post` calls `self._client.post(path, params=params)`, so the path is the first
    positional arg and params is the `params` kwarg.
    """
    call = adapter._client.post.call_args
    path = call.args[0] if call.args else call.kwargs.get("path")
    params = call.kwargs.get("params") if "params" in call.kwargs else call.args[1]
    return str(path), dict(params)


@pytest.mark.anyio
async def test_place_stop_market_order_uses_algo_endpoint_with_trigger_price() -> None:
    """SL must route to the Algo Order API (/fapi/v1/algoOrder), NOT /fapi/v1/order, using
    algoType=CONDITIONAL + triggerPrice (the post-2025-12 migration; old endpoint returns -4120)."""
    adapter = _make_adapter()
    # Algo API returns the id as `algoId` (not `orderId`).
    payload = {"algoId": 99999, "orderType": "STOP_MARKET", "algoStatus": "NEW"}
    adapter._client.post = AsyncMock(return_value=await _mock_response(payload))

    result = await adapter.place_stop_market_order(
        "BTCUSDT", "SELL", 0.001, 60000.0, reduce_only=True
    )

    path, params = _post_path_and_params(adapter)
    assert path == "/fapi/v1/algoOrder"
    assert path != "/fapi/v1/order"
    assert params.get("algoType") == "CONDITIONAL"
    assert params.get("type") == "STOP_MARKET"
    assert params.get("side") == "SELL"
    assert params.get("triggerPrice") == 60000.0
    assert "stopPrice" not in params  # renamed to triggerPrice on the algo endpoint
    assert params.get("reduceOnly") == "true"
    assert params.get("workingType") == "MARK_PRICE"
    # One-way mode: positionSide is not forced (defaults to BOTH server-side).
    assert params.get("positionSide") in (None, "BOTH")
    # Response is normalized so callers reading `orderId` keep working (mirrors `algoId`).
    assert result["algoId"] == 99999
    assert result["orderId"] == 99999


@pytest.mark.anyio
async def test_place_take_profit_market_order_uses_algo_endpoint() -> None:
    adapter = _make_adapter()
    payload = {"algoId": 88888, "orderType": "TAKE_PROFIT_MARKET"}
    adapter._client.post = AsyncMock(return_value=await _mock_response(payload))

    result = await adapter.place_take_profit_market_order("BTCUSDT", "SELL", 0.001, 70000.0)

    path, params = _post_path_and_params(adapter)
    assert path == "/fapi/v1/algoOrder"
    assert params.get("algoType") == "CONDITIONAL"
    assert params.get("type") == "TAKE_PROFIT_MARKET"
    assert params.get("triggerPrice") == 70000.0
    assert result["orderId"] == 88888  # algoId mirrored to orderId


@pytest.mark.anyio
async def test_entry_market_order_still_uses_regular_order_endpoint() -> None:
    """The entry MARKET order is NOT a conditional type — it stays on /fapi/v1/order."""
    adapter = _make_adapter()
    payload = {"orderId": 12345, "status": "FILLED", "avgPrice": "65000.0"}
    adapter._client.post = AsyncMock(return_value=await _mock_response(payload))

    await adapter.place_market_order("BTCUSDT", "BUY", 0.001)

    path, params = _post_path_and_params(adapter)
    assert path == "/fapi/v1/order"
    assert params.get("type") == "MARKET"


@pytest.mark.anyio
async def test_place_algo_aliases_route_to_algo_endpoint() -> None:
    adapter = _make_adapter()
    adapter._client.post = AsyncMock(return_value=await _mock_response({"algoId": 1}))
    await adapter.place_algo_stop_market_order("BTCUSDT", "SELL", 0.001, 60000.0)
    path, params = _post_path_and_params(adapter)
    assert path == "/fapi/v1/algoOrder"
    assert params.get("type") == "STOP_MARKET"

    adapter._client.post = AsyncMock(return_value=await _mock_response({"algoId": 2}))
    await adapter.place_algo_take_profit_market_order("BTCUSDT", "SELL", 0.001, 70000.0)
    path, params = _post_path_and_params(adapter)
    assert path == "/fapi/v1/algoOrder"
    assert params.get("type") == "TAKE_PROFIT_MARKET"


@pytest.mark.anyio
async def test_get_open_algo_orders_hits_algo_endpoint_signed() -> None:
    adapter = _make_adapter()
    payload = [{"algoId": 5, "symbol": "BTCUSDT", "algoStatus": "NEW"}]
    adapter._client.get = AsyncMock(return_value=await _mock_response(payload))
    result = await adapter.get_open_algo_orders("BTCUSDT")
    assert result[0]["algoId"] == 5
    call = adapter._client.get.call_args
    path = call.args[0] if call.args else call.kwargs.get("path")
    params = call.kwargs.get("params") if "params" in call.kwargs else call.args[1]
    assert path == "/fapi/v1/openAlgoOrders"
    assert "signature" in params and "timestamp" in params  # USER_DATA endpoint must be signed


@pytest.mark.anyio
async def test_cancel_algo_order_uses_delete_on_algo_endpoint() -> None:
    adapter = _make_adapter()
    adapter._client.delete = AsyncMock(
        return_value=await _mock_response({"algoId": 7, "code": 200})
    )
    result = await adapter.cancel_algo_order(algo_id=7)
    assert result["algoId"] == 7
    call = adapter._client.delete.call_args
    path = call.args[0] if call.args else call.kwargs.get("path")
    params = call.kwargs.get("params") if "params" in call.kwargs else call.args[1]
    assert path == "/fapi/v1/algoOrder"
    assert params.get("algoId") == 7


@pytest.mark.anyio
async def test_cancel_algo_order_requires_an_id() -> None:
    adapter = _make_adapter()
    with pytest.raises(ValueError, match="algo_id or client_algo_id"):
        await adapter.cancel_algo_order()


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
    with (
        patch.dict(
            os.environ,
            {
                "BINANCE_FUTURES_BASE_URL": "https://fapi.binance.com",
                "LIVE_TRADING_ENABLED": "false",
            },
        ),
        pytest.raises(RuntimeError, match="LIVE_TRADING_ENABLED"),
    ):
        BinanceFuturesAdapter()
