"""Deterministic execution preflight for crypto trade submission."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.exchange_tool import validate_order_request
from app.db.models.crypto_trading import MarketSnapshot, Position, TradeExecution, TradeProposal
from app.services.kill_switch import KillSwitch


class ExecutionPreflightError(Exception):
    """Raised when deterministic trade validation fails before submission."""


@dataclass
class ExecutionPlan:
    entry_price: float
    take_profits: list[float]
    size_usdt: float
    amount: float
    side: str
    direction: str
    market_regime: str
    market_type: str
    # True when the consecutive-loss kill-switch gate was cleared by an explicit single-use
    # acknowledgement. The caller must consume that ack after a real entry order is placed so it
    # authorizes exactly one attempt (mirrors ExecutionService).
    consecutive_loss_ack_used: bool = False


def derive_entry_side(direction: str) -> str:
    """Deterministic entry order side: LONG opens with BUY, SHORT opens with SELL."""
    return "buy" if str(direction or "").upper() == "LONG" else "sell"


def derive_close_side(direction: str) -> str:
    """Deterministic close order side — always the opposite of the entry side."""
    return "sell" if str(direction or "").upper() == "LONG" else "buy"


def validate_directional_risk_levels(
    direction: str,
    entry_price: float,
    stop_loss: float | None,
    take_profits: list[float],
) -> list[str]:
    """Deterministic, direction-aware stop-loss / take-profit relationship check.

    Hard validation only — never reorders or flips values. Returns a list of error strings
    (empty = pass); each string is prefixed with a stable ``reason`` code so callers can surface
    a structured block payload. Skips checks that depend on values another check already flags
    as missing (e.g. a non-positive entry price), since those are reported elsewhere.

    Rules:
      LONG:  stop_loss < entry; every TP > entry; TPs strictly ascending.
      SHORT: stop_loss > entry; every TP < entry; TPs strictly descending.
    """
    errors: list[str] = []
    norm = str(direction or "").upper()

    if norm not in {"LONG", "SHORT"}:
        errors.append(f"invalid_direction: direction must be LONG or SHORT, got {direction!r}")
        return errors

    # Directional relationships are only meaningful against a positive reference price.
    if entry_price <= 0:
        return errors

    if norm == "LONG":
        if stop_loss is not None and stop_loss >= entry_price:
            errors.append(
                f"invalid_long_stop_loss: For LONG, stop_loss ({stop_loss}) must be less than "
                f"entry/reference price ({entry_price})"
            )
        for idx, tp in enumerate(take_profits, start=1):
            if tp <= entry_price:
                errors.append(
                    f"invalid_long_take_profit: For LONG, take_profit[{idx}] ({tp}) must be greater "
                    f"than entry/reference price ({entry_price})"
                )
        if take_profits != sorted(take_profits):
            errors.append(
                f"take_profits_not_ordered: For LONG, take_profits must be ascending, got {take_profits}"
            )
    else:  # SHORT
        if stop_loss is not None and stop_loss <= entry_price:
            errors.append(
                f"invalid_short_stop_loss: For SHORT, stop_loss ({stop_loss}) must be greater than "
                f"entry/reference price ({entry_price})"
            )
        for idx, tp in enumerate(take_profits, start=1):
            if tp >= entry_price:
                errors.append(
                    f"invalid_short_take_profit: For SHORT, take_profit[{idx}] ({tp}) must be less "
                    f"than entry/reference price ({entry_price})"
                )
        if take_profits != sorted(take_profits, reverse=True):
            errors.append(
                f"take_profits_not_ordered: For SHORT, take_profits must be descending, got {take_profits}"
            )

    return errors


def entry_price_from_plan(entry_plan: object) -> float:
    if not isinstance(entry_plan, dict):
        return 0.0
    for key in (
        "primary_entry",
        "entry",
        "price",
        "avg_entry",
        "target_entry",
        "entry_zone_high",
        "entry_zone_low",
    ):
        try:
            value = float(entry_plan.get(key) or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            continue
    levels = entry_plan.get("levels")
    if isinstance(levels, list) and levels:
        try:
            value = float(levels[0])
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return 0.0


def take_profit_levels_from_proposal(raw_levels: object) -> list[float]:
    values: list[float] = []
    for item in raw_levels or []:
        try:
            if isinstance(item, dict):
                candidate = (
                    item.get("tp_level")
                    or item.get("price")
                    or item.get("target")
                    or item.get("level")
                )
            else:
                candidate = item
            if candidate is not None:
                value = float(candidate)
                if value > 0:
                    values.append(value)
        except (TypeError, ValueError):
            continue
    return values


async def latest_market_regime(db: AsyncSession, project_id: UUID) -> str:
    result = await db.execute(
        select(MarketSnapshot.market_regime)
        .where(MarketSnapshot.project_id == project_id)
        .order_by(desc(MarketSnapshot.created_at))
        .limit(1)
    )
    regime = result.scalar_one_or_none()
    return str(regime or "NEUTRAL").upper()


async def prepare_execution_plan(
    *,
    db: AsyncSession,
    project_id: UUID,
    proposal: TradeProposal,
    require_status: str = "APPROVED",
) -> ExecutionPlan:
    errors: list[str] = []
    direction = str(proposal.direction or "").upper()
    market_type = os.getenv("MARKET_TYPE", "futures").lower()

    if require_status and proposal.status != require_status:
        errors.append(f"proposal status={proposal.status} require={require_status}")
    if proposal.expires_at and proposal.expires_at < datetime.now(UTC):
        errors.append(f"proposal expired at {proposal.expires_at.isoformat()}")
    if not str(proposal.symbol or "").strip():
        errors.append("symbol is missing")
    if direction not in {"LONG", "SHORT"}:
        errors.append(f"invalid direction={direction or '<empty>'}")

    entry_price = entry_price_from_plan(proposal.entry_plan)
    if entry_price <= 0:
        errors.append("entry price is missing or non-positive")

    take_profits = take_profit_levels_from_proposal(proposal.take_profit)
    if not proposal.stop_loss:
        errors.append("stop_loss is missing")
    if not take_profits:
        errors.append("take_profit levels are missing")

    requested_size_usdt = float(proposal.position_size_usdt or 0)
    if requested_size_usdt <= 0:
        errors.append("position_size_usdt must be positive")

    if market_type == "spot" and direction == "SHORT":
        errors.append("spot market does not support opening SHORT positions")

    active_execution_result = await db.execute(
        select(TradeExecution.id).where(
            TradeExecution.project_id == project_id,
            TradeExecution.proposal_id == proposal.id,
            TradeExecution.execution_status.in_(["SUCCESS", "PENDING"]),
        )
    )
    if active_execution_result.scalar_one_or_none() is not None:
        errors.append("proposal already has an active execution record")

    duplicate_position_result = await db.execute(
        select(Position.id).where(
            Position.project_id == project_id,
            Position.symbol == proposal.symbol,
            Position.side == direction,
            Position.status == "OPEN",
        )
    )
    if duplicate_position_result.scalar_one_or_none() is not None:
        errors.append(f"open {direction} position already exists for {proposal.symbol}")

    market_regime = await latest_market_regime(db, project_id)
    ks = KillSwitch(db)
    ks_result = await ks.check(
        project_id=project_id,
        symbol=proposal.symbol,
        direction=direction,
        stop_loss=proposal.stop_loss,
        take_profit_levels=take_profits,
        proposed_size_usdt=requested_size_usdt,
        entry_price=entry_price,
        market_regime=market_regime,
    )
    if not ks_result.passed:
        errors.extend(ks_result.blocked_reasons)

    size_usdt = float(ks_result.adjusted_position_size_usdt or requested_size_usdt)
    if entry_price > 0:
        raw_amount = size_usdt / entry_price
        # Futures typical stepSize is 0.001; snap to 3dp so LOT_SIZE preflight passes.
        # Spot BUY MARKET uses quoteOrderQty so precision is irrelevant there.
        amount = round(raw_amount, 3) if market_type == "futures" else round(raw_amount, 8)
    else:
        amount = 0.0
    if amount <= 0:
        errors.append("computed base quantity is non-positive")

    errors.extend(
        validate_directional_risk_levels(direction, entry_price, proposal.stop_loss, take_profits)
    )

    side = derive_entry_side(direction)
    validation = await validate_order_request(
        symbol=proposal.symbol,
        side=side,
        amount=amount,
        order_type="market",
        price=entry_price,
        stop_loss=proposal.stop_loss,
        take_profits=take_profits,
        notional_usdt=size_usdt,
    )
    if not validation.get("passed", False):
        errors.extend([str(item) for item in validation.get("errors", [])])

    if errors:
        raise ExecutionPreflightError("Execution preflight failed: " + " | ".join(errors))

    return ExecutionPlan(
        entry_price=entry_price,
        take_profits=take_profits,
        size_usdt=size_usdt,
        amount=amount,
        side=side,
        direction=direction,
        market_regime=market_regime,
        market_type=market_type,
        consecutive_loss_ack_used=ks_result.consecutive_loss_ack_used,
    )
