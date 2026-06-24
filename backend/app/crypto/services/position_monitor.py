"""PositionMonitor — polls open positions and updates prices, PnL, and alerts."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter
from app.db.models.crypto_trading import Position, TradeExecution
from app.services.trading_mode import resolve_trading_mode

logger = logging.getLogger(__name__)

_ALERT_SL_PCT = 1.0
_ALERT_TP1_PCT = 2.0
_ALERT_PROFIT_SECURE_PCT = 3.0


def _derive_close_reason(
    *,
    stop_loss: float | None,
    tp_levels: list[float],
    sl_order_gone: bool,
    tp_order_gone: bool,
) -> str:
    """Classify WHY a now-flat position closed, using ONLY the disappeared-order signal.

    A reduce-only SL/TP order that is no longer resting on the exchange is a real, observed
    event — so an SL order gone (with an SL set) means "SL", a TP order gone (with a TP set)
    means "TP". We deliberately do NOT guess SL vs TP from the last mark price: a mark price
    happening to be beyond a level does not prove which order filled (it could be a manual or
    liquidation close), and a wrong guess pollutes the learning loop. When the order signal is
    absent or ambiguous (neither/both gone, or ids never recorded) we return the neutral
    ``UNKNOWN_EXCHANGE_FLAT`` rather than fabricating a reason.
    """
    sl_signal = sl_order_gone and bool(stop_loss)
    tp_signal = tp_order_gone and bool(tp_levels)
    if sl_signal and not tp_signal:
        return "SL"
    if tp_signal and not sl_signal:
        return "TP"
    return "UNKNOWN_EXCHANGE_FLAT"


class PositionMonitor:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def monitor_all(self, project_id: UUID) -> list[dict[str, Any]]:
        # Futures-only: every adapter call below targets the Binance futures API. Block spot
        # rather than silently monitoring spot positions through the wrong endpoints.
        if os.getenv("MARKET_TYPE", "futures").lower() == "spot":
            raise NotImplementedError(
                "PositionMonitor uses the futures adapter; spot position monitoring "
                "requires a spot adapter (not yet implemented)."
            )
        result = await self.db.execute(
            select(Position).where(
                Position.project_id == project_id,
                Position.status == "OPEN",
            )
        )
        positions = result.scalars().all()
        reports = []
        for pos in positions:
            try:
                report = await self._monitor_one(pos)
                reports.append(report)
            except Exception as exc:
                logger.warning("Monitor failed for position %s: %s", pos.id, exc)
        return reports

    async def build_snapshot(self, project_id: UUID) -> list[dict[str, Any]]:
        """Build an EXCHANGE-DRIVEN snapshot of every open position.

        This is the source-of-truth feed for the lifecycle/learning loop. Unlike
        ``monitor_all`` (which only updates prices/alerts), it asks the exchange whether each
        position is still open and, when flat, derives the close reason and realised PnL.

        Per entry it reports one of three outcomes (mutually exclusive):
          * ``closed: True``          — exchange confirms positionAmt == 0 (real close).
          * ``needs_attention: True`` — still open but the stop-loss order is missing.
          * ``error: True``           — exchange could not be reached/parsed (NEVER a close).

        Pure ``paper`` mode (no real exchange) yields ``paper: True`` stubs with no close
        detection — simulated exits are not exchange events and are handled by the legacy
        LLM-text path instead. ``demo``/``testnet``/``live`` are all exchange-backed.
        """
        if os.getenv("MARKET_TYPE", "futures").lower() == "spot":
            raise NotImplementedError(
                "PositionMonitor uses the futures adapter; spot position monitoring "
                "requires a spot adapter (not yet implemented)."
            )
        result = await self.db.execute(
            select(Position).where(
                Position.project_id == project_id,
                Position.status.in_(["OPEN", "NEEDS_ATTENTION"]),
            )
        )
        positions = result.scalars().all()

        exchange_backed = resolve_trading_mode().exchange_mode != "paper"
        snapshot: list[dict[str, Any]] = []
        for pos in positions:
            if not exchange_backed:
                snapshot.append(
                    {
                        "position_id": str(pos.id),
                        "symbol": pos.symbol,
                        "side": pos.side,
                        "paper": True,
                        "closed": False,
                        "needs_attention": False,
                        "error": False,
                    }
                )
                continue
            try:
                snapshot.append(await self._snapshot_one(pos))
            except Exception as exc:
                logger.warning("Snapshot failed for position %s (%s): %s", pos.id, pos.symbol, exc)
                snapshot.append(
                    {
                        "position_id": str(pos.id),
                        "symbol": pos.symbol,
                        "side": pos.side,
                        "closed": False,
                        "needs_attention": False,
                        "error": True,
                        "error_message": str(exc),
                    }
                )
        return snapshot

    async def _snapshot_one(self, pos: Position) -> dict[str, Any]:
        """Exchange-driven snapshot for a single position. Raises on adapter failure."""
        # Protection-order ids live on the TradeExecution row (not on Position).
        exec_row = (
            await self.db.execute(
                select(TradeExecution).where(TradeExecution.id == pos.execution_id)
            )
        ).scalar_one_or_none()
        sl_order_id = str(exec_row.sl_order_id).strip() if exec_row and exec_row.sl_order_id else ""
        tp_order_ids = [
            str(oid).strip()
            for oid in (exec_row.tp_order_ids or [] if exec_row else [])
            if oid is not None and str(oid).strip()
        ]

        async with BinanceFuturesAdapter() as adapter:
            position_rows = await adapter.get_position(pos.symbol)
            price_data = await adapter.get_mark_price(pos.symbol)
            mark_price = float(price_data.get("markPrice", pos.entry_price))
            orders = await adapter.get_open_orders(pos.symbol)
            open_order_ids = {str(o.get("orderId")) for o in (orders or [])}
            # SL/TP are CONDITIONAL algo orders (Binance 2025-12 Algo migration) that live on a
            # SEPARATE endpoint — they NEVER appear in /fapi/v1/openOrders. Union their algoIds
            # (the adapter mirrors algoId→orderId on placement, so the stored sl_order_id/
            # tp_order_ids are algoIds) so a live algo SL/TP is not mis-detected as "missing".
            # Best-effort: a read failure here must never block close detection.
            try:
                algo_orders = await adapter.get_open_algo_orders(pos.symbol)
                open_order_ids |= {str(o.get("algoId")) for o in (algo_orders or [])}
            except Exception as exc:
                logger.warning("get_open_algo_orders failed for %s: %s", pos.symbol, exc)

            position_amt = sum(
                abs(float(row.get("positionAmt", 0) or 0)) for row in (position_rows or [])
            )
            is_flat = position_amt <= 0

            tp_levels = [float(tp) for tp in (pos.take_profits or [])]
            sl_order_gone = bool(sl_order_id and sl_order_id not in open_order_ids)
            tp_order_gone = any(oid not in open_order_ids for oid in tp_order_ids)

            if is_flat:
                close_reason = _derive_close_reason(
                    stop_loss=pos.stop_loss,
                    tp_levels=tp_levels,
                    sl_order_gone=sl_order_gone,
                    tp_order_gone=tp_order_gone,
                )
                # Bound realised-PnL lookup to this position's lifetime so we never attribute a
                # *previous* trade's PnL (same symbol, earlier) to this close, and so we capture
                # ALL realised-PnL rows since entry (multiple rows when the exit was partial-filled).
                entry_ts = (exec_row.created_at if exec_row else None) or pos.created_at
                start_ms = int(entry_ts.timestamp() * 1000) if entry_ts is not None else None

                realized_pnl: float | None = None
                pnl_estimated = False
                try:
                    incomes = await adapter.get_income(
                        pos.symbol, income_type="REALIZED_PNL", start_time=start_ms
                    )
                    pnl_rows = [
                        r
                        for r in (incomes or [])
                        if str(r.get("symbol")) == pos.symbol
                        and (start_ms is None or int(r.get("time", 0) or 0) >= start_ms)
                    ]
                    if pnl_rows:
                        realized_pnl = sum(float(r.get("income", 0) or 0) for r in pnl_rows)
                except Exception as exc:  # PnL is best-effort; never blocks close detection
                    logger.warning(
                        "get_income failed for %s; PnL will be estimated: %s", pos.symbol, exc
                    )

                if realized_pnl is None and pos.entry_price:
                    # Fallback estimate from mark vs entry (ignores fees/funding/partial fills).
                    is_long = pos.side == "LONG"
                    delta = (
                        (mark_price - pos.entry_price)
                        if is_long
                        else (pos.entry_price - mark_price)
                    )
                    realized_pnl = delta * pos.size
                    pnl_estimated = True

                realized_pnl_pct: float | None = None
                notional = (pos.entry_price or 0) * (pos.size or 0)
                if realized_pnl is not None and notional:
                    realized_pnl_pct = realized_pnl / notional * 100

                return {
                    "position_id": str(pos.id),
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "closed": True,
                    "needs_attention": False,
                    "error": False,
                    "close_reason": close_reason,
                    "exit_price": mark_price,
                    "realized_pnl": round(realized_pnl, 6) if realized_pnl is not None else None,
                    "realized_pnl_pct": round(realized_pnl_pct, 4)
                    if realized_pnl_pct is not None
                    else None,
                    "pnl_estimated": pnl_estimated,
                    "monitored_at": datetime.now(UTC).isoformat(),
                }

            # Still open on the exchange — interpret health and flag missing stop-loss.
            is_long = pos.side == "LONG"
            if is_long:
                unrealized_pnl_pct = (mark_price - pos.entry_price) / pos.entry_price * 100
            else:
                unrealized_pnl_pct = (pos.entry_price - mark_price) / pos.entry_price * 100
            unrealized_pnl = unrealized_pnl_pct / 100 * (pos.entry_price * pos.size)

            sl_never_placed = bool(pos.stop_loss and not sl_order_id)
            sl_missing_on_exchange = sl_order_gone
            needs_attention = sl_never_placed or sl_missing_on_exchange

            return {
                "position_id": str(pos.id),
                "symbol": pos.symbol,
                "side": pos.side,
                "closed": False,
                "needs_attention": needs_attention,
                "error": False,
                "entry_price": pos.entry_price,
                "current_price": mark_price,
                "stop_loss": pos.stop_loss,
                "take_profit_levels": tp_levels,
                "unrealized_pnl": round(unrealized_pnl, 6),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
                "sl_never_placed": sl_never_placed,
                "sl_order_missing_on_exchange": sl_missing_on_exchange,
                "alert_type": "SL_MISSING" if needs_attention else "NO_ALERT",
                "monitored_at": datetime.now(UTC).isoformat(),
            }

    async def _monitor_one(self, pos: Position) -> dict[str, Any]:
        async with BinanceFuturesAdapter() as adapter:
            price_data = await adapter.get_mark_price(pos.symbol)
            current_price = float(price_data.get("markPrice", pos.entry_price))

            funding = await adapter.get_funding_rate(pos.symbol)
            funding_rate = float(funding.get("lastFundingRate", 0))

            orders = await adapter.get_open_orders(pos.symbol)
            open_order_ids = {str(o.get("orderId")) for o in orders}

        is_long = pos.side == "LONG"

        if is_long:
            unrealized_pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
        else:
            unrealized_pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100

        unrealized_pnl = unrealized_pnl_pct / 100 * (pos.entry_price * pos.size)

        distance_to_sl_pct = None
        if pos.stop_loss:
            if is_long:
                distance_to_sl_pct = (current_price - pos.stop_loss) / current_price * 100
            else:
                distance_to_sl_pct = (pos.stop_loss - current_price) / current_price * 100

        tp_levels = [float(tp) for tp in (pos.take_profits or [])]
        distance_to_tp1_pct = None
        if tp_levels:
            if is_long:
                distance_to_tp1_pct = (tp_levels[0] - current_price) / current_price * 100
            else:
                distance_to_tp1_pct = (current_price - tp_levels[0]) / current_price * 100

        alert_type = "NO_ALERT"
        alert_message: str | None = None

        if pos.stop_loss and distance_to_sl_pct is not None:
            if (is_long and current_price <= pos.stop_loss) or (
                not is_long and current_price >= pos.stop_loss
            ):
                alert_type = "SL_BREACH"
                alert_message = f"Stop loss breached at {current_price}"
            elif abs(distance_to_sl_pct) < _ALERT_SL_PCT:
                alert_type = "SL_APPROACH"
                alert_message = f"Price within {abs(distance_to_sl_pct):.2f}% of SL"

        if alert_type == "NO_ALERT" and tp_levels and distance_to_tp1_pct is not None:
            if distance_to_tp1_pct <= 0:
                alert_type = "TP1_HIT"
                alert_message = f"TP1 ({tp_levels[0]}) reached at {current_price}"
            elif distance_to_tp1_pct < _ALERT_TP1_PCT:
                alert_type = "TP1_APPROACH"
                alert_message = f"Price within {distance_to_tp1_pct:.2f}% of TP1"

        if alert_type == "NO_ALERT" and unrealized_pnl_pct >= _ALERT_PROFIT_SECURE_PCT:
            alert_type = "PROFIT_SECURE_SUGGESTED"
            alert_message = (
                f"Unrealized PnL {unrealized_pnl_pct:.2f}% — consider moving stop to break-even"
            )

        if abs(funding_rate) > 0.001:
            alert_type = alert_type if alert_type != "NO_ALERT" else "FUNDING_RISK"
            alert_message = (alert_message or "") + f" | Funding rate: {funding_rate:.4%}"

        # SL never placed (no sl_order_id recorded at all)
        sl_never_placed = bool(pos.stop_loss and not pos.sl_order_id)
        # SL placed but no longer in open orders (triggered or cancelled externally)
        sl_missing_on_exchange = bool(
            pos.stop_loss and pos.sl_order_id and str(pos.sl_order_id) not in open_order_ids
        )

        if (sl_never_placed or sl_missing_on_exchange) and alert_type == "NO_ALERT":
            alert_type = "SL_MISSING"
            reason = (
                "SL order was never placed"
                if sl_never_placed
                else "SL order no longer in open orders"
            )
            alert_message = f"{reason} for {pos.symbol} {pos.side} position"

        # A position with no working stop-loss is unprotected (runaway risk). Flag it
        # NEEDS_ATTENTION as a persistent, blocking alert so it is surfaced for human action
        # instead of being treated as a healthy OPEN position. Per policy we do NOT auto-place
        # a close/SL order — a human resolves it.
        update_values: dict[str, Any] = {
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
        }
        if sl_never_placed or sl_missing_on_exchange:
            update_values["status"] = "NEEDS_ATTENTION"
            logger.warning(
                "Position %s (%s %s) flagged NEEDS_ATTENTION — %s",
                pos.id,
                pos.symbol,
                pos.side,
                alert_message or "stop-loss missing",
            )

        await self.db.execute(update(Position).where(Position.id == pos.id).values(**update_values))
        await self.db.flush()

        return {
            "position_id": str(pos.id),
            "symbol": pos.symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "current_price": current_price,
            "stop_loss": pos.stop_loss,
            "take_profit_levels": tp_levels,
            "unrealized_pnl": round(unrealized_pnl, 6),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
            "distance_to_sl_pct": round(distance_to_sl_pct, 4)
            if distance_to_sl_pct is not None
            else None,
            "distance_to_tp1_pct": round(distance_to_tp1_pct, 4)
            if distance_to_tp1_pct is not None
            else None,
            "funding_rate": funding_rate,
            "alert_type": alert_type,
            "alert_message": alert_message,
            "sl_never_placed": sl_never_placed,
            "sl_order_missing_on_exchange": sl_missing_on_exchange,
            "monitored_at": datetime.now(UTC).isoformat(),
        }
