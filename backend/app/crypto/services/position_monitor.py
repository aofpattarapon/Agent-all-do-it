"""PositionMonitor — polls open positions and updates prices, PnL, and alerts."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter
from app.db.models.crypto_trading import Position

logger = logging.getLogger(__name__)

_ALERT_SL_PCT = 1.0
_ALERT_TP1_PCT = 2.0
_ALERT_PROFIT_SECURE_PCT = 3.0


class PositionMonitor:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def monitor_all(self, project_id: UUID) -> list[dict[str, Any]]:
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
            if (is_long and current_price <= pos.stop_loss) or (not is_long and current_price >= pos.stop_loss):
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
            alert_message = f"Unrealized PnL {unrealized_pnl_pct:.2f}% — consider moving stop to break-even"

        if abs(funding_rate) > 0.001:
            alert_type = alert_type if alert_type != "NO_ALERT" else "FUNDING_RISK"
            alert_message = (alert_message or "") + f" | Funding rate: {funding_rate:.4%}"

        sl_missing_on_exchange = pos.stop_loss and not any("SL" in str(oid) for oid in open_order_ids)

        await self.db.execute(
            update(Position)
            .where(Position.id == pos.id)
            .values(
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
            )
        )
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
            "distance_to_sl_pct": round(distance_to_sl_pct, 4) if distance_to_sl_pct is not None else None,
            "distance_to_tp1_pct": round(distance_to_tp1_pct, 4) if distance_to_tp1_pct is not None else None,
            "funding_rate": funding_rate,
            "alert_type": alert_type,
            "alert_message": alert_message,
            "sl_order_missing_on_exchange": sl_missing_on_exchange,
            "monitored_at": datetime.now(UTC).isoformat(),
        }
