"""Binance Futures Testnet adapter — TESTNET ONLY, never calls fapi.binance.com."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com")
_LIVE_URL = "https://fapi.binance.com"
_LIVE_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"

# As of 2025-12-09 Binance USDⓈ-M Futures migrated all CONDITIONAL order types
# (STOP_MARKET / TAKE_PROFIT_MARKET / STOP / TAKE_PROFIT / TRAILING_STOP_MARKET) off the
# regular order endpoint onto the Algo Order service. The old /fapi/v1/order now rejects them
# with -4120 (STOP_ORDER_SWITCH_ALGO). Conditional SL/TP orders MUST use these endpoints; the
# trigger level is `triggerPrice` (not `stopPrice`) and the response id is `algoId`.
_ALGO_ORDER_PATH = "/fapi/v1/algoOrder"
_OPEN_ALGO_ORDERS_PATH = "/fapi/v1/openAlgoOrders"
_ALL_ALGO_ORDERS_PATH = "/fapi/v1/allAlgoOrders"


def _get_credentials() -> tuple[str, str]:
    mode = os.getenv("BINANCE_ENVIRONMENT", "TESTNET").upper()
    if mode == "TESTNET":
        key = os.getenv("BINANCE_TESTNET_API_KEY", "")
        secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")
    else:
        if not _LIVE_ENABLED:
            raise RuntimeError(
                "Live trading is disabled. Set LIVE_TRADING_ENABLED=true to enable (DANGEROUS)."
            )
        key = os.getenv("BINANCE_LIVE_API_KEY", "")
        secret = os.getenv("BINANCE_LIVE_API_SECRET", "")
    return key, secret


def _sign(params: dict[str, Any], secret: str) -> str:
    query = urlencode(params)
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


class BinanceFuturesAdapter:
    """Async Binance Futures adapter. Defaults to testnet (demo-fapi.binance.com)."""

    def __init__(self) -> None:
        base = os.getenv("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com").rstrip("/")
        live_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
        if base == _LIVE_URL and not live_enabled:
            raise RuntimeError("LIVE_TRADING_ENABLED is false — cannot use live Binance URL.")
        self._base = base
        self._api_key, self._secret = _get_credentials()
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-MBX-APIKEY": self._api_key},
            timeout=15.0,
        )

    async def _get(
        self, path: str, params: dict[str, Any] | None = None, signed: bool = False
    ) -> Any:
        p = dict(params or {})
        if signed:
            p["timestamp"] = int(time.time() * 1000)
            p["signature"] = _sign(p, self._secret)
        resp = await self._client.get(path, params=p)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, params: dict[str, Any]) -> Any:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _sign(params, self._secret)
        resp = await self._client.post(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _delete(self, path: str, params: dict[str, Any]) -> Any:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _sign(params, self._secret)
        resp = await self._client.delete(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def ping(self) -> dict[str, Any]:
        return await self._get("/fapi/v1/ping")

    async def get_server_time(self) -> dict[str, Any]:
        return await self._get("/fapi/v1/time")

    async def get_exchange_info(self) -> dict[str, Any]:
        return await self._get("/fapi/v1/exchangeInfo")

    async def get_account_balance(self) -> list[dict[str, Any]]:
        return await self._get("/fapi/v2/balance", signed=True)

    async def get_mark_price(self, symbol: str) -> dict[str, Any]:
        return await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})

    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[Any]:
        return await self._get(
            "/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit}
        )

    async def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        return await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})

    async def get_long_short_ratio(
        self, symbol: str, period: str = "4h", limit: int = 12
    ) -> list[dict[str, Any]]:
        return await self._get(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": period, "limit": limit},
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return await self._get("/fapi/v1/openOrders", params, signed=True)

    async def get_position(self, symbol: str) -> list[dict[str, Any]]:
        return await self._get("/fapi/v2/positionRisk", {"symbol": symbol}, signed=True)

    async def get_order(self, symbol: str, order_id: str | int) -> dict[str, Any]:
        """Query a single order's status/fill — READ-ONLY, never places an order.

        Binance USDⓈ-M MARKET fills settle asynchronously: the synchronous POST ack from
        ``place_market_order`` frequently returns ``avgPrice="0.00000"`` / ``executedQty="0"``.
        Re-querying the order once it is FILLED returns the real ``avgPrice``/``executedQty`` so
        the fill price/qty can be captured instead of a placeholder 0.0.
        """
        return await self._get(
            "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, signed=True
        )

    async def get_income(
        self,
        symbol: str | None = None,
        income_type: str = "REALIZED_PNL",
        limit: int = 50,
        start_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read income history (default: realized PnL). READ-ONLY — never places orders.

        ``start_time`` (epoch milliseconds) bounds the query to income posted at/after a given
        moment — used to exclude a symbol's earlier, unrelated trades when attributing realised
        PnL to the position that just closed.
        """
        params: dict[str, Any] = {"incomeType": income_type, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if start_time is not None:
            params["startTime"] = start_time
        return await self._get("/fapi/v1/income", params, signed=True)

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return await self._post("/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, client_order_id: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
        }
        # H6: a deterministic newClientOrderId lets the exchange itself reject a duplicate entry
        # for the same proposal, so a retry/concurrent dispatch cannot double-open the position.
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return await self._post("/fapi/v1/order", params)

    async def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> dict[str, Any]:
        return await self._post(
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": side.upper(),
                "type": "LIMIT",
                "quantity": quantity,
                "price": price,
                "timeInForce": "GTC",
            },
        )

    @staticmethod
    def _normalize_algo_response(resp: Any) -> Any:
        """Expose the algo order id under both `algoId` and `orderId`.

        The Algo Order API returns the id as `algoId`, but existing callers read `orderId`.
        Mirroring it keeps those callers working while preserving the true `algoId` field.
        """
        if isinstance(resp, dict):
            algo_id = resp.get("algoId")
            if algo_id is not None and not resp.get("orderId"):
                resp["orderId"] = algo_id
        return resp

    async def _place_conditional_algo_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        trigger_price: float,
        reduce_only: bool = True,
        working_type: str = "MARK_PRICE",
        client_algo_id: str | None = None,
    ) -> dict[str, Any]:
        """Place a CONDITIONAL algo order (SL/TP) via /fapi/v1/algoOrder.

        One-way mode is assumed (positionSide defaults to BOTH). `reduce_only` is valid in
        one-way mode and guarantees the order can only flatten — never flip or open — a
        position. `trigger_price` is sent as `triggerPrice` (the Algo API name; the old
        `/fapi/v1/order` used `stopPrice`). `working_type` defaults to MARK_PRICE so stops
        trigger off the mark price (avoids last-price wick stop-hunts). The response is
        normalized so callers reading `orderId` keep working (it mirrors `algoId`).
        """
        params: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type,
            "quantity": quantity,
            "triggerPrice": trigger_price,
            "workingType": working_type,
            "reduceOnly": "true" if reduce_only else "false",
        }
        if client_algo_id:
            params["clientAlgoId"] = client_algo_id
        resp = await self._post(_ALGO_ORDER_PATH, params)
        return self._normalize_algo_response(resp)

    async def place_stop_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        reduce_only: bool = True,
        working_type: str = "MARK_PRICE",
        client_algo_id: str | None = None,
    ) -> dict[str, Any]:
        """Place a stop-loss (STOP_MARKET) conditional order via the Algo Order API.

        Backward-compatible signature: `stop_price` is the trigger level (sent as
        `triggerPrice`). Routes to /fapi/v1/algoOrder (the deprecated /fapi/v1/order rejects
        conditional types with -4120).
        """
        return await self._place_conditional_algo_order(
            symbol=symbol,
            side=side,
            order_type="STOP_MARKET",
            quantity=quantity,
            trigger_price=stop_price,
            reduce_only=reduce_only,
            working_type=working_type,
            client_algo_id=client_algo_id,
        )

    async def place_take_profit_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        reduce_only: bool = True,
        working_type: str = "MARK_PRICE",
        client_algo_id: str | None = None,
    ) -> dict[str, Any]:
        """Place a take-profit (TAKE_PROFIT_MARKET) conditional order via the Algo Order API.

        `stop_price` is the trigger level (sent as `triggerPrice`). Routes to
        /fapi/v1/algoOrder.
        """
        return await self._place_conditional_algo_order(
            symbol=symbol,
            side=side,
            order_type="TAKE_PROFIT_MARKET",
            quantity=quantity,
            trigger_price=stop_price,
            reduce_only=reduce_only,
            working_type=working_type,
            client_algo_id=client_algo_id,
        )

    async def place_algo_stop_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        trigger_price: float,
        reduce_only: bool = True,
        working_type: str = "MARK_PRICE",
        client_algo_id: str | None = None,
    ) -> dict[str, Any]:
        """Explicit Algo-API name for a STOP_MARKET SL (delegates to place_stop_market_order)."""
        return await self.place_stop_market_order(
            symbol, side, quantity, trigger_price, reduce_only, working_type, client_algo_id
        )

    async def place_algo_take_profit_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        trigger_price: float,
        reduce_only: bool = True,
        working_type: str = "MARK_PRICE",
        client_algo_id: str | None = None,
    ) -> dict[str, Any]:
        """Explicit Algo-API name for a TAKE_PROFIT_MARKET TP (delegates to the TP method)."""
        return await self.place_take_profit_market_order(
            symbol, side, quantity, trigger_price, reduce_only, working_type, client_algo_id
        )

    async def get_open_algo_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Open CONDITIONAL algo orders (live SL/TP triggers).

        IMPORTANT: algo orders do NOT appear in get_open_orders (/fapi/v1/openOrders). Any SL/TP
        liveness check must use this endpoint. The id field is `algoId`; status is `algoStatus`.
        """
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return await self._get(_OPEN_ALGO_ORDERS_PATH, params, signed=True)

    async def get_algo_orders(
        self, symbol: str, algo_id: int | str | None = None
    ) -> list[dict[str, Any]]:
        """All algo orders for a symbol (open + historical). Status is `algoStatus`."""
        params: dict[str, Any] = {"symbol": symbol}
        if algo_id is not None:
            params["algoId"] = algo_id
        return await self._get(_ALL_ALGO_ORDERS_PATH, params, signed=True)

    async def get_algo_order_status(self, symbol: str, algo_id: int | str) -> dict[str, Any] | None:
        """Return the algo order matching `algo_id` (open first, then history), or None."""
        for o in await self.get_open_algo_orders(symbol) or []:
            if str(o.get("algoId")) == str(algo_id):
                return o
        for o in await self.get_algo_orders(symbol, algo_id) or []:
            if str(o.get("algoId")) == str(algo_id):
                return o
        return None

    async def cancel_algo_order(
        self, algo_id: int | str | None = None, client_algo_id: str | None = None
    ) -> dict[str, Any]:
        """Cancel a CONDITIONAL algo order by `algoId` or `clientAlgoId` (one is required)."""
        if algo_id is None and not client_algo_id:
            raise ValueError("cancel_algo_order requires algo_id or client_algo_id")
        params: dict[str, Any] = {}
        if algo_id is not None:
            params["algoId"] = algo_id
        if client_algo_id:
            params["clientAlgoId"] = client_algo_id
        return await self._delete(_ALGO_ORDER_PATH, params)

    async def cancel_order(self, symbol: str, order_id: int | str) -> dict[str, Any]:
        return await self._delete("/fapi/v1/order", {"symbol": symbol, "orderId": order_id})

    async def cancel_all_open_orders(self, symbol: str) -> dict[str, Any]:
        return await self._delete("/fapi/v1/allOpenOrders", {"symbol": symbol})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> BinanceFuturesAdapter:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
