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

        checks.append("sl_required")
        if self.cfg.require_sl and not stop_loss:
            blocked.append("NO_STOP_LOSS: A stop loss is required for every trade.")

        checks.append("tp_required")
        if self.cfg.require_tp and not take_profit_levels:
            blocked.append("NO_TAKE_PROFIT: At least one take profit level is required.")

        checks.append("risk_reward")
        if stop_loss and take_profit_levels and entry_price > 0:
            sl_dist = abs(entry_price - stop_loss)
            tp_dist = abs(take_profit_levels[0] - entry_price)
            if sl_dist > 0:
                rr = round(tp_dist / sl_dist, 2)
                if rr < self.cfg.min_risk_reward:
                    blocked.append(
                        f"POOR_RR: Risk/Reward={rr} is below minimum {self.cfg.min_risk_reward}:1"
                    )

        checks.append("risk_per_trade")
        if stop_loss and entry_price > 0 and proposed_size_usdt > 0:
            sl_pct = abs(entry_price - stop_loss) / entry_price
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
        if self.cfg.block_longs_in_risk_off and market_regime == "RISK_OFF" and direction.upper() == "LONG":
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
            logger.warning("Could not check open positions: %s", exc)
            warnings.append(f"POSITION_CHECK_SKIPPED: {exc}")

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
            logger.warning("Could not check daily loss: %s", exc)
            warnings.append(f"DAILY_LOSS_CHECK_SKIPPED: {exc}")

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
            if (
                len(recent) >= self.cfg.block_after_consecutive_losses
                and all(item == "LOSS" for item in recent)
            ):
                blocked.append(
                    f"CONSECUTIVE_LOSSES: Last {self.cfg.block_after_consecutive_losses} trades "
                    "all lost. Review strategy before continuing."
                )
        except Exception as exc:
            logger.warning("Could not check consecutive losses: %s", exc)

        return KillSwitchResult(
            passed=len(blocked) == 0,
            blocked_reasons=blocked,
            warnings=warnings,
            adjusted_position_size_usdt=adjusted_size if adjusted_size != proposed_size_usdt else None,
            checks_run=checks,
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
