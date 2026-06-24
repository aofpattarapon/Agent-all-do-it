"""Risk Kill Switch — pure Python, zero AI involvement."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import desc, func, select, update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class KillSwitchConfig:
    max_daily_loss_pct: float = float(os.getenv("KILL_SWITCH_MAX_DAILY_LOSS_PCT", "2.0"))
    max_open_positions: int = int(os.getenv("KILL_SWITCH_MAX_OPEN_POSITIONS", "3"))
    max_risk_per_trade_pct: float = float(os.getenv("KILL_SWITCH_MAX_RISK_PER_TRADE_PCT", "1.0"))
    max_leverage: float = 1.0
    block_after_consecutive_losses: int = int(os.getenv("KILL_SWITCH_CONSECUTIVE_LOSS_BLOCK", "3"))
    min_risk_reward: float = 2.0
    require_sl: bool = True
    require_tp: bool = True
    proposal_expiry_minutes: int = int(os.getenv("KILL_SWITCH_PROPOSAL_EXPIRY_MINUTES", "30"))
    block_longs_in_risk_off: bool = True
    portfolio_usdt: float = float(os.getenv("PAPER_PORTFOLIO_USDT", "1000.0"))


@dataclass
class KillSwitchResult:
    passed: bool
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adjusted_position_size_usdt: float | None = None
    checks_run: list[str] = field(default_factory=list)
    # True when the consecutive-loss block was bypassed by an explicit, audited
    # strategy-review acknowledgement. The caller consumes that single-use ack after
    # the order attempt (see ExecutionService._execute_proposal).
    consecutive_loss_ack_used: bool = False


class KillSwitch:
    def __init__(self, db: AsyncSession, config: KillSwitchConfig | None = None) -> None:
        self.db = db
        self.cfg = config or KillSwitchConfig()

    async def check(
        self,
        *,
        project_id: UUID,
        symbol: str,
        direction: str,
        stop_loss: float | None,
        take_profit_levels: list[float],
        proposed_size_usdt: float,
        entry_price: float,
        market_regime: str = "NEUTRAL",
    ) -> KillSwitchResult:
        from app.db.models.crypto_trading import Position, TradeJournal

        blocked: list[str] = []
        warnings: list[str] = []
        checks: list[str] = []
        adjusted_size = proposed_size_usdt
        consecutive_loss_ack_used = False

        checks.append("sl_required")
        if self.cfg.require_sl and not stop_loss:
            blocked.append("NO_STOP_LOSS: A stop loss is required for every trade.")

        checks.append("tp_required")
        if self.cfg.require_tp and not take_profit_levels:
            blocked.append("NO_TAKE_PROFIT: At least one take profit level is required.")

        checks.append("risk_reward")
        norm_direction = direction.upper()
        if stop_loss and take_profit_levels and entry_price > 0:
            # Signed, direction-aware distances: a wrong-direction SL/TP yields a
            # non-positive distance and is blocked rather than masked by abs().
            if norm_direction == "LONG":
                sl_dist = entry_price - stop_loss
                tp_dist = take_profit_levels[0] - entry_price
            else:  # SHORT
                sl_dist = stop_loss - entry_price
                tp_dist = entry_price - take_profit_levels[0]

            if sl_dist <= 0 or tp_dist <= 0:
                blocked.append(
                    f"WRONG_DIRECTION_SL_TP: For {norm_direction}, stop_loss ({stop_loss}) and "
                    f"take_profit ({take_profit_levels[0]}) are on the wrong side of entry "
                    f"({entry_price})."
                )
            else:
                rr = round(tp_dist / sl_dist, 2)
                if rr < self.cfg.min_risk_reward:
                    blocked.append(
                        f"POOR_RR: Risk/Reward={rr} is below minimum {self.cfg.min_risk_reward}:1"
                    )

        checks.append("risk_per_trade")
        if stop_loss and entry_price > 0 and proposed_size_usdt > 0:
            signed_sl_dist = (
                entry_price - stop_loss if norm_direction == "LONG" else stop_loss - entry_price
            )
            sl_pct = abs(signed_sl_dist) / entry_price
            max_loss_usdt = proposed_size_usdt * sl_pct
            risk_pct = (max_loss_usdt / self.cfg.portfolio_usdt) * 100
            if risk_pct > self.cfg.max_risk_per_trade_pct:
                safe_loss = self.cfg.portfolio_usdt * (self.cfg.max_risk_per_trade_pct / 100)
                adjusted_size = round(safe_loss / sl_pct, 2) if sl_pct > 0 else proposed_size_usdt
                warnings.append(
                    f"SIZE_REDUCED: Risk {risk_pct:.2f}% > limit {self.cfg.max_risk_per_trade_pct}%. "
                    f"Size reduced from {proposed_size_usdt} → {adjusted_size} USDT."
                )

        checks.append("market_regime")
        if (
            self.cfg.block_longs_in_risk_off
            and market_regime == "RISK_OFF"
            and direction.upper() == "LONG"
        ):
            blocked.append("MARKET_RISK_OFF: No new LONG positions during RISK_OFF market regime.")

        checks.append("leverage")
        if self.cfg.max_leverage <= 1.0:
            warnings.append("LEVERAGE: Max leverage is 1x (spot/no-leverage mode).")

        checks.append("max_positions")
        try:
            stmt = select(func.count()).where(
                Position.project_id == project_id,
                Position.status == "OPEN",
            )
            result = await self.db.execute(stmt)
            open_count = result.scalar() or 0
            if open_count >= self.cfg.max_open_positions:
                blocked.append(
                    f"MAX_POSITIONS: {open_count}/{self.cfg.max_open_positions} positions open. "
                    "Close existing positions first."
                )
        except Exception as exc:
            # Fail CLOSED: a risk check we cannot evaluate must block the trade, never
            # silently pass. Letting it through would disable the kill switch exactly
            # when the system is least healthy.
            logger.warning("Could not check open positions — blocking: %s", exc)
            blocked.append(f"POSITION_CHECK_UNAVAILABLE: max-positions check failed ({exc}).")

        checks.append("daily_loss")
        try:
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = select(func.sum(TradeJournal.realized_pnl)).where(
                TradeJournal.project_id == project_id,
                TradeJournal.created_at >= today_start,
                TradeJournal.result == "LOSS",
            )
            result = await self.db.execute(stmt)
            daily_loss = abs(result.scalar() or 0.0)
            daily_loss_pct = (daily_loss / self.cfg.portfolio_usdt) * 100
            if daily_loss_pct >= self.cfg.max_daily_loss_pct:
                blocked.append(
                    f"DAILY_LOSS_LIMIT: Lost {daily_loss_pct:.2f}% today "
                    f"(limit: {self.cfg.max_daily_loss_pct}%). No more trades today."
                )
            elif daily_loss_pct >= self.cfg.max_daily_loss_pct * 0.8:
                warnings.append(
                    f"DAILY_LOSS_WARNING: {daily_loss_pct:.2f}% daily loss "
                    f"(80% of {self.cfg.max_daily_loss_pct}% limit)."
                )
        except Exception as exc:
            # Fail CLOSED — see max_positions rationale above.
            logger.warning("Could not check daily loss — blocking: %s", exc)
            blocked.append(f"DAILY_LOSS_CHECK_UNAVAILABLE: daily-loss check failed ({exc}).")

        checks.append("consecutive_losses")
        try:
            stmt = (
                select(TradeJournal.result)
                .where(TradeJournal.project_id == project_id)
                .order_by(desc(TradeJournal.created_at))
                .limit(self.cfg.block_after_consecutive_losses)
            )
            result = await self.db.execute(stmt)
            recent = [row[0] for row in result.fetchall()]
            if len(recent) >= self.cfg.block_after_consecutive_losses and all(
                item == "LOSS" for item in recent
            ):
                # An explicit, audited strategy-review acknowledgement may bypass THIS gate
                # only. It is read fail-closed (a missing/expired/used/invalid ack → block) and
                # never affects any other check above. The single-use ack is consumed by the
                # caller after the order attempt.
                from app.services import risk_ack

                ack = await risk_ack.get_active_ack(self.db, project_id)
                if ack is not None:
                    consecutive_loss_ack_used = True
                    checks.append("consecutive_losses_ack")
                    warnings.append(
                        f"CONSECUTIVE_LOSSES_ACK: consecutive-loss block bypassed by an explicit "
                        f"strategy-review acknowledgement recorded by {ack.get('acknowledged_by')} "
                        f"at {ack.get('acknowledged_at')} (reason: {ack.get('reason')}). All other "
                        "risk checks still apply; this acknowledgement is single-use."
                    )
                else:
                    blocked.append(
                        f"CONSECUTIVE_LOSSES: Last {self.cfg.block_after_consecutive_losses} trades "
                        "all lost. Review strategy before continuing."
                    )
        except Exception as exc:
            # Fail CLOSED — see max_positions rationale above.
            logger.warning("Could not check consecutive losses — blocking: %s", exc)
            blocked.append(
                f"CONSECUTIVE_LOSSES_CHECK_UNAVAILABLE: consecutive-losses check failed ({exc})."
            )

        return KillSwitchResult(
            passed=len(blocked) == 0,
            blocked_reasons=blocked,
            warnings=warnings,
            adjusted_position_size_usdt=adjusted_size
            if adjusted_size != proposed_size_usdt
            else None,
            checks_run=checks,
            consecutive_loss_ack_used=consecutive_loss_ack_used,
        )

    async def expire_old_proposals(self, project_id: UUID) -> int:
        """Auto-expire pending proposals past the configured timeout."""
        from app.db.models.crypto_trading import TradeProposal

        cutoff = datetime.now(UTC) - timedelta(minutes=self.cfg.proposal_expiry_minutes)
        stmt = (
            update(TradeProposal)
            .where(
                TradeProposal.project_id == project_id,
                TradeProposal.status == "PENDING_APPROVAL",
                TradeProposal.created_at < cutoff,
            )
            .values(status="EXPIRED")
            .returning(TradeProposal.id)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        expired = len(result.fetchall())
        if expired:
            logger.info("Expired %d proposals for project %s", expired, project_id)
        return expired
