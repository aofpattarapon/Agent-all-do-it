"""ExecutionService — orchestrates testnet trade execution with 12 pre-execution checks."""

from __future__ import annotations

import logging
import math
import os
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter
from app.db.models.crypto_trading import Position, TradeExecution, TradeJournal, TradeProposal
from app.services.kill_switch import KillSwitch

logger = logging.getLogger(__name__)

_TRADING_MODE = os.getenv("TRADING_MODE", "TESTNET").upper()
_LIVE_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
_EXCHANGE_LABEL = "binance_futures_live" if _LIVE_ENABLED else "binance_futures_testnet"
_BLOCK_IF_SL_FAILS = os.getenv("BLOCK_IF_SL_ORDER_FAILS", "true").lower() == "true"
_MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "1"))


class ExecutionError(Exception):
    pass


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, proposal_id: UUID, project_id: UUID, user_id: UUID) -> dict[str, Any]:
        proposal = await self._get_proposal(proposal_id, project_id)
        await self._run_pre_checks(proposal, project_id)

        async with BinanceFuturesAdapter() as adapter:
            return await self._execute_proposal(adapter, proposal, project_id, user_id)

    async def _get_proposal(self, proposal_id: UUID, project_id: UUID) -> TradeProposal:
        result = await self.db.execute(
            select(TradeProposal).where(
                TradeProposal.id == proposal_id,
                TradeProposal.project_id == project_id,
            )
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            raise ExecutionError(f"Proposal {proposal_id} not found")
        return proposal

    async def _run_pre_checks(self, proposal: TradeProposal, project_id: UUID) -> None:
        errors: list[str] = []

        # 1. Proposal must be APPROVED
        if proposal.status != "APPROVED":
            errors.append(f"check_1_approval: status={proposal.status} (require APPROVED)")

        # 2. Not expired
        if proposal.expires_at and datetime.now(UTC) > proposal.expires_at:
            errors.append(f"check_2_expiry: expired_at={proposal.expires_at}")

        # 3. Trading mode must be set (TESTNET or LIVE)
        if _TRADING_MODE not in ("TESTNET", "LIVE"):
            errors.append(f"check_3_mode: TRADING_MODE={_TRADING_MODE} (must be TESTNET or LIVE)")

        # 4. Live trading: if LIVE mode, LIVE_TRADING_ENABLED must be true
        if _TRADING_MODE == "LIVE" and not _LIVE_ENABLED:
            errors.append("check_4_live: TRADING_MODE=LIVE but LIVE_TRADING_ENABLED=false")

        # 5–7. Exchange info checks
        try:
            async with BinanceFuturesAdapter() as adapter:
                info = await adapter.get_exchange_info()
            symbols_info = {s["symbol"]: s for s in info.get("symbols", [])}
            symbol_info = symbols_info.get(proposal.symbol)

            if symbol_info is None:
                errors.append(f"check_5_symbol: {proposal.symbol} not found in exchange info")
            else:
                # 6. Step size check
                position_size = proposal.position_size_usdt or 40.0
                mark_price = await self._get_mark_price_safe(proposal.symbol)
                quantity = position_size / mark_price if mark_price else 0

                lot_filter = next((f for f in symbol_info.get("filters", []) if f["filterType"] == "LOT_SIZE"), None)
                if lot_filter:
                    step_size = float(lot_filter.get("stepSize", 0.001))
                    min_qty = float(lot_filter.get("minQty", 0.001))
                    precision = max(0, int(round(-math.log10(step_size))))
                    quantity = round(round(quantity / step_size) * step_size, precision)
                    if quantity < min_qty:
                        errors.append(f"check_6_qty: quantity={quantity} < minQty={min_qty}")

                # 7. Notional check
                notional_filter = next((f for f in symbol_info.get("filters", []) if f["filterType"] == "MIN_NOTIONAL"), None)
                if notional_filter and mark_price:
                    min_notional = float(notional_filter.get("notional", 5))
                    notional = quantity * mark_price
                    if notional < min_notional:
                        errors.append(f"check_7_notional: notional={notional:.2f} < min={min_notional}")
        except Exception as exc:
            errors.append(f"check_5-7_exchange: {exc}")

        # 8. Leverage
        if _MAX_LEVERAGE > 1:
            errors.append(f"check_8_leverage: MAX_LEVERAGE={_MAX_LEVERAGE} (require <=1)")

        # 9. Stop loss set
        if not proposal.stop_loss:
            errors.append("check_9_sl: stop_loss is not set")

        # 10. Take profit set
        if not proposal.take_profit:
            errors.append("check_10_tp: take_profit list is empty")

        # 11. No duplicate open position
        dup_result = await self.db.execute(
            select(Position).where(
                Position.project_id == project_id,
                Position.symbol == proposal.symbol,
                Position.side == ("LONG" if proposal.direction == "LONG" else "SHORT"),
                Position.status == "OPEN",
            )
        )
        if dup_result.scalar_one_or_none():
            errors.append(f"check_11_duplicate: open {proposal.direction} position for {proposal.symbol} already exists")

        # 12. Kill switch
        ks = KillSwitch(self.db)
        ks_result = await ks.check(self.db, project_id=project_id, proposal=proposal)
        if not ks_result.passed:
            errors.append(f"check_12_kill_switch: {'; '.join(ks_result.blocked_reasons)}")

        if errors:
            raise ExecutionError("Pre-execution checks failed: " + " | ".join(errors))

    async def _get_mark_price_safe(self, symbol: str) -> float:
        try:
            async with BinanceFuturesAdapter() as adapter:
                data = await adapter.get_mark_price(symbol)
            return float(data.get("markPrice", 0))
        except Exception:
            return 0.0

    async def _execute_proposal(
        self, adapter: BinanceFuturesAdapter, proposal: TradeProposal, project_id: UUID, user_id: UUID
    ) -> dict[str, Any]:
        symbol = proposal.symbol
        side = "BUY" if proposal.direction == "LONG" else "SELL"
        close_side = "SELL" if proposal.direction == "LONG" else "BUY"

        position_size = proposal.position_size_usdt or 40.0
        mark_price = await self._get_mark_price_safe(symbol)
        if mark_price <= 0:
            raise ExecutionError(f"Cannot get mark price for {symbol}")

        quantity = position_size / mark_price
        info = await adapter.get_exchange_info()
        symbols_info = {s["symbol"]: s for s in info.get("symbols", [])}
        symbol_info = symbols_info.get(symbol, {})
        lot_filter = next((f for f in symbol_info.get("filters", []) if f["filterType"] == "LOT_SIZE"), None)
        if lot_filter:
            step_size = float(lot_filter.get("stepSize", 0.001))
            precision = max(0, int(round(-math.log10(step_size))))
            quantity = round(round(quantity / step_size) * step_size, precision)

        await adapter.set_leverage(symbol, 1)

        execution_id = uuid.uuid4()
        entry_order: dict[str, Any] = {}
        execution_status = "PENDING"
        error_message: str | None = None
        order_id: str = ""

        try:
            entry_order = await adapter.place_market_order(symbol, side, quantity)
            executed_price = float(entry_order.get("avgPrice") or entry_order.get("price") or mark_price)
            order_id = str(entry_order.get("orderId", ""))
            execution_status = "SUCCESS"
        except Exception as exc:
            error_message = str(exc)
            execution_status = "FAILED"
            logger.error("Entry order failed for proposal %s: %s", proposal.id, exc)

        execution = TradeExecution(
            id=execution_id,
            project_id=project_id,
            proposal_id=proposal.id,
            exchange=_EXCHANGE_LABEL,
            order_id=order_id,
            symbol=symbol,
            side=side,
            executed_price=mark_price if execution_status == "FAILED" else float(entry_order.get("avgPrice") or mark_price),
            size=quantity,
            execution_status=execution_status,
            error_message=error_message,
            raw_response=entry_order,
        )
        self.db.add(execution)
        await self.db.flush()
        await self.db.refresh(execution)

        if execution_status == "FAILED":
            await self._update_proposal_status(proposal, "EXECUTION_FAILED")
            await self.db.flush()
            raise ExecutionError(f"Entry order failed: {error_message}")

        executed_price = float(entry_order.get("avgPrice") or mark_price)

        position = Position(
            project_id=project_id,
            execution_id=execution_id,
            symbol=symbol,
            side="LONG" if proposal.direction == "LONG" else "SHORT",
            entry_price=executed_price,
            current_price=executed_price,
            size=quantity,
            stop_loss=proposal.stop_loss,
            take_profits=self._extract_tp_levels(proposal.take_profit),
            status="OPEN",
        )
        self.db.add(position)
        await self.db.flush()
        await self.db.refresh(position)

        sl_order_id: str = ""
        tp_order_ids: list[str] = []

        # Place SL order
        try:
            sl_order = await adapter.place_stop_market_order(
                symbol, close_side, quantity, proposal.stop_loss, reduce_only=True
            )
            sl_order_id = str(sl_order.get("orderId", ""))
        except Exception as exc:
            logger.error("SL order failed for position %s: %s", position.id, exc)
            position.status = "NEEDS_ATTENTION"
            await self.db.flush()
            if _BLOCK_IF_SL_FAILS:
                try:
                    await adapter.cancel_all_open_orders(symbol)
                    await adapter.place_market_order(symbol, close_side, quantity)
                except Exception:
                    pass
                raise ExecutionError(f"SL placement failed, position closed: {exc}")

        # Place TP orders (TP1=50%, TP2=30%, TP3=20%)
        tp_levels = self._extract_tp_levels(proposal.take_profit)
        size_pcts = [0.5, 0.3, 0.2]
        for i, tp_price in enumerate(tp_levels[:3]):
            pct = size_pcts[i] if i < len(size_pcts) else 0.1
            tp_qty = round(quantity * pct, len(str(quantity).rstrip("0").split(".")[-1]))
            try:
                tp_order = await adapter.place_take_profit_market_order(
                    symbol, close_side, tp_qty, tp_price, reduce_only=True
                )
                tp_order_ids.append(str(tp_order.get("orderId", "")))
            except Exception as exc:
                logger.warning("TP%d order failed for position %s: %s", i + 1, position.id, exc)
                position.status = "NEEDS_ATTENTION"

        execution.sl_order_id = sl_order_id
        execution.tp_order_ids = tp_order_ids

        await self._update_proposal_status(proposal, "EXECUTED")

        journal_entry = TradeJournal(
            project_id=project_id,
            position_id=position.id,
            symbol=symbol,
            direction=proposal.direction,
            entry_price=executed_price,
            size=quantity,
            result="OPEN",
            original_thesis=proposal.full_proposal_md or "",
            decision_log=[{
                "action": "executed",
                "exchange": _EXCHANGE_LABEL,
                "order_id": order_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "entry_price": executed_price,
            }],
            news_used=[proposal.news_summary] if proposal.news_summary else [],
            agent_votes=proposal.agent_vote_summary or {},
        )
        self.db.add(journal_entry)
        await self.db.flush()

        return {
            "execution_id": str(execution_id),
            "position_id": str(position.id),
            "order_id": order_id,
            "sl_order_id": sl_order_id,
            "tp_order_ids": tp_order_ids,
            "executed_price": executed_price,
            "quantity": quantity,
            "status": "SUCCESS",
        }

    def _extract_tp_levels(self, take_profit: list[Any]) -> list[float]:
        levels = []
        for tp in take_profit:
            if isinstance(tp, dict):
                level = tp.get("tp_level") or tp.get("price") or tp.get("level")
                if level:
                    levels.append(float(level))
            elif isinstance(tp, (int, float)):
                levels.append(float(tp))
        return sorted(levels)

    async def _update_proposal_status(self, proposal: TradeProposal, status: str) -> None:
        proposal.status = status
        await self.db.flush()
