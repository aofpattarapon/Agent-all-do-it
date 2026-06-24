"""Read-only normalization of trade execution + position state into UI-facing visibility.

This module derives a clear, honest picture of *how* a trade was executed and *whether*
its TP/SL protection is currently active. It exists because the underlying execution data
is correct but its labels are misleading: a trade submitted to Binance Demo Futures (with
separate reduce-only SL/TP orders actually placed on the exchange) was historically surfaced
to the user as ``execution_mode=PAPER``.

Nothing here changes execution behavior. It only reads already-persisted fields
(``TradeExecution.raw_response["mode"]``, ``exchange``, ``sl_order_id``, ``tp_order_ids``,
and the ``Position`` SL/TP/status) and returns normalized dictionaries.

Key invariant we communicate: TP/SL is implemented as *separate reduce-only orders*, not as
Binance position-level TP/SL. Binance's own position row therefore may not show TP/SL — but
the orders exist under Open Orders, and this app is the source of truth for grouped visibility.
"""

from __future__ import annotations

from typing import Any

# ── Mode normalization ────────────────────────────────────────────────────────

# Canonical execution-mode descriptors keyed by the raw ``mode`` token an exchange
# adapter writes into ``TradeExecution.raw_response["mode"]``.
_MODE_TABLE: dict[str, dict[str, Any]] = {
    "PAPER": {
        "label": "PAPER_SIMULATION",
        "safety_mode": "SIMULATION",
        "submitted_to_exchange": False,
        "simulated_only": True,
        "real_money": False,
    },
    "DEMO_FUTURES": {
        "label": "DEMO_FUTURES",
        "safety_mode": "DEMO",
        "submitted_to_exchange": True,
        "simulated_only": False,
        "real_money": False,
    },
    "TESTNET": {
        "label": "TESTNET",
        "safety_mode": "TESTNET",
        "submitted_to_exchange": True,
        "simulated_only": False,
        "real_money": False,
    },
    "LIVE": {
        "label": "LIVE",
        "safety_mode": "LIVE",
        "submitted_to_exchange": True,
        "simulated_only": False,
        "real_money": True,
    },
}

# Fallback mapping from the persisted ``exchange`` string when ``mode`` is absent.
_EXCHANGE_TO_MODE: dict[str, str] = {
    "paper_trade": "PAPER",
    "binance_demo_futures": "DEMO_FUTURES",
    "binance_testnet": "TESTNET",
    "binance_live": "LIVE",
}

_UNKNOWN_MODE: dict[str, Any] = {
    "label": "UNKNOWN",
    "safety_mode": "UNKNOWN",
    "submitted_to_exchange": False,
    "simulated_only": False,
    "real_money": False,
}

_EXPLANATION = (
    "TP/SL is active via separate reduce-only orders. Binance may display these under "
    "Open Orders rather than the Position TP/SL row."
)


def _normalize_mode(raw_response: dict[str, Any] | None, exchange: str | None) -> dict[str, Any]:
    """Resolve the canonical mode descriptor from raw_response['mode'], falling back to exchange."""
    mode_token = ""
    if isinstance(raw_response, dict):
        mode_token = str(raw_response.get("mode") or "").strip().upper()
    # ``DEMO_FUTURES_SPOT`` / ``TESTNET_SPOT`` style suffixes normalize to their base mode.
    if mode_token not in _MODE_TABLE:
        for base in ("DEMO_FUTURES", "TESTNET", "LIVE", "PAPER"):
            if mode_token.startswith(base):
                mode_token = base
                break
    if mode_token in _MODE_TABLE:
        return _MODE_TABLE[mode_token]
    ex = (exchange or "").strip().lower()
    if ex in _EXCHANGE_TO_MODE:
        return _MODE_TABLE[_EXCHANGE_TO_MODE[ex]]
    return _UNKNOWN_MODE


def _tp_price(tp: Any) -> float | None:
    """Extract a numeric price from a take-profit entry (float or dict-shaped)."""
    if isinstance(tp, (int, float)):
        return float(tp)
    if isinstance(tp, dict):
        for key in ("price", "tp_price", "level", "tp_level", "target"):
            val = tp.get(key)
            if isinstance(val, (int, float)):
                return float(val)
    return None


def _clean_id(value: Any) -> str | None:
    """Normalize an order id to a non-empty string, or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_execution_visibility(
    *,
    exchange: str | None,
    raw_response: dict[str, Any] | None,
    sl_order_id: str | None,
    tp_order_ids: list[Any] | None,
    stop_loss: float | None,
    take_profits: list[Any] | None,
    position_status: str | None,
) -> dict[str, Any]:
    """Build the normalized execution-visibility object for a position/execution pair.

    All inputs are plain values pulled from the ``TradeExecution`` and ``Position`` rows so
    the function is trivially unit-testable without ORM objects. Read-only; never mutates.

    Returns a dict with: ``safety_mode``, ``exchange_route``, ``execution_mode_label``,
    ``submitted_to_exchange``, ``simulated_only``, ``real_money``, and ``protection``.
    """
    mode = _normalize_mode(raw_response, exchange)
    exchange_route = (exchange or "").strip().lower() or None
    # raw_response may carry a more specific exchange than the column (rare); prefer column.
    if exchange_route is None and isinstance(raw_response, dict):
        exchange_route = (str(raw_response.get("exchange") or "").strip().lower()) or None

    protection = build_protection(
        sl_order_id=sl_order_id,
        tp_order_ids=tp_order_ids,
        stop_loss=stop_loss,
        take_profits=take_profits,
        position_status=position_status,
        submitted_to_exchange=bool(mode["submitted_to_exchange"]),
    )

    return {
        "safety_mode": mode["safety_mode"],
        "exchange_route": exchange_route,
        "execution_mode_label": mode["label"],
        "submitted_to_exchange": bool(mode["submitted_to_exchange"]),
        "simulated_only": bool(mode["simulated_only"]),
        "real_money": bool(mode["real_money"]),
        "protection": protection,
    }


def build_protection(
    *,
    sl_order_id: str | None,
    tp_order_ids: list[Any] | None,
    stop_loss: float | None,
    take_profits: list[Any] | None,
    position_status: str | None,
    submitted_to_exchange: bool,
) -> dict[str, Any]:
    """Classify TP/SL protection state and build SL + TP order rows.

    Status:
      * ``CLOSED``  — the position is no longer open.
      * ``ACTIVE``  — open with at least one SL *and* at least one TP order/level.
      * ``PARTIAL`` — open with only an SL or only a TP (not both).
      * ``MISSING`` — open with neither SL nor TP.
      * ``UNKNOWN`` — not enough data to classify (e.g. no execution record).
    """
    status_norm = (position_status or "").strip().upper()
    is_closed = status_norm in {"CLOSED", "STOPPED", "LIQUIDATED"}

    sl_id = _clean_id(sl_order_id)
    tp_ids = [_clean_id(t) for t in (tp_order_ids or [])]
    tp_ids = [t for t in tp_ids if t is not None]

    row_status = "CLOSED" if is_closed else "OPEN"

    # ── Stop-loss row ──
    sl_row: dict[str, Any] | None = None
    if stop_loss is not None or sl_id is not None:
        sl_row = {
            "price": stop_loss,
            "order_id": sl_id,
            "status": row_status,
        }

    # ── Take-profit rows (zip prices with order ids by index) ──
    tp_rows: list[dict[str, Any]] = []
    tp_prices = list(take_profits or [])
    count = max(len(tp_prices), len(tp_ids))
    for i in range(count):
        price = _tp_price(tp_prices[i]) if i < len(tp_prices) else None
        order_id = tp_ids[i] if i < len(tp_ids) else None
        tp_rows.append(
            {
                "level": i + 1,
                "price": price,
                "order_id": order_id,
                "status": row_status,
            }
        )

    has_sl = sl_row is not None
    has_tp = len(tp_rows) > 0

    if is_closed:
        status = "CLOSED"
    elif not has_sl and not has_tp:
        # No protection data at all: distinguish genuinely-missing from unknowable.
        status = "MISSING" if status_norm == "OPEN" else "UNKNOWN"
    elif has_sl and has_tp:
        status = "ACTIVE"
    else:
        status = "PARTIAL"

    # Protection is delivered via separate reduce-only orders whenever real exchange order
    # ids exist; pure paper runs only simulate them.
    if submitted_to_exchange and (sl_id is not None or tp_ids):
        source = "separate_reduce_only_orders"
    elif submitted_to_exchange:
        source = "exchange"
    else:
        source = "simulated"

    return {
        "status": status,
        "source": source,
        "explanation": _EXPLANATION,
        "stop_loss": sl_row,
        "take_profits": tp_rows,
        "sl_active": has_sl and not is_closed,
        "tp_active_count": len(tp_rows) if not is_closed else 0,
        "tp_total_count": len(tp_rows),
    }


def build_trade_confirmation(
    *,
    position_status: str | None,
    realized_pnl: float | None,
    submitted_to_exchange: bool,
    has_execution: bool,
    order_id: str | None,
    execution_status: str | None,
) -> dict[str, Any]:
    """Derive honest confirmation flags for a position from already-persisted fields.

    Read-only and column-derived — never fabricates. Meanings:

      * ``order_placed`` — an order was actually submitted (a linked execution exists with an
        order id or a SUCCESS status). Distinguishes a real order from a no-order run.
      * ``position_created`` — a position row exists for this trade.
      * ``exchange_confirmed`` — the position was submitted to a real exchange route
        (demo/testnet/live) *and* is now closed; exchange-backed closes are reconciled against
        live exchange state by the monitor before the DB row is closed.
      * ``pnl_estimated`` — no booked ``realized_pnl`` is recorded, so any PnL shown is an
        unrealized/estimated figure. ``False`` once a realized PnL has been booked on close.
    """
    status_norm = (position_status or "").strip().upper()
    is_closed = status_norm in {"CLOSED", "STOPPED", "LIQUIDATED"}
    order_placed = bool(
        has_execution
        and ((order_id or "").strip() or (execution_status or "").strip().upper() == "SUCCESS")
    )
    return {
        "order_placed": order_placed,
        "position_created": True,
        "exchange_confirmed": is_closed and bool(submitted_to_exchange),
        "pnl_estimated": realized_pnl is None,
    }


def build_protection_summary(
    *,
    sl_order_id: str | None,
    tp_order_ids: list[Any] | None,
    stop_loss: float | None,
    take_profits: list[Any] | None,
    position_status: str | None,
    submitted_to_exchange: bool,
) -> dict[str, Any]:
    """Compact protection summary for list views (status + counts + explanation)."""
    protection = build_protection(
        sl_order_id=sl_order_id,
        tp_order_ids=tp_order_ids,
        stop_loss=stop_loss,
        take_profits=take_profits,
        position_status=position_status,
        submitted_to_exchange=submitted_to_exchange,
    )
    return {
        "status": protection["status"],
        "source": protection["source"],
        "sl_active": protection["sl_active"],
        "tp_active_count": protection["tp_active_count"],
        "tp_total_count": protection["tp_total_count"],
        "explanation": protection["explanation"],
    }
