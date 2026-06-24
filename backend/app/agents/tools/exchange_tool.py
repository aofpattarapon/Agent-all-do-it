"""Exchange tool — wraps CCXT for paper / testnet / live trade execution."""

from __future__ import annotations

import logging
import os
import uuid as _uuid
from typing import Any

import httpx

from app.services.exchange_routing import (
    resolve_demo_credentials,
    resolve_exchange_profile,
    validate_demo_routing,
)
from app.services.trading_mode import resolve_trading_mode

logger = logging.getLogger(__name__)

EXCHANGE_MODE: str = os.getenv("EXCHANGE_MODE", "paper").lower()
MARKET_TYPE: str = os.getenv("MARKET_TYPE", "futures").lower()  # "spot" or "futures"
LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"


async def validate_order_request(
    *,
    symbol: str,
    side: str,
    amount: float,
    order_type: str = "market",
    price: float | None = None,
    stop_loss: float | None = None,
    take_profits: list[float] | None = None,
    notional_usdt: float | None = None,
) -> dict[str, Any]:
    """Deterministic preflight for order submission."""
    errors: list[str] = []
    clean_symbol = symbol.replace("/", "").upper().strip()
    normalized_side = side.upper().strip()
    normalized_type = order_type.upper().strip()

    if not clean_symbol:
        errors.append("symbol is required")
    if normalized_side not in {"BUY", "SELL"}:
        errors.append(f"invalid side={side}")
    if amount <= 0:
        errors.append(f"amount must be positive, got {amount}")
    if stop_loss is not None and stop_loss <= 0:
        errors.append(f"stop_loss must be positive, got {stop_loss}")
    for idx, tp in enumerate(take_profits or [], start=1):
        if tp <= 0:
            errors.append(f"take_profit[{idx}] must be positive, got {tp}")
    if EXCHANGE_MODE == "live" and not LIVE_TRADING_ENABLED:
        errors.append("LIVE_TRADING_ENABLED is false while EXCHANGE_MODE=live")

    if MARKET_TYPE == "spot" and normalized_type == "MARKET":
        if normalized_side == "BUY" and (notional_usdt is None or notional_usdt <= 0):
            errors.append("spot BUY MARKET requires positive notional_usdt for quoteOrderQty")
        if normalized_side == "SELL" and amount <= 0:
            errors.append("spot SELL MARKET requires positive base quantity")

    if errors:
        return {
            "passed": False,
            "errors": errors,
            "exchange_mode": EXCHANGE_MODE,
            "market_type": MARKET_TYPE,
        }

    if EXCHANGE_MODE == "paper":
        return {
            "passed": True,
            "errors": [],
            "exchange_mode": EXCHANGE_MODE,
            "market_type": MARKET_TYPE,
        }

    if MARKET_TYPE == "spot" and EXCHANGE_MODE in {"demo", "testnet"}:
        profile = resolve_exchange_profile()
        async with httpx.AsyncClient(
            base_url=profile.endpoint_base.removesuffix("/api"), timeout=15
        ) as client:
            qty_for_preflight = (
                amount if not (normalized_type == "MARKET" and normalized_side == "BUY") else None
            )
            spot_errors = await _preflight_spot_order(
                client=client,
                clean_symbol=clean_symbol,
                side=normalized_side,
                order_type=normalized_type,
                quantity=qty_for_preflight,
                notional_usdt=notional_usdt,
            )
        return {
            "passed": not spot_errors,
            "errors": spot_errors,
            "exchange_mode": EXCHANGE_MODE,
            "market_type": MARKET_TYPE,
        }

    futures_errors = await _preflight_futures_order(
        clean_symbol=clean_symbol,
        quantity=amount,
        notional_usdt=notional_usdt,
    )
    return {
        "passed": not futures_errors,
        "errors": futures_errors,
        "exchange_mode": EXCHANGE_MODE,
        "market_type": MARKET_TYPE,
    }


async def place_order(
    *,
    symbol: str,
    side: str,
    amount: float,
    order_type: str = "market",
    price: float | None = None,
    stop_loss: float | None = None,
    take_profits: list[float] | None = None,
    notional_usdt: float | None = None,
    exchange_name: str = "binance",
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict[str, Any]:
    """Place an order. Returns a standardised execution result.

    Routing is driven by the *resolved* trading mode (``resolve_trading_mode()``), which
    reads the live environment and cross-checks ``TRADING_MODE`` against ``EXCHANGE_MODE``.
    This is the Phase 2B order boundary:

    * Any mode conflict (e.g. ``TRADING_MODE=PAPER`` + ``EXCHANGE_MODE=demo``) is BLOCKED
      here, before any external adapter is touched.
    * Local simulation (``PAPER``/paper) is forced to ``_paper_execute`` and can NEVER reach
      ``_demo_execute``/``_exchange_execute``/CCXT/any Binance endpoint.
    * Only an order-capable resolved mode (demo/testnet/live) routes to a real venue, and
      ``live`` additionally requires ``LIVE_TRADING_ENABLED=true``.
    """
    status = resolve_trading_mode()
    logger.info(
        "[exchange_tool] place_order resolved mode: trading_mode=%s exchange_mode=%s "
        "is_local_simulation=%s is_order_capable=%s is_live=%s",
        status.trading_mode,
        status.exchange_mode,
        status.is_local_simulation,
        status.is_order_capable,
        status.is_live,
    )
    if status.conflict:
        logger.error("[exchange_tool] BLOCKED order — trading mode conflict: %s", status.conflict)
        return {
            "execution_status": "BLOCKED",
            "error": f"Trading mode conflict — refusing to place order: {status.conflict}",
            "trading_mode": status.trading_mode,
            "exchange_mode": status.exchange_mode,
        }

    mode = status.exchange_mode
    if status.is_local_simulation:
        if price is None:
            # Use a real, market-type-aware reference price so paper P&L is meaningful
            # for any symbol — never a hardcoded guess.
            market = await get_market_data(symbol)
            price = market.get("price") or None
        return _paper_execute(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
        )
    if mode == "demo":
        routing = validate_demo_routing()
        if not routing.passed:
            return {
                "execution_status": "BLOCKED",
                "error": "Exchange routing guard failed: " + " | ".join(routing.errors),
                "routing_errors": routing.errors,
            }
        return await _demo_execute(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            notional_usdt=notional_usdt,
            api_key=api_key,
            api_secret=api_secret,
        )
    if mode == "testnet":
        if MARKET_TYPE == "spot":
            routing = validate_demo_routing()
            if not routing.passed:
                return {
                    "execution_status": "BLOCKED",
                    "error": "Exchange routing guard failed: " + " | ".join(routing.errors),
                    "routing_errors": routing.errors,
                }
            return await _demo_execute(
                symbol=symbol,
                side=side,
                amount=amount,
                order_type=order_type,
                price=price,
                stop_loss=stop_loss,
                take_profits=take_profits,
                notional_usdt=notional_usdt,
                api_key=api_key,
                api_secret=api_secret,
            )
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
    if mode == "live":
        # Read the live flag from the live environment (not the import-time constant) so a
        # freshly-configured live process is gated correctly without a code reload.
        live_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
        if not live_enabled:
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
    return {"execution_status": "ERROR", "error": f"Unknown EXCHANGE_MODE: {mode!r}"}


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
    if price is None or price <= 0:
        return {
            "execution_status": "BLOCKED",
            "exchange": "paper_trade",
            "symbol": symbol,
            "side": side.upper(),
            "mode": "PAPER",
            "error": (
                "paper execute: no reference price available for "
                f"{symbol} — cannot simulate without a real market price."
            ),
        }
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
        "tp_order_ids": [
            f"PAPER-TP{i + 1}-{_uuid.uuid4().hex[:6].upper()}" for i in range(len(tp_list))
        ],
        "mode": "PAPER",
        "note": "Simulated paper trade — no real order placed.",
    }


def _coerce_positive_float(value: Any) -> float:
    """Parse a numeric-ish value to a positive float, else 0.0.

    Binance returns prices/quantities as strings (e.g. ``"0.00000"``). A non-empty string is
    truthy in Python, so ``x.get("avgPrice") or fallback`` never falls through on ``"0.00000"`` —
    it yields ``float("0.00000") == 0.0``. This coerces and treats <= 0 (and unparseable) as 0.0
    so callers can branch on "no real fill yet" reliably.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result > 0 else 0.0


async def _resolve_fill_price_qty(
    adapter: Any, *, symbol: str, entry_order: dict[str, Any], price: float | None, amount: float
) -> tuple[float, float, str]:
    """Resolve the real entry fill price/qty, never returning 0.0 for the price.

    Order of preference (USDⓈ-M MARKET fills settle async, so the POST ack is often empty):
      1. the synchronous ack's ``avgPrice``/``executedQty`` (when already populated),
      2. a ``get_order`` re-query of the same order id (the fill once FILLED),
      3. the live position ``entryPrice`` from ``get_position`` (single-position fallback),
      4. the proposal/plan ``price`` (last resort) so we never persist 0.0.

    Returns ``(executed_price, executed_qty, source)`` where ``source`` is one of
    ``ack`` / ``order_query`` / ``position`` / ``proposal_fallback`` for audit/logging.
    """
    executed_price = _coerce_positive_float(entry_order.get("avgPrice"))
    executed_qty = _coerce_positive_float(entry_order.get("executedQty"))
    source = "ack"
    order_id = str(entry_order.get("orderId", "") or "")

    if (executed_price <= 0 or executed_qty <= 0) and order_id:
        try:
            confirmed = await adapter.get_order(symbol, order_id)
            if executed_price <= 0:
                executed_price = _coerce_positive_float(confirmed.get("avgPrice"))
            if executed_qty <= 0:
                executed_qty = _coerce_positive_float(confirmed.get("executedQty"))
            if executed_price > 0:
                source = "order_query"
        except Exception as exc:
            logger.warning(
                "[exchange_tool] fill re-query via get_order failed for %s: %s", symbol, exc
            )

    if executed_price <= 0:
        try:
            positions = await adapter.get_position(symbol)
            for pos in positions or []:
                entry = _coerce_positive_float(pos.get("entryPrice"))
                if entry > 0:
                    executed_price = entry
                    source = "position"
                    break
        except Exception as exc:
            logger.warning(
                "[exchange_tool] fill fallback via get_position failed for %s: %s", symbol, exc
            )

    if executed_price <= 0:
        executed_price = float(price or 0)
        source = "proposal_fallback"
    if executed_qty <= 0:
        executed_qty = float(amount)

    return executed_price, executed_qty, source


async def _execute_futures_via_adapter(
    *,
    symbol: str,
    side: str,
    amount: float,
    price: float | None,
    stop_loss: float | None,
    take_profits: list[float] | None,
    mode_label: str,
    exchange_label: str,
) -> dict[str, Any]:
    """Place a futures entry + protective SL/TP through the hardened ``BinanceFuturesAdapter``.

    This is the SINGLE safe implementation for Binance futures conditional orders, shared by the
    demo and testnet/live routes so there is no second order-placement path with weaker safety:

    * Entry MARKET → ``/fapi/v1/order`` (correct for MARKET).
    * SL ``STOP_MARKET`` / TP ``TAKE_PROFIT_MARKET`` → ``/fapi/v1/algoOrder`` (the Algo Order API).
      The deprecated ``/fapi/v1/order`` rejects conditional types with ``-4120``; the old CCXT
      ``create_order(type="stop_market", ...)`` route hit exactly that. No futures SL/TP order may
      use ``/fapi/v1/order``.
    * The stop-loss is a HARD BLOCK: if it cannot be confirmed the result is
      ``ENTRY_FILLED_SL_FAILED`` (never ``SUCCESS``) with ``needs_attention=True``, so no caller
      (autonomous ``run_executor`` or the API route) marks the proposal ``EXECUTED`` or opens an
      unprotected position. TP failures are non-blocking warnings — matching ``ExecutionService``.
    """
    from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter

    close_side = "SELL" if side.lower() == "buy" else "BUY"
    result: dict[str, Any] = {
        "execution_status": "PENDING",
        "exchange": exchange_label,
        "symbol": symbol,
        "side": side.upper(),
        "sl_order_id": None,
        "tp_order_ids": [],
        "mode": mode_label,
        "market_type": "futures",
    }

    try:
        async with BinanceFuturesAdapter() as adapter:
            entry_order = await adapter.place_market_order(symbol, side, amount)
            executed_price, executed_qty, fill_source = await _resolve_fill_price_qty(
                adapter, symbol=symbol, entry_order=entry_order, price=price, amount=amount
            )
            if fill_source == "proposal_fallback":
                logger.warning(
                    "[exchange_tool] could not read a real fill price for %s order %s — "
                    "falling back to proposal price %s",
                    symbol,
                    entry_order.get("orderId"),
                    executed_price,
                )
            result.update(
                {
                    "order_id": str(entry_order.get("orderId", "")),
                    "executed_price": executed_price,
                    "size": executed_qty,
                    "fill_price_source": fill_source,
                }
            )

            # Stop-loss — MANDATORY hard block. The entry has already filled, so on failure we do
            # NOT claim success: surface ENTRY_FILLED_SL_FAILED + needs_attention and stop before
            # any TP. The caller (which only persists a Position when execution_status == SUCCESS)
            # leaves the proposal un-EXECUTED so a human resolves the naked exposure.
            if stop_loss:
                try:
                    sl_order = await adapter.place_stop_market_order(
                        symbol, close_side, amount, float(stop_loss)
                    )
                    result["sl_order_id"] = str(
                        sl_order.get("algoId") or sl_order.get("orderId") or ""
                    )
                except Exception as exc:
                    logger.error(
                        "[exchange_tool] futures SL placement FAILED for %s — hard block, "
                        "no SUCCESS, position needs attention: %s",
                        symbol,
                        exc,
                    )
                    result.update(
                        {
                            "execution_status": "ENTRY_FILLED_SL_FAILED",
                            "needs_attention": True,
                            "error": f"Stop-loss order failed (hard block): {exc}",
                        }
                    )
                    return result

            # Take-profit ladder — best effort (non-blocking), Algo Order API.
            tp_size_pcts = [0.5, 0.3, 0.2]
            for i, tp_price in enumerate(take_profits or []):
                tp_pct = tp_size_pcts[i] if i < len(tp_size_pcts) else 0.2
                tp_amount = round(amount * tp_pct, 6)
                if tp_amount <= 0:
                    continue
                try:
                    tp_order = await adapter.place_take_profit_market_order(
                        symbol, close_side, tp_amount, float(tp_price)
                    )
                    result["tp_order_ids"].append(
                        str(tp_order.get("algoId") or tp_order.get("orderId") or "")
                    )
                except Exception as exc:
                    result.setdefault("tp_warnings", []).append(f"TP{i + 1} order failed: {exc}")
                    logger.warning(
                        "[exchange_tool] futures TP%d failed for %s: %s", i + 1, symbol, exc
                    )

            # SUCCESS only after entry + confirmed SL (TP is best-effort).
            result["execution_status"] = "SUCCESS"
    except Exception as exc:
        logger.exception("[exchange_tool] futures execution via adapter failed: %s", exc)
        result.update({"execution_status": "FAILED", "error": str(exc)})

    return result


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
    # Binance FUTURES (testnet/live) routes through the hardened adapter so SL/TP use the Algo
    # Order API and the stop-loss is a hard block — never the stale CCXT conditional path that
    # posts STOP_MARKET/TAKE_PROFIT_MARKET to /fapi/v1/order (-4120). Spot and any non-binance
    # exchange keep the CCXT path below (no futures Algo Order migration applies there).
    if exchange_name == "binance" and MARKET_TYPE != "spot":
        mode_label = "TESTNET" if sandbox else "LIVE"
        return await _execute_futures_via_adapter(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            mode_label=mode_label,
            exchange_label=f"{exchange_name}_{mode_label.lower()}",
        )

    try:
        import ccxt.async_support as ccxt  # type: ignore[import-not-found]
    except ImportError:
        return {"execution_status": "ERROR", "error": "ccxt not installed. Run: pip install ccxt"}

    exchange_class = getattr(ccxt, exchange_name, None)
    if exchange_class is None:
        return {
            "execution_status": "ERROR",
            "error": f"Exchange '{exchange_name}' not found in ccxt",
        }

    if sandbox:
        resolved_key = api_key or os.getenv("BINANCE_TESTNET_API_KEY", "")
        resolved_secret = api_secret or os.getenv(
            "BINANCE_TESTNET_API_SECRET", os.getenv("BINANCE_TESTNET_SECRET", "")
        )
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
    notional_usdt: float | None,
    api_key: str | None,
    api_secret: str | None,
) -> dict[str, Any]:
    # Defense in depth: _demo_execute submits a real (virtual-money) Binance demo order.
    # It must never run under local simulation or an unresolved mode conflict, even if a
    # caller reaches it directly. place_order() already gates this, but fail closed here too.
    _status = resolve_trading_mode()
    if _status.is_local_simulation or _status.conflict:
        logger.error(
            "[exchange_tool] BLOCKED _demo_execute — not order-capable "
            "(trading_mode=%s exchange_mode=%s conflict=%s)",
            _status.trading_mode,
            _status.exchange_mode,
            _status.conflict,
        )
        return {
            "execution_status": "BLOCKED",
            "error": (
                "_demo_execute refused: resolved mode is not order-capable "
                f"(trading_mode={_status.trading_mode}, exchange_mode={_status.exchange_mode}, "
                f"conflict={_status.conflict})"
            ),
        }

    _demo_key, _demo_secret = resolve_demo_credentials(MARKET_TYPE, EXCHANGE_MODE)
    resolved_key = api_key or _demo_key
    resolved_secret = api_secret or _demo_secret

    if MARKET_TYPE == "spot":
        profile = resolve_exchange_profile()
        return await _spot_demo_execute(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            notional_usdt=notional_usdt,
            api_key=resolved_key,
            api_secret=resolved_secret,
            base_url=profile.endpoint_base.removesuffix("/api"),
            mode_label=profile.exchange_mode.upper(),
        )

    # ── Futures demo (demo-fapi.binance.com) ──────────────────────────────────
    # Route through the hardened BinanceFuturesAdapter: entry MARKET on /fapi/v1/order, SL/TP on
    # the Algo Order API (/fapi/v1/algoOrder), SL enforced as a hard block. The old CCXT
    # create_order(type="stop_market", ...) path posted conditional orders to /fapi/v1/order and
    # hit -4120 while still returning SUCCESS (a naked position) — that path is gone.
    return await _execute_futures_via_adapter(
        symbol=symbol,
        side=side,
        amount=amount,
        price=price,
        stop_loss=stop_loss,
        take_profits=take_profits,
        mode_label="DEMO_FUTURES",
        exchange_label="binance_demo_futures",
    )


async def _preflight_spot_order(
    client: httpx.AsyncClient,
    clean_symbol: str,
    side: str,
    order_type: str,
    quantity: float | None,
    notional_usdt: float | None,
) -> list[str]:
    """Call /api/v3/exchangeInfo and return a list of validation errors (empty = OK)."""
    errors: list[str] = []
    try:
        ei_resp = await client.get("/api/v3/exchangeInfo", params={"symbol": clean_symbol})
        if ei_resp.status_code != 200:
            logger.warning(
                "exchangeInfo returned %s for %s — skipping preflight",
                ei_resp.status_code,
                clean_symbol,
            )
            return errors
        info = ei_resp.json()
        symbols = info.get("symbols", [])
        sym_info = next((s for s in symbols if s.get("symbol") == clean_symbol), None)
        if sym_info is None:
            errors.append(f"PREFLIGHT: symbol {clean_symbol} not found in exchangeInfo")
            return errors

        filters: dict[str, dict] = {f["filterType"]: f for f in sym_info.get("filters", [])}

        lot = filters.get("LOT_SIZE", {})
        if lot and quantity is not None:
            min_qty = float(lot.get("minQty", 0))
            max_qty = float(lot.get("maxQty", float("inf")))
            step = float(lot.get("stepSize", 0))
            if quantity < min_qty:
                errors.append(f"PREFLIGHT LOT_SIZE: quantity {quantity} < minQty {min_qty}")
            if quantity > max_qty:
                errors.append(f"PREFLIGHT LOT_SIZE: quantity {quantity} > maxQty {max_qty}")
            if step > 0:
                import math

                remainder = round(math.fmod(quantity - min_qty, step), 10)
                if remainder > 1e-9:
                    # Auto-snap down to nearest valid step; warn, don't error.
                    snapped = math.floor((quantity - min_qty) / step) * step + min_qty
                    logger.warning(
                        "PREFLIGHT LOT_SIZE spot: quantity %s snapped to %s (stepSize=%s)",
                        quantity,
                        round(snapped, 10),
                        step,
                    )

        market_lot = filters.get("MARKET_LOT_SIZE", {})
        if market_lot and order_type.upper() == "MARKET" and quantity is not None:
            min_mq = float(market_lot.get("minQty", 0))
            max_mq = float(market_lot.get("maxQty", float("inf")))
            if quantity < min_mq:
                errors.append(f"PREFLIGHT MARKET_LOT_SIZE: quantity {quantity} < minQty {min_mq}")
            if quantity > max_mq:
                errors.append(f"PREFLIGHT MARKET_LOT_SIZE: quantity {quantity} > maxQty {max_mq}")

        # NOTIONAL (newer filter) or MIN_NOTIONAL
        notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL", {})
        if notional_filter and notional_usdt is not None:
            min_notional = float(notional_filter.get("minNotional", 0))
            if notional_usdt < min_notional:
                errors.append(
                    f"PREFLIGHT NOTIONAL: notional_usdt {notional_usdt} < minNotional {min_notional}"
                )

    except Exception as exc:
        logger.warning("exchangeInfo preflight failed (non-fatal): %s", exc)
    return errors


async def _spot_demo_execute(
    *,
    symbol: str,
    side: str,
    amount: float,
    order_type: str,
    price: float | None,
    stop_loss: float | None,
    take_profits: list[float] | None,
    notional_usdt: float | None,
    api_key: str,
    api_secret: str,
    base_url: str,
    mode_label: str,
) -> dict[str, Any]:
    """Spot demo via direct signed httpx — bypasses CCXT market-loading (demo lacks margin endpoints).

    BUY MARKET orders use quoteOrderQty (USDT notional) to avoid LOT_SIZE precision issues.
    SELL MARKET orders use quantity (base asset amount).
    """
    import hashlib
    import hmac as _hmac
    import time

    clean = symbol.replace("/", "").upper()

    def _sign(params: dict[str, Any]) -> str:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return _hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _sanitize(params: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in params.items() if k != "signature"}

    result: dict[str, Any] = {
        "execution_status": "PENDING",
        "exchange": f"binance_{mode_label.lower()}_spot",
        "symbol": symbol,
        "side": side.upper(),
        "sl_order_id": None,
        "tp_order_ids": [],
        "mode": f"{mode_label}_SPOT",
        "market_type": "spot",
    }

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-MBX-APIKEY": api_key},
        timeout=15,
    ) as client:
        try:
            # ── Preflight exchangeInfo validation ────────────────────────────
            qty_for_preflight = (
                amount if not (order_type.upper() == "MARKET" and side.upper() == "BUY") else None
            )
            preflight_errors = await _preflight_spot_order(
                client=client,
                clean_symbol=clean,
                side=side.upper(),
                order_type=order_type,
                quantity=qty_for_preflight,
                notional_usdt=notional_usdt,
            )
            if preflight_errors:
                result.update(
                    {
                        "execution_status": "FAILED",
                        "error": "; ".join(preflight_errors),
                        "preflight_errors": preflight_errors,
                    }
                )
                logger.error("Spot demo preflight failed for %s: %s", symbol, preflight_errors)
                return result

            # ── Main entry order ─────────────────────────────────────────────
            ts = int(time.time() * 1000)
            is_buy_market = order_type.upper() == "MARKET" and side.upper() == "BUY"

            if is_buy_market:
                # Use quoteOrderQty (USDT) for BUY MARKET — avoids LOT_SIZE quantity precision issues.
                usdt_amount = notional_usdt or (amount * (price or 65000.0))
                order_params: dict[str, Any] = {
                    "symbol": clean,
                    "side": "BUY",
                    "type": "MARKET",
                    "quoteOrderQty": str(round(usdt_amount, 2)),
                    "timestamp": ts,
                    "recvWindow": 10000,
                }
            else:
                order_params = {
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
            if not resp.is_success:
                body = resp.text
                try:
                    err_json = resp.json()
                    err_code = err_json.get("code", resp.status_code)
                    err_msg = err_json.get("msg", body)
                except Exception:
                    err_code = resp.status_code
                    err_msg = body
                sanitized = _sanitize(order_params)
                logger.error(
                    "Spot demo order failed — HTTP %s | code=%s | msg=%s | params=%s",
                    resp.status_code,
                    err_code,
                    err_msg,
                    sanitized,
                )
                result.update(
                    {
                        "execution_status": "FAILED",
                        "error": f"Binance code={err_code}: {err_msg}",
                        "binance_code": err_code,
                        "binance_msg": err_msg,
                        "http_status": resp.status_code,
                        "request_params": sanitized,
                    }
                )
                return result

            order = resp.json()

            fills = order.get("fills", [])
            avg_price: float = price or 0.0
            if fills:
                total_qty = sum(float(f["qty"]) for f in fills)
                avg_price = (
                    sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
                    if total_qty
                    else avg_price
                )
            executed_qty = float(order.get("executedQty") or amount)

            result.update(
                {
                    "execution_status": "SUCCESS",
                    "order_id": str(order.get("orderId", "")),
                    "executed_price": avg_price,
                    "size": executed_qty,
                    "order_status": order.get("status", ""),
                }
            )

            # ── Stop loss (STOP_LOSS_LIMIT) ──────────────────────────────────
            if stop_loss:
                sl_side = "SELL" if side.upper() == "BUY" else "BUY"
                sl_limit = round(stop_loss * 0.995 if sl_side == "SELL" else stop_loss * 1.005, 2)
                ts = int(time.time() * 1000)
                sl_params: dict[str, Any] = {
                    "symbol": clean,
                    "side": sl_side,
                    "type": "STOP_LOSS_LIMIT",
                    "quantity": str(round(executed_qty, 6)),
                    "price": str(sl_limit),
                    "stopPrice": str(stop_loss),
                    "timeInForce": "GTC",
                    "timestamp": ts,
                    "recvWindow": 10000,
                }
                sl_params["signature"] = _sign(sl_params)
                try:
                    sl_resp = await client.post("/api/v3/order", params=sl_params)
                    if sl_resp.is_success:
                        result["sl_order_id"] = str(sl_resp.json().get("orderId", ""))
                    else:
                        err = (
                            sl_resp.json()
                            if sl_resp.headers.get("content-type", "").startswith(
                                "application/json"
                            )
                            else {}
                        )
                        warn = f"SL order failed: HTTP {sl_resp.status_code} code={err.get('code')} msg={err.get('msg', sl_resp.text)}"
                        result["sl_warning"] = warn
                        logger.warning(
                            "SL order failed for %s: %s | params=%s",
                            symbol,
                            warn,
                            _sanitize(sl_params),
                        )
                except Exception as exc:
                    result["sl_warning"] = f"SL order failed: {exc}"
                    logger.warning("SL order failed for %s: %s", symbol, exc)

            # ── Take profits (LIMIT) ─────────────────────────────────────────
            tp_size_pcts = [0.5, 0.3, 0.2]
            for i, tp_price in enumerate(take_profits or []):
                tp_side = "SELL" if side.upper() == "BUY" else "BUY"
                tp_pct = tp_size_pcts[i] if i < len(tp_size_pcts) else 0.2
                tp_qty = round(executed_qty * tp_pct, 6)
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
                    if tp_resp.is_success:
                        result["tp_order_ids"].append(str(tp_resp.json().get("orderId", "")))
                    else:
                        err = (
                            tp_resp.json()
                            if tp_resp.headers.get("content-type", "").startswith(
                                "application/json"
                            )
                            else {}
                        )
                        warn = f"TP{i + 1} failed: HTTP {tp_resp.status_code} code={err.get('code')} msg={err.get('msg', tp_resp.text)}"
                        result.setdefault("tp_warnings", []).append(warn)
                        logger.warning("TP%d order failed for %s: %s", i + 1, symbol, warn)
                except Exception as exc:
                    result.setdefault("tp_warnings", []).append(f"TP{i + 1} order failed: {exc}")
                    logger.warning("TP%d order failed for %s: %s", i + 1, symbol, exc)

        except Exception as exc:
            logger.exception("Spot demo execution failed: %s", exc)
            result.update({"execution_status": "FAILED", "error": str(exc)})

    return result


async def _preflight_futures_order(
    *,
    clean_symbol: str,
    quantity: float,
    notional_usdt: float | None,
) -> list[str]:
    errors: list[str] = []
    base_url = os.getenv("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com").rstrip("/")
    if EXCHANGE_MODE == "live":
        base_url = "https://fapi.binance.com"
    elif EXCHANGE_MODE == "testnet":
        base_url = os.getenv("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com").rstrip(
            "/"
        )
    elif EXCHANGE_MODE == "demo":
        base_url = "https://demo-fapi.binance.com"

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as client:
            resp = await client.get("/fapi/v1/exchangeInfo")
            if resp.status_code != 200:
                return [f"PREFLIGHT: futures exchangeInfo returned HTTP {resp.status_code}"]
            info = resp.json()
    except Exception as exc:
        return [f"PREFLIGHT: futures exchangeInfo fetch failed: {exc}"]

    symbols = info.get("symbols", [])
    sym_info = next((s for s in symbols if s.get("symbol") == clean_symbol), None)
    if sym_info is None:
        return [f"PREFLIGHT: symbol {clean_symbol} not found in futures exchangeInfo"]

    filters: dict[str, dict] = {f["filterType"]: f for f in sym_info.get("filters", [])}
    lot = filters.get("LOT_SIZE", {})
    if lot:
        min_qty = float(lot.get("minQty", 0))
        max_qty = float(lot.get("maxQty", float("inf")))
        step = float(lot.get("stepSize", 0))
        if quantity < min_qty:
            errors.append(f"PREFLIGHT LOT_SIZE: quantity {quantity} < minQty {min_qty}")
        if quantity > max_qty:
            errors.append(f"PREFLIGHT LOT_SIZE: quantity {quantity} > maxQty {max_qty}")
        if step > 0:
            import math

            remainder = round(math.fmod(quantity, step), 10)
            if remainder > 1e-9 and abs(remainder - step) > 1e-9:
                # Auto-snap down to nearest valid step; warn, don't error.
                snapped = math.floor(quantity / step) * step
                logger.warning(
                    "PREFLIGHT LOT_SIZE futures: quantity %s snapped to %s (stepSize=%s)",
                    quantity,
                    round(snapped, 10),
                    step,
                )

    market_lot = filters.get("MARKET_LOT_SIZE", {})
    if market_lot:
        min_qty = float(market_lot.get("minQty", 0))
        max_qty = float(market_lot.get("maxQty", float("inf")))
        if quantity < min_qty:
            errors.append(f"PREFLIGHT MARKET_LOT_SIZE: quantity {quantity} < minQty {min_qty}")
        if quantity > max_qty:
            errors.append(f"PREFLIGHT MARKET_LOT_SIZE: quantity {quantity} > maxQty {max_qty}")

    notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL", {})
    if notional_filter and notional_usdt is not None:
        min_notional = float(
            notional_filter.get("notional") or notional_filter.get("minNotional") or 0
        )
        max_notional = float(notional_filter.get("maxNotional") or float("inf"))
        if min_notional and notional_usdt < min_notional:
            errors.append(
                f"PREFLIGHT NOTIONAL: notional_usdt {notional_usdt} < minNotional {min_notional}"
            )
        if max_notional != float("inf") and notional_usdt > max_notional:
            errors.append(
                f"PREFLIGHT NOTIONAL: notional_usdt {notional_usdt} > maxNotional {max_notional}"
            )

    return errors


def _public_market_base() -> tuple[str, bool]:
    """Return (base_url, is_spot) for public market-data reads, selected by MARKET_TYPE.

    Production public hosts are used in every mode: they are read-only, and demo/testnet
    hosts do not serve full market data. SL/TP and screening must reference the real market.
    """
    if MARKET_TYPE == "spot":
        return "https://api.binance.com/api/v3", True
    return "https://fapi.binance.com/fapi/v1", False


async def get_market_data(symbol: str, exchange_name: str = "binance") -> dict[str, Any]:
    """Fetch price, funding rate, and long/short ratio from public APIs.

    Price comes from the host matching MARKET_TYPE (spot vs futures). Funding rate and
    long/short ratio are futures-only concepts and are skipped under a spot market.
    """
    clean = symbol.replace("/", "").upper()
    base, is_spot = _public_market_base()
    data: dict[str, Any] = {"symbol": symbol, "exchange": exchange_name, "errors": []}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            price_resp = await client.get(f"{base}/ticker/price?symbol={clean}")
            if price_resp.status_code == 200:
                data["price"] = float(price_resp.json().get("price", 0))

            if not is_spot:
                funding_resp = await client.get(
                    f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={clean}"
                )
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


async def get_klines(symbol: str, interval: str = "4h", limit: int = 100) -> list[list]:
    """Fetch OHLCV klines from the Binance public API matching MARKET_TYPE.

    Returns list of [open_time, open, high, low, close, volume, ...] rows.
    """
    clean = symbol.replace("/", "").upper()
    base, _ = _public_market_base()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base}/klines",
                params={"symbol": clean, "interval": interval, "limit": limit},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning("get_klines error for %s %s: %s", symbol, interval, exc)
    return []


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


# Stablecoin base assets that should never be traded as a USDT pair (no real volatility edge).
_STABLE_BASES: frozenset[str] = frozenset(
    {"USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "USDD", "PYUSD", "EURI", "AEUR", "USD1"}
)


def _is_leveraged_token(base: str) -> bool:
    """Binance leveraged tokens (BTCUP/BTCDOWN/ETHBULL/...) — not spot-tradeable the normal way."""
    return base.endswith(("UP", "DOWN")) or "BULL" in base or "BEAR" in base


async def screen_usdt_symbols(
    top_n: int = 5,
    min_quote_volume: float = 5_000_000.0,
    blacklist: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Rank liquid USDT pairs by liquidity x momentum (pure price math, no LLM).

    Selects the market matching MARKET_TYPE: spot pairs (``isSpotTradingAllowed``) or USDT-M
    perpetual futures contracts (``contractType == "PERPETUAL"``). Pulls the matching public
    Binance exchangeInfo + 24h ticker, drops leveraged tokens, stablecoin bases, blacklisted
    symbols, and pairs below ``min_quote_volume`` (24h quote volume in USDT). Ranks the
    survivors by ``quoteVolume * (1 + abs(priceChangePercent)/100)`` and returns the top
    ``top_n``.

    Returns a list of dicts: {symbol, base, quote_volume, price_change_pct, last_price, score}.
    """
    blacklist_set = {s.upper() for s in (blacklist or [])}
    base_url, is_spot = _public_market_base()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            info_resp = await client.get(f"{base_url}/exchangeInfo")
            ticker_resp = await client.get(f"{base_url}/ticker/24hr")
    except Exception as exc:
        logger.warning("screen_usdt_symbols fetch failed: %s", exc)
        return []

    if info_resp.status_code != 200 or ticker_resp.status_code != 200:
        logger.warning(
            "screen_usdt_symbols bad status: exchangeInfo=%s ticker=%s",
            info_resp.status_code,
            ticker_resp.status_code,
        )
        return []

    # Build the set of tradeable USDT symbols from exchangeInfo. Spot exposes
    # ``isSpotTradingAllowed``; futures exposes ``contractType`` (we keep only PERPETUAL).
    tradeable: dict[str, str] = {}  # symbol -> base asset
    for sym in info_resp.json().get("symbols", []):
        symbol = sym.get("symbol", "")
        base = sym.get("baseAsset", "")
        if is_spot:
            market_ok = bool(sym.get("isSpotTradingAllowed"))
        else:
            market_ok = sym.get("contractType") == "PERPETUAL"
        if (
            sym.get("status") == "TRADING"
            and sym.get("quoteAsset") == "USDT"
            and market_ok
            and symbol not in blacklist_set
            and base not in _STABLE_BASES
            and not _is_leveraged_token(base)
        ):
            tradeable[symbol] = base

    # Join with 24h ticker stats and score.
    candidates: list[dict[str, Any]] = []
    for row in ticker_resp.json():
        symbol = row.get("symbol", "")
        if symbol not in tradeable:
            continue
        try:
            quote_volume = float(row.get("quoteVolume", 0))
            price_change_pct = float(row.get("priceChangePercent", 0))
            last_price = float(row.get("lastPrice", 0))
        except (TypeError, ValueError):
            continue
        if quote_volume < min_quote_volume:
            continue
        score = quote_volume * (1.0 + abs(price_change_pct) / 100.0)
        candidates.append(
            {
                "symbol": symbol,
                "base": tradeable[symbol],
                "quote_volume": quote_volume,
                "price_change_pct": price_change_pct,
                "last_price": last_price,
                "score": score,
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[: max(0, top_n)]
