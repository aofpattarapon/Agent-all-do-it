"""Exchange tool — wraps CCXT for paper / testnet / live trade execution."""

from __future__ import annotations

import logging
import os
import uuid as _uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EXCHANGE_MODE: str = os.getenv("EXCHANGE_MODE", "paper").lower()
MARKET_TYPE: str = os.getenv("MARKET_TYPE", "futures").lower()  # "spot" or "futures"
LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"


async def place_order(
    *,
    symbol: str,
    side: str,
    amount: float,
    order_type: str = "market",
    price: float | None = None,
    stop_loss: float | None = None,
    take_profits: list[float] | None = None,
    exchange_name: str = "binance",
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict[str, Any]:
    """Place an order. Returns a standardised execution result."""
    if EXCHANGE_MODE == "paper":
        return _paper_execute(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
        )
    if EXCHANGE_MODE == "demo":
        return await _demo_execute(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            api_key=api_key,
            api_secret=api_secret,
        )
    if EXCHANGE_MODE == "testnet":
        return await _exchange_execute(
            exchange_name=exchange_name,
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            api_key=api_key,
            api_secret=api_secret,
            sandbox=True,
        )
    if EXCHANGE_MODE == "live":
        if not LIVE_TRADING_ENABLED:
            return {
                "execution_status": "BLOCKED",
                "error": "LIVE_TRADING_ENABLED is false. Set it to true to enable live trading.",
            }
        return await _exchange_execute(
            exchange_name=exchange_name,
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            api_key=api_key,
            api_secret=api_secret,
            sandbox=False,
        )
    return {"execution_status": "ERROR", "error": f"Unknown EXCHANGE_MODE: {EXCHANGE_MODE}"}


def _paper_execute(
    *,
    symbol: str,
    side: str,
    amount: float,
    price: float | None,
    stop_loss: float | None,
    take_profits: list[float] | None,
) -> dict[str, Any]:
    """Simulate locally — no network calls, no real money."""
    if price is None:
        price = 65000.0 if "BTC" in symbol.upper() else 2500.0
    tp_list = take_profits or []
    return {
        "execution_status": "SUCCESS",
        "exchange": "paper_trade",
        "order_id": f"PAPER-{_uuid.uuid4().hex[:8].upper()}",
        "symbol": symbol,
        "side": side.upper(),
        "executed_price": price,
        "size": amount,
        "sl_order_id": f"PAPER-SL-{_uuid.uuid4().hex[:8].upper()}" if stop_loss else None,
        "tp_order_ids": [f"PAPER-TP{i + 1}-{_uuid.uuid4().hex[:6].upper()}" for i in range(len(tp_list))],
        "mode": "PAPER",
        "note": "Simulated paper trade — no real order placed.",
    }


async def _exchange_execute(
    *,
    exchange_name: str,
    symbol: str,
    side: str,
    amount: float,
    order_type: str,
    price: float | None,
    stop_loss: float | None,
    take_profits: list[float] | None,
    api_key: str | None,
    api_secret: str | None,
    sandbox: bool,
) -> dict[str, Any]:
    try:
        import ccxt.async_support as ccxt  # type: ignore[import-not-found]
    except ImportError:
        return {"execution_status": "ERROR", "error": "ccxt not installed. Run: pip install ccxt"}

    exchange_class = getattr(ccxt, exchange_name, None)
    if exchange_class is None:
        return {"execution_status": "ERROR", "error": f"Exchange '{exchange_name}' not found in ccxt"}

    if sandbox:
        resolved_key = api_key or os.getenv("BINANCE_TESTNET_API_KEY", "")
        resolved_secret = api_secret or os.getenv("BINANCE_TESTNET_API_SECRET", os.getenv("BINANCE_TESTNET_SECRET", ""))
    else:
        resolved_key = api_key or os.getenv("BINANCE_LIVE_API_KEY", "")
        resolved_secret = api_secret or os.getenv("BINANCE_LIVE_API_SECRET", "")

    exchange = exchange_class(
        {
            "apiKey": resolved_key,
            "secret": resolved_secret,
            "sandbox": sandbox,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
    )

    mode_label = "TESTNET" if sandbox else "LIVE"
    result: dict[str, Any] = {
        "execution_status": "PENDING",
        "exchange": f"{exchange_name}_{mode_label.lower()}",
        "symbol": symbol,
        "side": side.upper(),
        "sl_order_id": None,
        "tp_order_ids": [],
        "mode": mode_label,
    }

    try:
        order = await exchange.create_order(
            symbol=symbol,
            type=order_type,
            side=side.lower(),
            amount=amount,
            price=price,
        )
        result.update(
            {
                "execution_status": "SUCCESS",
                "order_id": str(order.get("id", "")),
                "executed_price": float(order.get("price") or order.get("average") or price or 0),
                "size": amount,
            }
        )

        if stop_loss:
            sl_side = "sell" if side.lower() == "buy" else "buy"
            try:
                sl_order = await exchange.create_order(
                    symbol=symbol,
                    type="stop_market",
                    side=sl_side,
                    amount=amount,
                    price=stop_loss,
                    params={"stopPrice": stop_loss, "reduceOnly": True},
                )
                result["sl_order_id"] = str(sl_order.get("id", ""))
            except Exception as exc:
                result["sl_warning"] = f"SL order failed: {exc}"
                logger.warning("SL order failed for %s: %s", symbol, exc)

        tp_size_pcts = [0.5, 0.3, 0.2]
        for i, tp_price in enumerate(take_profits or []):
            tp_side = "sell" if side.lower() == "buy" else "buy"
            tp_pct = tp_size_pcts[i] if i < len(tp_size_pcts) else 0.2
            tp_amount = round(amount * tp_pct, 6)
            try:
                tp_order = await exchange.create_order(
                    symbol=symbol,
                    type="limit",
                    side=tp_side,
                    amount=tp_amount,
                    price=tp_price,
                    params={"reduceOnly": True},
                )
                result["tp_order_ids"].append(str(tp_order.get("id", "")))
            except Exception as exc:
                result.setdefault("tp_warnings", []).append(f"TP{i + 1} order failed: {exc}")
                logger.warning("TP%d order failed for %s: %s", i + 1, symbol, exc)

    except Exception as exc:
        logger.exception("Exchange execution failed: %s", exc)
        result.update({"execution_status": "FAILED", "error": str(exc)})
    finally:
        await exchange.close()

    return result


async def _demo_execute(
    *,
    symbol: str,
    side: str,
    amount: float,
    order_type: str,
    price: float | None,
    stop_loss: float | None,
    take_profits: list[float] | None,
    api_key: str | None,
    api_secret: str | None,
) -> dict[str, Any]:
    import hashlib
    import hmac as _hmac
    import time

    resolved_key = api_key or os.getenv("BINANCE_DEMO_API_KEY", os.getenv("BINANCE_TESTNET_API_KEY", ""))
    resolved_secret = api_secret or os.getenv("BINANCE_DEMO_API_SECRET", os.getenv("BINANCE_TESTNET_API_SECRET", ""))

    if MARKET_TYPE == "spot":
        return await _spot_demo_execute(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            api_key=resolved_key,
            api_secret=resolved_secret,
        )

    # ── Futures demo (demo-fapi.binance.com via CCXT) ─────────────────────────
    try:
        import ccxt.async_support as ccxt  # type: ignore[import-not-found]
    except ImportError:
        return {"execution_status": "ERROR", "error": "ccxt not installed. Run: pip install ccxt"}

    _SPOT_BASE = "https://demo-api.binance.com"
    _FAPI_BASE = "https://demo-fapi.binance.com"
    exchange = ccxt.binanceusdm(
        {
            "apiKey": resolved_key,
            "secret": resolved_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "fetchCurrencies": False,
            },
            "urls": {
                "api": {
                    "public":        f"{_SPOT_BASE}/api/v3",
                    "private":       f"{_SPOT_BASE}/api/v3",
                    "sapi":          f"{_SPOT_BASE}/sapi/v1",
                    "fapiPublic":    f"{_FAPI_BASE}/fapi/v1",
                    "fapiPublicV2":  f"{_FAPI_BASE}/fapi/v2",
                    "fapiPublicV3":  f"{_FAPI_BASE}/fapi/v3",
                    "fapiPrivate":   f"{_FAPI_BASE}/fapi/v1",
                    "fapiPrivateV2": f"{_FAPI_BASE}/fapi/v2",
                    "fapiPrivateV3": f"{_FAPI_BASE}/fapi/v3",
                    "fapiData":      f"{_FAPI_BASE}/futures/data",
                }
            },
        }
    )

    result: dict[str, Any] = {
        "execution_status": "PENDING",
        "exchange": "binance_demo_futures",
        "symbol": symbol,
        "side": side.upper(),
        "sl_order_id": None,
        "tp_order_ids": [],
        "mode": "DEMO_FUTURES",
        "market_type": "futures",
    }

    try:
        order = await exchange.create_order(
            symbol=symbol, type=order_type, side=side.lower(), amount=amount, price=price,
        )
        result.update({
            "execution_status": "SUCCESS",
            "order_id": str(order.get("id", "")),
            "executed_price": float(order.get("price") or order.get("average") or price or 0),
            "size": amount,
        })
        if stop_loss:
            sl_side = "sell" if side.lower() == "buy" else "buy"
            try:
                sl_order = await exchange.create_order(
                    symbol=symbol, type="stop_market", side=sl_side, amount=amount,
                    price=stop_loss, params={"stopPrice": stop_loss, "reduceOnly": True},
                )
                result["sl_order_id"] = str(sl_order.get("id", ""))
            except Exception as exc:
                result["sl_warning"] = f"SL order failed: {exc}"
        tp_size_pcts = [0.5, 0.3, 0.2]
        for i, tp_price in enumerate(take_profits or []):
            tp_side = "sell" if side.lower() == "buy" else "buy"
            tp_amount = round(amount * (tp_size_pcts[i] if i < len(tp_size_pcts) else 0.2), 6)
            try:
                tp_order = await exchange.create_order(
                    symbol=symbol, type="limit", side=tp_side, amount=tp_amount,
                    price=tp_price, params={"reduceOnly": True},
                )
                result["tp_order_ids"].append(str(tp_order.get("id", "")))
            except Exception as exc:
                result.setdefault("tp_warnings", []).append(f"TP{i+1} order failed: {exc}")
    except Exception as exc:
        logger.exception("Demo futures execution failed: %s", exc)
        result.update({"execution_status": "FAILED", "error": str(exc)})
    finally:
        await exchange.close()

    return result


async def _spot_demo_execute(
    *,
    symbol: str,
    side: str,
    amount: float,
    order_type: str,
    price: float | None,
    stop_loss: float | None,
    take_profits: list[float] | None,
    api_key: str,
    api_secret: str,
) -> dict[str, Any]:
    """Spot demo via direct signed httpx — bypasses CCXT market-loading (demo lacks margin endpoints)."""
    import hashlib
    import hmac as _hmac
    import time

    _BASE = "https://demo-api.binance.com"
    clean = symbol.replace("/", "").upper()

    def _sign(params: dict[str, Any]) -> str:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return _hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    result: dict[str, Any] = {
        "execution_status": "PENDING",
        "exchange": "binance_demo_spot",
        "symbol": symbol,
        "side": side.upper(),
        "sl_order_id": None,
        "tp_order_ids": [],
        "mode": "DEMO_SPOT",
        "market_type": "spot",
    }

    async with httpx.AsyncClient(
        base_url=_BASE,
        headers={"X-MBX-APIKEY": api_key},
        timeout=15,
    ) as client:
        try:
            # ── Main entry order ─────────────────────────────────────────────
            ts = int(time.time() * 1000)
            order_params: dict[str, Any] = {
                "symbol": clean,
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": str(round(amount, 6)),
                "timestamp": ts,
                "recvWindow": 10000,
            }
            if order_type.lower() == "limit" and price:
                order_params["price"] = str(price)
                order_params["timeInForce"] = "GTC"
            order_params["signature"] = _sign(order_params)

            resp = await client.post("/api/v3/order", params=order_params)
            resp.raise_for_status()
            order = resp.json()

            fills = order.get("fills", [])
            avg_price: float = price or 0
            if fills:
                total_qty = sum(float(f["qty"]) for f in fills)
                avg_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty if total_qty else 0

            result.update({
                "execution_status": "SUCCESS",
                "order_id": str(order.get("orderId", "")),
                "executed_price": avg_price,
                "size": amount,
                "order_status": order.get("status", ""),
            })

            # ── Stop loss (STOP_LOSS_LIMIT) ──────────────────────────────────
            if stop_loss:
                sl_side = "SELL" if side.upper() == "BUY" else "BUY"
                sl_limit = round(stop_loss * 0.995 if sl_side == "SELL" else stop_loss * 1.005, 2)
                ts = int(time.time() * 1000)
                sl_params: dict[str, Any] = {
                    "symbol": clean,
                    "side": sl_side,
                    "type": "STOP_LOSS_LIMIT",
                    "quantity": str(round(amount, 6)),
                    "price": str(sl_limit),
                    "stopPrice": str(stop_loss),
                    "timeInForce": "GTC",
                    "timestamp": ts,
                    "recvWindow": 10000,
                }
                sl_params["signature"] = _sign(sl_params)
                try:
                    sl_resp = await client.post("/api/v3/order", params=sl_params)
                    sl_resp.raise_for_status()
                    result["sl_order_id"] = str(sl_resp.json().get("orderId", ""))
                except Exception as exc:
                    result["sl_warning"] = f"SL order failed: {exc}"
                    logger.warning("SL order failed for %s: %s", symbol, exc)

            # ── Take profits (LIMIT) ─────────────────────────────────────────
            tp_size_pcts = [0.5, 0.3, 0.2]
            for i, tp_price in enumerate(take_profits or []):
                tp_side = "SELL" if side.upper() == "BUY" else "BUY"
                tp_pct = tp_size_pcts[i] if i < len(tp_size_pcts) else 0.2
                tp_qty = round(amount * tp_pct, 6)
                ts = int(time.time() * 1000)
                tp_params: dict[str, Any] = {
                    "symbol": clean,
                    "side": tp_side,
                    "type": "LIMIT",
                    "quantity": str(tp_qty),
                    "price": str(tp_price),
                    "timeInForce": "GTC",
                    "timestamp": ts,
                    "recvWindow": 10000,
                }
                tp_params["signature"] = _sign(tp_params)
                try:
                    tp_resp = await client.post("/api/v3/order", params=tp_params)
                    tp_resp.raise_for_status()
                    result["tp_order_ids"].append(str(tp_resp.json().get("orderId", "")))
                except Exception as exc:
                    result.setdefault("tp_warnings", []).append(f"TP{i+1} order failed: {exc}")
                    logger.warning("TP%d order failed for %s: %s", i + 1, symbol, exc)

        except Exception as exc:
            logger.exception("Spot demo execution failed: %s", exc)
            result.update({"execution_status": "FAILED", "error": str(exc)})

    return result


async def get_market_data(symbol: str, exchange_name: str = "binance") -> dict[str, Any]:
    """Fetch price, funding rate, and long/short ratio from public APIs."""
    clean = symbol.replace("/", "").upper()
    data: dict[str, Any] = {"symbol": symbol, "exchange": exchange_name, "errors": []}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            price_resp = await client.get(f"https://api.binance.com/api/v3/ticker/price?symbol={clean}")
            if price_resp.status_code == 200:
                data["price"] = float(price_resp.json().get("price", 0))

            funding_resp = await client.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={clean}")
            if funding_resp.status_code == 200:
                data["funding_rate"] = float(funding_resp.json().get("lastFundingRate", 0))

            ratio_resp = await client.get(
                "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                params={"symbol": clean, "period": "5m", "limit": 1},
            )
            if ratio_resp.status_code == 200 and ratio_resp.json():
                data["long_short_ratio"] = float(ratio_resp.json()[0].get("longShortRatio", 1))
    except Exception as exc:
        data["errors"].append(str(exc))
        logger.warning("get_market_data error for %s: %s", symbol, exc)
    return data


async def get_fear_greed() -> dict[str, Any]:
    """Fetch Fear & Greed index from alternative.me."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://api.alternative.me/fng/?limit=1")
            if response.status_code == 200:
                item = response.json().get("data", [{}])[0]
                return {
                    "value": int(item.get("value", 50)),
                    "label": item.get("value_classification", "Neutral"),
                    "timestamp": item.get("timestamp"),
                }
    except Exception as exc:
        logger.warning("get_fear_greed failed: %s", exc)
    return {"value": 50, "label": "Neutral", "timestamp": None, "error": "fetch_failed"}
