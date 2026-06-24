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
from app.db.locks import LockNamespace, advisory_xact_lock
from app.db.models.crypto_trading import Position, TradeExecution, TradeJournal, TradeProposal
from app.services.crypto_persistence import build_trade_journal_raw_facts
from app.services.execution_preflight import (
    entry_price_from_plan,
    latest_market_regime,
    take_profit_levels_from_proposal,
)
from app.services.kill_switch import KillSwitch
from app.services.trading_mode import resolve_trading_mode

logger = logging.getLogger(__name__)

# Order-capable trading modes that ExecutionService accepts. PAPER is deliberately
# excluded — it is local-simulation-only and must never reach this real-order path
# (the paper route lives in exchange_tool._paper_execute).
_ORDER_CAPABLE_MODES = ("DEMO", "TESTNET", "LIVE")

_TRADING_MODE = os.getenv("TRADING_MODE", "TESTNET").upper()
_LIVE_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"


def _resolve_exchange_label() -> str:
    """Honest exchange label for execution visibility (demo ≠ testnet ≠ live)."""
    if _LIVE_ENABLED and _TRADING_MODE == "LIVE":
        return "binance_futures_live"
    if _TRADING_MODE == "DEMO":
        return "binance_demo_futures"
    return "binance_futures_testnet"


_EXCHANGE_LABEL = _resolve_exchange_label()
_MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "1"))


class ExecutionError(Exception):
    pass


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, proposal_id: UUID, project_id: UUID, user_id: UUID) -> dict[str, Any]:
        # H5/H6: serialize concurrent executions. The per-project lock guards the position-cap
        # check-and-open critical section so the cap can't be exceeded by interleaved calls; the
        # per-proposal lock guards against the same proposal being executed twice. Both are
        # transaction-scoped and auto-released at commit/rollback.
        await advisory_xact_lock(self.db, LockNamespace.POSITION_CAP, project_id)
        await advisory_xact_lock(self.db, LockNamespace.PROPOSAL_EXECUTION, proposal_id)

        # H6 idempotency: if this proposal already has a SUCCESS execution, return it instead of
        # placing a second entry order (defends retries / double-clicks / concurrent dispatch).
        existing = await self._existing_successful_execution(proposal_id, project_id)
        if existing is not None:
            logger.info(
                "Proposal %s already has SUCCESS execution %s — returning it idempotently "
                "(no second order placed)",
                proposal_id,
                existing.id,
            )
            return self._execution_to_result(existing)

        proposal = await self._get_proposal(proposal_id, project_id)
        consume_loss_ack = await self._run_pre_checks(proposal, project_id)

        async with BinanceFuturesAdapter() as adapter:
            return await self._execute_proposal(
                adapter, proposal, project_id, user_id, consume_loss_ack=consume_loss_ack
            )

    async def _get_proposal(self, proposal_id: UUID, project_id: UUID) -> TradeProposal:
        # FOR UPDATE: hold a row lock on the proposal so two concurrent executions of the same
        # proposal serialize — the loser observes the EXECUTED status / SUCCESS execution and stops.
        result = await self.db.execute(
            select(TradeProposal)
            .where(
                TradeProposal.id == proposal_id,
                TradeProposal.project_id == project_id,
            )
            .with_for_update()
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            raise ExecutionError(f"Proposal {proposal_id} not found")
        return proposal

    async def _existing_successful_execution(
        self, proposal_id: UUID, project_id: UUID
    ) -> TradeExecution | None:
        """Return the existing SUCCESS execution for this proposal, if any (idempotency check)."""
        result = await self.db.execute(
            select(TradeExecution)
            .where(
                TradeExecution.proposal_id == proposal_id,
                TradeExecution.project_id == project_id,
                TradeExecution.execution_status == "SUCCESS",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _execution_to_result(execution: TradeExecution) -> dict[str, Any]:
        """Build the success payload from an already-persisted execution (idempotent replay)."""
        return {
            "execution_id": str(execution.id),
            "position_id": "",
            "order_id": execution.order_id or "",
            "sl_order_id": execution.sl_order_id or "",
            "tp_order_ids": list(execution.tp_order_ids or []),
            "executed_price": execution.executed_price,
            "quantity": execution.size,
            "status": "SUCCESS",
            "idempotent": True,
        }

    async def _run_pre_checks(self, proposal: TradeProposal, project_id: UUID) -> bool:
        """Run the 12 pre-execution checks. Returns whether the consecutive-loss kill-switch
        block was bypassed by an explicit single-use acknowledgement (so the caller consumes it
        after the order attempt). Raises ExecutionError if any check fails."""
        errors: list[str] = []
        direction = str(proposal.direction or "").upper()
        entry_price = entry_price_from_plan(proposal.entry_plan)
        take_profit_levels = take_profit_levels_from_proposal(proposal.take_profit)

        # 1. Proposal must be APPROVED
        if proposal.status != "APPROVED":
            errors.append(f"check_1_approval: status={proposal.status} (require APPROVED)")

        # 2. Not expired
        if proposal.expires_at and datetime.now(UTC) > proposal.expires_at:
            errors.append(f"check_2_expiry: expired_at={proposal.expires_at}")

        # 3. Trading mode must be order-capable (DEMO, TESTNET, or LIVE). PAPER is
        # local-simulation-only and can never place an exchange order through this path.
        if _TRADING_MODE not in _ORDER_CAPABLE_MODES:
            errors.append(
                f"check_3_mode: TRADING_MODE={_TRADING_MODE} (must be DEMO, TESTNET, or LIVE; "
                "PAPER is local-simulation-only and cannot place exchange orders)"
            )

        # 3b. TRADING_MODE and EXCHANGE_MODE must agree — fail closed on any mismatch so
        # ExecutionService and the exchange_tool/run_executor path resolve the same mode.
        mode_status = resolve_trading_mode()
        if mode_status.conflict:
            errors.append(f"check_3b_mode_conflict: {mode_status.conflict}")

        # 4. Live trading: if LIVE mode, LIVE_TRADING_ENABLED must be true
        if _TRADING_MODE == "LIVE" and not _LIVE_ENABLED:
            errors.append("check_4_live: TRADING_MODE=LIVE but LIVE_TRADING_ENABLED=false")

        if direction not in {"LONG", "SHORT"}:
            errors.append(f"check_4b_direction: invalid direction={direction or '<empty>'}")
        if not str(proposal.symbol or "").strip():
            errors.append("check_4c_symbol: symbol is missing")
        if entry_price <= 0:
            errors.append("check_4d_entry: entry price is missing or non-positive")
        if float(proposal.position_size_usdt or 0) <= 0:
            errors.append("check_4e_size: position_size_usdt must be positive")

        # 5-7. Exchange info checks
        try:
            async with BinanceFuturesAdapter() as adapter:
                info = await adapter.get_exchange_info()
                symbols_info = {s["symbol"]: s for s in info.get("symbols", [])}
                symbol_info = symbols_info.get(proposal.symbol)

                if symbol_info is None:
                    errors.append(f"check_5_symbol: {proposal.symbol} not found in exchange info")
                else:
                    mark_price = await self._get_mark_price_safe(proposal.symbol)
                    quantity, filter_errors = self._validate_symbol_filters(
                        symbol_info=symbol_info,
                        position_size_usdt=float(proposal.position_size_usdt or 0),
                        mark_price=mark_price,
                    )
                    errors.extend(filter_errors)
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
            errors.append(
                f"check_11_duplicate: open {proposal.direction} position for {proposal.symbol} already exists"
            )

        # 12. Kill switch
        ks = KillSwitch(self.db)
        market_regime = await latest_market_regime(self.db, project_id)
        ks_result = await ks.check(
            project_id=project_id,
            symbol=proposal.symbol,
            direction=direction,
            stop_loss=proposal.stop_loss,
            take_profit_levels=take_profit_levels,
            proposed_size_usdt=float(proposal.position_size_usdt or 0),
            entry_price=entry_price,
            market_regime=market_regime,
        )
        if not ks_result.passed:
            errors.append(f"check_12_kill_switch: {'; '.join(ks_result.blocked_reasons)}")

        if errors:
            raise ExecutionError("Pre-execution checks failed: " + " | ".join(errors))

        return ks_result.consecutive_loss_ack_used

    async def _get_mark_price_safe(self, symbol: str) -> float:
        try:
            async with BinanceFuturesAdapter() as adapter:
                data = await adapter.get_mark_price(symbol)
            return float(data.get("markPrice", 0))
        except Exception:
            return 0.0

    async def _execute_proposal(
        self,
        adapter: BinanceFuturesAdapter,
        proposal: TradeProposal,
        project_id: UUID,
        user_id: UUID,
        *,
        consume_loss_ack: bool = False,
    ) -> dict[str, Any]:
        symbol = proposal.symbol
        side = "BUY" if proposal.direction == "LONG" else "SELL"
        close_side = "SELL" if proposal.direction == "LONG" else "BUY"

        position_size = proposal.position_size_usdt or 40.0
        mark_price = await self._get_mark_price_safe(symbol)
        if mark_price <= 0:
            raise ExecutionError(f"Cannot get mark price for {symbol}")

        info = await adapter.get_exchange_info()
        symbols_info = {s["symbol"]: s for s in info.get("symbols", [])}
        symbol_info = symbols_info.get(symbol, {})
        quantity, filter_errors = self._validate_symbol_filters(
            symbol_info=symbol_info,
            position_size_usdt=float(position_size),
            mark_price=mark_price,
        )
        if filter_errors:
            raise ExecutionError("Pre-execution checks failed: " + " | ".join(filter_errors))

        await adapter.set_leverage(symbol, 1)

        execution_id = uuid.uuid4()
        entry_order: dict[str, Any] = {}
        execution_status = "PENDING"
        error_message: str | None = None
        order_id: str = ""
        execution_payload: dict[str, Any] = {}

        try:
            # Deterministic client order id (H6) — same proposal ⇒ same id ⇒ exchange-side dedupe.
            client_order_id = f"pda-{proposal.id.hex}"
            entry_order = await adapter.place_market_order(symbol, side, quantity, client_order_id)
            executed_price = float(
                entry_order.get("avgPrice") or entry_order.get("price") or mark_price
            )
            order_id = str(entry_order.get("orderId", ""))
            # Entry filled, but the trade is NOT a complete success yet — the protective
            # stop-loss must be confirmed first. Persist a provisional ENTRY_FILLED status so a
            # SUCCESS row only ever represents an entry+SL-confirmed (protected) trade. This is
            # promoted to SUCCESS after the SL is placed, or set to ENTRY_FILLED_SL_FAILED below.
            execution_status = "ENTRY_FILLED"
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
            executed_price=mark_price
            if execution_status == "FAILED"
            else float(entry_order.get("avgPrice") or mark_price),
            size=quantity,
            execution_status=execution_status,
            error_message=error_message,
            raw_response=entry_order,
        )
        self.db.add(execution)
        await self.db.flush()
        await self.db.refresh(execution)

        # Single-shot consume: an entry order has now been ATTEMPTED on the exchange (the
        # execution row is persisted whether it filled or was rejected). If this trade only
        # cleared the consecutive-loss gate via an explicit acknowledgement, burn that ack now
        # so it authorizes exactly one attempt — a retry requires a fresh acknowledgement.
        if consume_loss_ack:
            from app.services import risk_ack

            await risk_ack.consume_ack(self.db, project_id)

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
        sl_warning: str | None = None
        tp_warnings: list[str] = []

        # Place SL order — a confirmed stop-loss is MANDATORY (hard block; the prior
        # BLOCK_IF_SL_ORDER_FAILS env bypass that could return SUCCESS with a naked
        # position has been removed). The entry is already filled, so on failure we must
        # NOT roll the position back (that would orphan a live exchange position the system
        # can no longer see). Instead keep it TRACKED as NEEDS_ATTENTION, commit, and raise
        # a blocking alert. Per policy the system does NOT auto-place a close order to flatten
        # the position — a human resolves it (previously this was a swallowed best-effort
        # close that could silently leave the position live while the DB rolled back).
        try:
            sl_order = await adapter.place_stop_market_order(
                symbol, close_side, quantity, proposal.stop_loss, reduce_only=True
            )
            sl_order_id = str(sl_order.get("orderId", ""))
            # Entry AND the protective stop-loss are both confirmed — only now is this a
            # complete, protected execution. (A subsequent TP failure flags the position
            # NEEDS_ATTENTION but does not revoke SUCCESS — the position is still protected.)
            execution.execution_status = "SUCCESS"
        except Exception as exc:
            logger.error(
                "SL order failed for position %s (%s) — hard blocking, position left OPEN "
                "and flagged NEEDS_ATTENTION: %s",
                position.id,
                symbol,
                exc,
            )
            position.status = "NEEDS_ATTENTION"
            execution.sl_order_id = ""
            # The entry filled but the stop-loss was rejected: this is NOT a complete success.
            # Record an explicit non-complete status so the persisted TradeExecution can never
            # be mistaken for an entry+SL-confirmed trade, and so the H6 SUCCESS-only idempotency
            # index / `_existing_successful_execution` guard does not treat it as a finished
            # trade. (A replay is still blocked from a second entry order: the proposal is now
            # NEEDS_ATTENTION, so re-running execute() fails check_1_approval before any order.)
            execution.execution_status = "ENTRY_FILLED_SL_FAILED"
            execution.raw_response = {
                **entry_order,
                "exchange": _EXCHANGE_LABEL,
                "execution_status": execution.execution_status,
                "order_id": order_id,
                "sl_order_id": "",
                "tp_order_ids": [],
                "mode": _TRADING_MODE,
                "sl_warning": f"SL order failed: {exc}",
            }
            # The proposal is NOT marked EXECUTED — the trade is unprotected and unresolved.
            await self._update_proposal_status(proposal, "NEEDS_ATTENTION")
            await self.db.commit()  # persist so the live, unprotected exposure stays tracked
            raise ExecutionError(
                f"Stop-loss order could not be placed for position {position.id} "
                f"({symbol}): {exc}. The position is OPEN on the exchange WITHOUT a "
                "stop-loss and is flagged NEEDS_ATTENTION — resolve it manually."
            ) from exc

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
                tp_warnings.append(f"TP{i + 1} order failed: {exc}")

        execution.sl_order_id = sl_order_id
        execution.tp_order_ids = tp_order_ids
        execution_payload = {
            **entry_order,
            "exchange": _EXCHANGE_LABEL,
            "execution_status": execution.execution_status,
            "order_id": order_id,
            "sl_order_id": sl_order_id,
            "tp_order_ids": tp_order_ids,
            "mode": _TRADING_MODE,
        }
        if sl_warning:
            execution_payload["sl_warning"] = sl_warning
        if tp_warnings:
            execution_payload["tp_warnings"] = tp_warnings
        execution.raw_response = execution_payload

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
            raw_facts=build_trade_journal_raw_facts(
                proposal=proposal,
                execution_payload=execution_payload,
                position_id=position.id,
                journal_action="executed",
                entry_price=executed_price,
                size=quantity,
            ),
            decision_log=[
                {
                    "action": "executed",
                    "exchange": _EXCHANGE_LABEL,
                    "order_id": order_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "entry_price": executed_price,
                }
            ],
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
        return sorted(take_profit_levels_from_proposal(take_profit))

    @staticmethod
    def _validate_symbol_filters(
        *,
        symbol_info: dict[str, Any],
        position_size_usdt: float,
        mark_price: float,
    ) -> tuple[float, list[str]]:
        errors: list[str] = []
        if mark_price <= 0:
            return 0.0, ["check_5-7_exchange: mark price unavailable"]

        quantity = position_size_usdt / mark_price if position_size_usdt > 0 else 0.0
        filters = {f["filterType"]: f for f in symbol_info.get("filters", [])}

        lot_filter = filters.get("LOT_SIZE")
        if lot_filter:
            step_size = float(lot_filter.get("stepSize", 0.001))
            min_qty = float(lot_filter.get("minQty", 0.001))
            max_qty = float(lot_filter.get("maxQty", float("inf")))
            precision = max(0, round(-math.log10(step_size))) if step_size > 0 else 8
            quantity = (
                round(round(quantity / step_size) * step_size, precision)
                if step_size > 0
                else quantity
            )
            if quantity < min_qty:
                errors.append(f"check_6_qty: quantity={quantity} < minQty={min_qty}")
            if quantity > max_qty:
                errors.append(f"check_6_qty: quantity={quantity} > maxQty={max_qty}")

        market_lot_filter = filters.get("MARKET_LOT_SIZE")
        if market_lot_filter:
            min_qty = float(market_lot_filter.get("minQty", 0))
            max_qty = float(market_lot_filter.get("maxQty", float("inf")))
            if quantity < min_qty:
                errors.append(f"check_6_market_qty: quantity={quantity} < minQty={min_qty}")
            if quantity > max_qty:
                errors.append(f"check_6_market_qty: quantity={quantity} > maxQty={max_qty}")

        notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
        if notional_filter:
            notional = quantity * mark_price
            min_notional = float(
                notional_filter.get("notional") or notional_filter.get("minNotional") or 0
            )
            max_notional = float(notional_filter.get("maxNotional") or float("inf"))
            if min_notional and notional < min_notional:
                errors.append(f"check_7_notional: notional={notional:.2f} < min={min_notional}")
            if max_notional != float("inf") and notional > max_notional:
                errors.append(f"check_7_notional: notional={notional:.2f} > max={max_notional}")

        return quantity, errors

    async def _update_proposal_status(self, proposal: TradeProposal, status: str) -> None:
        proposal.status = status
        await self.db.flush()
