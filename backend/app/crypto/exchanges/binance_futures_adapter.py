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


def _get_credentials() -> tuple[str, str]:
    mode = os.getenv("BINANCE_ENVIRONMENT", "TESTNET").upper()
    if mode == "TESTNET":
        key = os.getenv("BINANCE_TESTNET_API_KEY", "")
        secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")
    else:
        if not _LIVE_ENABLED:
            raise RuntimeError("Live trading is disabled. Set LIVE_TRADING_ENABLED=true to enable (DANGEROUS).")
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

    async def _get(self, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> Any:
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
        return await self._get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    async def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        return await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})

    async def get_long_short_ratio(self, symbol: str, period: str = "4h", limit: int = 12) -> list[dict[str, Any]]:
        return await self._get("/futures/data/globalLongShortAccountRatio", {"symbol": symbol, "period": period, "limit": limit})

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return await self._get("/fapi/v1/openOrders", params, signed=True)

    async def get_position(self, symbol: str) -> list[dict[str, Any]]:
        return await self._get("/fapi/v2/positionRisk", {"symbol": symbol}, signed=True)

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return await self._post("/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})

    async def place_market_order(self, symbol: str, side: str, quantity: float) -> dict[str, Any]:
        return await self._post("/fapi/v1/order", {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
        })

    async def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> dict[str, Any]:
        return await self._post("/fapi/v1/order", {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "quantity": quantity,
            "price": price,
            "timeInForce": "GTC",
        })

    async def place_stop_market_order(
        self, symbol: str, side: str, quantity: float, stop_price: float, reduce_only: bool = True
    ) -> dict[str, Any]:
        return await self._post("/fapi/v1/order", {
            "symbol": symbol,
            "side": side.upper(),
            "type": "STOP_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true" if reduce_only else "false",
        })

    async def place_take_profit_market_order(
        self, symbol: str, side: str, quantity: float, stop_price: float, reduce_only: bool = True
    ) -> dict[str, Any]:
        return await self._post("/fapi/v1/order", {
            "symbol": symbol,
            "side": side.upper(),
            "type": "TAKE_PROFIT_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true" if reduce_only else "false",
        })

    async def cancel_order(self, symbol: str, order_id: int | str) -> dict[str, Any]:
        return await self._delete("/fapi/v1/order", {"symbol": symbol, "orderId": order_id})

    async def cancel_all_open_orders(self, symbol: str) -> dict[str, Any]:
        return await self._delete("/fapi/v1/allOpenOrders", {"symbol": symbol})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BinanceFuturesAdapter":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
