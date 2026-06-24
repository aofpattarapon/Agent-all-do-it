"""Persistence helpers for crypto workflow outputs."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.json_utils import extract_json_object
from app.db.models.crypto_trading import (
    AgentVote,
    CryptoRawPayload,
    MarketSnapshot,
    NewsEvent,
    TradeProposal,
)
from app.services.kill_switch import KillSwitch, KillSwitchConfig

logger = logging.getLogger(__name__)


class ProposalValidationError(Exception):
    """Raised when compile_proposal output is structurally invalid (entry=0, missing fields, etc.)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def build_trade_journal_raw_facts(
    *,
    proposal: TradeProposal,
    execution_payload: dict,
    position_id: UUID | str | None,
    journal_action: str,
    entry_price: float,
    size: float,
) -> dict:
    return {
        "symbol": proposal.symbol,
        "direction": proposal.direction,
        "position_id": str(position_id) if position_id else None,
        "journal_action": journal_action,
        "entry_price": entry_price,
        "size": size,
        "proposal": {
            "id": str(proposal.id),
            "run_id": str(proposal.run_id),
            "status": proposal.status,
            "entry_plan": proposal.entry_plan or {},
            "take_profit": proposal.take_profit or [],
            "stop_loss": proposal.stop_loss,
            "position_size_usdt": proposal.position_size_usdt,
            "full_proposal_md": proposal.full_proposal_md,
            "news_summary": proposal.news_summary,
            "agent_vote_summary": proposal.agent_vote_summary or {},
            "raw_payload": proposal.raw_payload or {},
        },
        "execution": execution_payload,
    }


class CryptoPersistenceService:
    """Persist structured crypto-agent outputs into domain tables."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def persist_agent_output(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        agent_role: str,
        output_text: str,
    ) -> None:
        payload = self._load_json(output_text)
        if payload is None:
            return

        await self.store_raw_payload(
            project_id=project_id,
            run_id=run_id,
            payload_kind=agent_role,
            agent_role=agent_role,
            step_key=agent_role,
            payload=payload,
        )

        if agent_role == "news_monitor":
            await self.save_news_events(project_id=project_id, run_id=run_id, payload=payload)
            return
        if agent_role == "source_reliability":
            await self.update_news_reliability(
                project_id=project_id, run_id=run_id, payload=payload
            )
            return
        if agent_role == "market_regime":
            await self.save_market_snapshot(project_id=project_id, run_id=run_id, payload=payload)
            return
        if agent_role.startswith("hawk_") or agent_role == "sage":
            await self.save_agent_vote(
                project_id=project_id, run_id=run_id, agent_role=agent_role, payload=payload
            )
            return
        if agent_role == "trade_proposal":
            await self.save_trade_proposal(project_id=project_id, run_id=run_id, payload=payload)

    async def store_raw_payload(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        payload_kind: str,
        payload: dict,
        agent_role: str | None = None,
        step_key: str | None = None,
    ) -> CryptoRawPayload:
        record = CryptoRawPayload(
            project_id=project_id,
            run_id=run_id,
            payload_kind=payload_kind[:50],
            agent_role=agent_role[:50] if agent_role else None,
            step_key=step_key[:100] if step_key else None,
            payload_json=payload,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def save_news_events(self, *, project_id: UUID, run_id: UUID, payload: dict) -> None:
        items = payload.get("news_items")
        if not isinstance(items, list):
            return
        sources_checked = payload.get("sources_checked")
        source_type = "aggregated"
        if isinstance(sources_checked, list) and sources_checked:
            source_type = str(sources_checked[0])[:50]

        for item in items:
            if not isinstance(item, dict):
                continue
            news_id = str(item.get("news_id") or "").strip()
            headline = str(item.get("headline") or "").strip()
            source = str(item.get("source") or "").strip()
            if not news_id or not headline or not source:
                continue

            existing = await self._latest_news_event(
                project_id=project_id, run_id=run_id, news_id=news_id
            )
            values = {
                "headline": headline,
                "source": source,
                "source_type": source_type,
                "published_at": self._parse_datetime(item.get("published_at")),
                "related_assets": self._string_list(item.get("related_assets")),
                "category": str(item.get("category") or "UNKNOWN")[:100],
                "urgency": str(item.get("urgency") or "MEDIUM")[:20],
                "risk_flags": self._string_list(item.get("risk_flags")),
                "raw_summary": self._optional_str(item.get("raw_summary")),
            }
            if existing is None:
                self.db.add(
                    NewsEvent(
                        project_id=project_id,
                        run_id=run_id,
                        news_id=news_id,
                        reliability_score=self._as_int(item.get("reliability_score")),
                        reliability_status=self._optional_str(
                            item.get("reliability_status"), max_len=30
                        ),
                        used_for_trade=False,
                        **values,
                    )
                )
            else:
                for field, value in values.items():
                    setattr(existing, field, value)
                existing.reliability_score = (
                    self._as_int(item.get("reliability_score")) or existing.reliability_score
                )
                existing.reliability_status = (
                    self._optional_str(item.get("reliability_status"), max_len=30)
                    or existing.reliability_status
                )
                self.db.add(existing)
        await self.db.flush()

    async def update_news_reliability(
        self, *, project_id: UUID, run_id: UUID, payload: dict
    ) -> None:
        items = payload.get("items")
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            news_id = str(item.get("news_id") or "").strip()
            if not news_id:
                continue
            existing = await self._latest_news_event(
                project_id=project_id, run_id=run_id, news_id=news_id
            )
            if existing is None:
                headline = str(item.get("headline") or "").strip()
                if not headline:
                    continue
                existing = NewsEvent(
                    project_id=project_id,
                    run_id=run_id,
                    news_id=news_id,
                    headline=headline,
                    source="source_reliability",
                    source_type="source_reliability",
                    related_assets=[],
                    category="UNCLASSIFIED",
                    urgency="MEDIUM",
                    risk_flags=[],
                    used_for_trade=False,
                )
                self.db.add(existing)
            existing.reliability_score = self._as_int(item.get("reliability_score"))
            existing.reliability_status = self._optional_str(
                item.get("reliability_status"), max_len=30
            )
            existing.risk_flags = self._string_list(item.get("risk_flags"))
            self.db.add(existing)
        await self.db.flush()

    async def save_market_snapshot(self, *, project_id: UUID, run_id: UUID, payload: dict) -> None:
        existing = await self._latest_market_snapshot(project_id=project_id, run_id=run_id)
        values = {
            "snapshot_at": self._parse_datetime(payload.get("assessed_at")) or datetime.now(UTC),
            "market_regime": str(payload.get("market_regime") or "NEUTRAL")[:30],
            "altcoin_condition": self._optional_str(payload.get("altcoin_condition"), max_len=30),
            "btc_condition": self._optional_str(payload.get("btc_condition"), max_len=30),
            "volatility_level": self._optional_str(payload.get("volatility_level"), max_len=20),
            "fear_greed_index": self._as_int(payload.get("fear_greed_index")),
            "btc_dominance": self._as_float(payload.get("btc_dominance_pct")),
            "funding_rate_btc": self._as_float(payload.get("funding_rate_btc")),
            "long_short_ratio": self._as_float(payload.get("long_short_ratio")),
            "trade_permission": str(payload.get("trade_permission") or "ALLOW")[:30],
            "raw_data": payload,
        }
        if existing is None:
            self.db.add(MarketSnapshot(project_id=project_id, run_id=run_id, **values))
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            self.db.add(existing)
        await self.db.flush()

    async def save_agent_vote(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        agent_role: str,
        payload: dict,
    ) -> None:
        existing = await self._latest_agent_vote(
            project_id=project_id, run_id=run_id, agent_role=agent_role
        )
        vote_value = payload.get("vote")
        if agent_role == "sage":
            vote_value = payload.get("sage_decision")

        values = {
            "agent_name": str(payload.get("agent") or agent_role)[:100],
            "agent_role": agent_role[:50],
            "vote": str(vote_value or "UNKNOWN")[:20],
            "confidence": self._as_int(payload.get("confidence")) or 0,
            "reasoning": self._optional_str(payload.get("reasoning")) or "",
            "veto_reason": self._optional_str(payload.get("veto_reason")),
        }
        if existing is None:
            self.db.add(AgentVote(project_id=project_id, run_id=run_id, **values))
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            self.db.add(existing)
        await self.db.flush()

    @staticmethod
    def _is_sage_approved(payload: dict) -> bool:
        """Return True only when SAGE approval is explicitly the boolean ``True``.

        Accepts the flag at the top level (``payload["sage_approved"]``) OR nested
        under ``payload["agent_vote_summary"]["sage_approved"]`` — some models emit
        the approval flag only inside the vote summary (observed in the W13 Auto run).
        Strict boolean ``True`` is required at either location; missing values and
        falsy/string values remain fail-closed (no persistence).
        """
        if payload.get("sage_approved") is True:
            return True
        vote_summary = payload.get("agent_vote_summary")
        return isinstance(vote_summary, dict) and vote_summary.get("sage_approved") is True

    async def save_trade_proposal(
        self, *, project_id: UUID, run_id: UUID, payload: dict
    ) -> TradeProposal | None:
        if not self._is_sage_approved(payload):
            # Fail-closed: do not persist a proposal SAGE did not approve. Surface the
            # reason (instead of a silent ``return None``) so the run step records it via
            # run_executor's ProposalValidationError → meta["proposal_validation_error"].
            raise ProposalValidationError(
                "SAGE_NOT_APPROVED: sage_approved is not True at top level or under "
                f"agent_vote_summary — proposal not persisted (run_id={run_id})"
            )

        symbol = str(payload.get("symbol") or "").strip()
        direction = str(payload.get("direction") or "").strip().upper()
        entry_plan = payload.get("entry_plan")
        take_profit = payload.get("take_profit")
        stop_loss = self._as_float(payload.get("stop_loss"))
        notional_usdt = self._as_float(
            payload.get("notional_usdt") or payload.get("position_size_usdt")
        )

        if not symbol:
            raise ProposalValidationError(f"PROPOSAL_INVALID: symbol is missing (run_id={run_id})")
        if direction not in {"LONG", "SHORT"}:
            raise ProposalValidationError(
                f"PROPOSAL_INVALID: direction={direction!r} not LONG/SHORT (run_id={run_id})"
            )
        if not isinstance(entry_plan, dict):
            raise ProposalValidationError(
                f"PROPOSAL_INVALID: entry_plan is not a dict — got {type(entry_plan).__name__} (run_id={run_id})"
            )
        if not payload.get("side") and direction not in {"LONG", "SHORT"}:
            raise ProposalValidationError(
                f"PROPOSAL_INVALID: side missing and direction={direction!r} (run_id={run_id})"
            )

        entry_price = self._entry_price(entry_plan)
        normalized_take_profit = self._normalize_take_profit_items(
            take_profit,
            entry_price=entry_price,
            stop_loss=stop_loss,
            direction=direction,
        )
        tp_levels = self._take_profit_levels(normalized_take_profit)
        if entry_price <= 0:
            raise ProposalValidationError(
                f"DATA_FAILURE: entry_price={entry_price} <= 0 — compile_proposal had no real market data "
                f"(symbol={symbol}, direction={direction}, run_id={run_id})"
            )
        if stop_loss is None:
            raise ProposalValidationError(
                f"DATA_FAILURE: stop_loss is None — compile_proposal output incomplete "
                f"(symbol={symbol}, direction={direction}, entry_price={entry_price}, run_id={run_id})"
            )
        if not tp_levels:
            raise ProposalValidationError(
                f"DATA_FAILURE: take_profit levels are empty "
                f"(symbol={symbol}, direction={direction}, run_id={run_id})"
            )
        if not notional_usdt or notional_usdt <= 0:
            raise ProposalValidationError(
                f"PROPOSAL_INVALID: notional_usdt/position_size_usdt is missing or zero "
                f"(symbol={symbol}, direction={direction}, run_id={run_id})"
            )

        _market_type = os.getenv("MARKET_TYPE", "futures").lower()
        if _market_type == "futures":
            _min_notional = float(os.getenv("MIN_FUTURES_NOTIONAL_USDT", "50.0"))
            if notional_usdt < _min_notional:
                raise ProposalValidationError(
                    f"PROPOSAL_NOTIONAL_BELOW_EXCHANGE_MINIMUM: position_size_usdt {notional_usdt} < "
                    f"minNotional {_min_notional} for futures market "
                    f"(symbol={symbol}, direction={direction}, run_id={run_id})"
                )

        market_snapshot = await self._latest_market_snapshot(project_id=project_id, run_id=run_id)
        market_regime = market_snapshot.market_regime if market_snapshot is not None else "NEUTRAL"
        proposed_size = self._as_float(payload.get("position_size_usdt")) or 0.0
        normalized_rr = self._first_risk_reward(
            take_profit=normalized_take_profit,
            entry_price=entry_price,
            stop_loss=stop_loss,
            direction=direction,
        )
        normalized_max_loss = self._max_loss_usdt(
            entry_price=entry_price,
            stop_loss=stop_loss,
            position_size_usdt=proposed_size,
        )

        kill_switch = KillSwitch(self.db, KillSwitchConfig())
        ks_result = await kill_switch.check(
            project_id=project_id,
            symbol=symbol,
            direction=direction,
            stop_loss=stop_loss,
            take_profit_levels=tp_levels,
            proposed_size_usdt=proposed_size,
            entry_price=entry_price,
            market_regime=market_regime,
        )
        ks_blocked = not ks_result.passed
        block_reason = ""
        if ks_blocked:
            # W28E persist-then-promote: do NOT silently drop a valid, SAGE-approved proposal just
            # because the kill switch is armed. Persist it in an explicit, non-executable
            # ``BLOCKED_KILL_SWITCH`` state so the proposal is traceable and can be safely promoted
            # later ONLY if an explicit warmup approval/resume re-validates it (the kill switch
            # clears or a valid single-use risk_ack exists). Execution stays fail-closed:
            # ``_run_exchange_execute`` requires ``status == "APPROVED"`` and
            # ``prepare_execution_plan`` re-runs the kill switch before any order, so a row left in
            # this state can never reach the exchange.
            block_reason = "KILL_SWITCH_BLOCKED: " + (
                "; ".join(ks_result.blocked_reasons) or "blocked"
            )
            logger.info(
                "Persisting kill-switch-blocked proposal as BLOCKED_KILL_SWITCH (non-executable) "
                "for %s: %s",
                symbol,
                block_reason,
            )

        existing = await self._latest_trade_proposal(project_id=project_id, run_id=run_id)
        hawk_vote_count = await self._count_hawk_votes(project_id=project_id, run_id=run_id)
        expires_at = datetime.now(UTC) + timedelta(
            minutes=KillSwitchConfig().proposal_expiry_minutes
        )
        news_events = await self._news_events_for_run(project_id=project_id, run_id=run_id)

        values = {
            "symbol": symbol[:30],
            "direction": direction[:10],
            "strategy_type": self._optional_str(payload.get("strategy_type"), max_len=100),
            "time_horizon": self._optional_str(payload.get("time_horizon"), max_len=50),
            "entry_plan": entry_plan,
            "take_profit": normalized_take_profit,
            "stop_loss": stop_loss,
            "risk_reward": normalized_rr,
            "position_size_usdt": ks_result.adjusted_position_size_usdt or proposed_size,
            "max_loss_usdt": normalized_max_loss,
            "total_score": self._as_float(payload.get("total_score")),
            "hawk_votes": hawk_vote_count,
            "sage_approved": True,
            "kill_switch_passed": ks_result.passed,
            "kill_switch_details": {
                "warnings": ks_result.warnings,
                "checks_run": ks_result.checks_run,
                "blocked_reasons": ks_result.blocked_reasons,
                "adjusted_position_size_usdt": ks_result.adjusted_position_size_usdt,
                "proposal_normalized": True,
            },
            "agent_vote_summary": payload.get("agent_vote_summary")
            if isinstance(payload.get("agent_vote_summary"), dict)
            else {},
            "news_summary": self._optional_str(payload.get("news_summary")),
            # Blocked proposals are persisted in a distinct, non-executable status so they are
            # never picked up by execute_trade (APPROVED) or auto-execute (PENDING_APPROVAL); they
            # can only become executable via an explicit, re-validated warmup promotion.
            "status": "BLOCKED_KILL_SWITCH" if ks_blocked else "PENDING_APPROVAL",
            "rejection_reason": block_reason or None,
            "expires_at": expires_at,
            "full_proposal_md": self._optional_str(payload.get("full_proposal_md")),
            "raw_payload": payload,
        }
        if (
            values["max_loss_usdt"] is None
            and values["position_size_usdt"]
            and stop_loss
            and entry_price > 0
        ):
            sl_pct = abs(entry_price - stop_loss) / entry_price
            values["max_loss_usdt"] = round(values["position_size_usdt"] * sl_pct, 4)

        if existing is None:
            proposal = TradeProposal(
                project_id=project_id,
                run_id=run_id,
                **values,
            )
            self.db.add(proposal)
        else:
            proposal = existing
            for field, value in values.items():
                setattr(proposal, field, value)
            self.db.add(proposal)

        for event in news_events:
            event.used_for_trade = True
            self.db.add(event)

        await self.db.flush()
        return proposal

    async def _latest_news_event(
        self, *, project_id: UUID, run_id: UUID, news_id: str
    ) -> NewsEvent | None:
        result = await self.db.execute(
            select(NewsEvent)
            .where(
                NewsEvent.project_id == project_id,
                NewsEvent.run_id == run_id,
                NewsEvent.news_id == news_id,
            )
            .order_by(NewsEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_market_snapshot(
        self, *, project_id: UUID, run_id: UUID
    ) -> MarketSnapshot | None:
        result = await self.db.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.project_id == project_id, MarketSnapshot.run_id == run_id)
            .order_by(MarketSnapshot.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_agent_vote(
        self, *, project_id: UUID, run_id: UUID, agent_role: str
    ) -> AgentVote | None:
        result = await self.db.execute(
            select(AgentVote)
            .where(
                AgentVote.project_id == project_id,
                AgentVote.run_id == run_id,
                AgentVote.agent_role == agent_role,
            )
            .order_by(AgentVote.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_trade_proposal(
        self, *, project_id: UUID, run_id: UUID
    ) -> TradeProposal | None:
        result = await self.db.execute(
            select(TradeProposal)
            .where(TradeProposal.project_id == project_id, TradeProposal.run_id == run_id)
            .order_by(TradeProposal.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _count_hawk_votes(self, *, project_id: UUID, run_id: UUID) -> int:
        result = await self.db.execute(
            select(AgentVote).where(
                AgentVote.project_id == project_id,
                AgentVote.run_id == run_id,
                AgentVote.agent_role.in_(["hawk_trend", "hawk_structure", "hawk_counter"]),
            )
        )
        return len(result.scalars().all())

    async def _news_events_for_run(self, *, project_id: UUID, run_id: UUID) -> list[NewsEvent]:
        result = await self.db.execute(
            select(NewsEvent).where(NewsEvent.project_id == project_id, NewsEvent.run_id == run_id)
        )
        return list(result.scalars().all())

    @staticmethod
    def _load_json(output_text: str) -> dict | None:
        payload = extract_json_object(output_text)
        if payload is None:
            logger.debug("Skipping crypto persistence for non-JSON output")
        else:
            return payload
        return payload

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item is not None]

    @staticmethod
    def _optional_str(value: object, *, max_len: int | None = None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if max_len is not None:
            return text[:max_len]
        return text

    @staticmethod
    def _as_int(value: object) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value: object) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    @classmethod
    def _entry_price(cls, entry_plan: dict) -> float:
        for key in ("primary_entry", "entry_zone_high", "entry_zone_low"):
            value = cls._as_float(entry_plan.get(key))
            if value and value > 0:
                return value
        return 0.0

    @classmethod
    def _take_profit_levels(cls, take_profit: object) -> list[float]:
        if not isinstance(take_profit, list):
            return []
        levels: list[float] = []
        for item in take_profit:
            if not isinstance(item, dict):
                continue
            value = cls._as_float(item.get("tp_level"))
            if value and value > 0:
                levels.append(value)
        return levels

    @classmethod
    def _normalize_take_profit_items(
        cls,
        take_profit: object,
        *,
        entry_price: float,
        stop_loss: float | None,
        direction: str,
    ) -> list[dict]:
        if not isinstance(take_profit, list):
            return []
        normalized: list[dict] = []
        risk_distance = (
            abs(entry_price - stop_loss) if stop_loss is not None and entry_price > 0 else 0.0
        )
        for item in take_profit:
            if not isinstance(item, dict):
                continue
            rr_ratio = cls._as_float(item.get("rr_ratio"))
            tp_level = cls._as_float(item.get("tp_level"))
            if rr_ratio and risk_distance > 0:
                derived = (
                    entry_price + (risk_distance * rr_ratio)
                    if direction == "LONG"
                    else entry_price - (risk_distance * rr_ratio)
                )
                tp_level = round(derived, 4)
            if tp_level is None or tp_level <= 0:
                continue
            normalized.append(
                {
                    "tp_level": tp_level,
                    "rr_ratio": rr_ratio,
                    "size_pct": cls._as_int(item.get("size_pct")) or 0,
                }
            )
        return normalized

    @classmethod
    def _first_risk_reward(
        cls,
        *,
        take_profit: list[dict],
        entry_price: float,
        stop_loss: float | None,
        direction: str,
    ) -> float | None:
        if not take_profit or stop_loss is None or entry_price <= 0:
            return None
        first_tp = cls._as_float(take_profit[0].get("tp_level"))
        if first_tp is None:
            return None
        risk_distance = abs(entry_price - stop_loss)
        if risk_distance <= 0:
            return None
        reward_distance = (
            (first_tp - entry_price) if direction == "LONG" else (entry_price - first_tp)
        )
        if reward_distance <= 0:
            return None
        return round(reward_distance / risk_distance, 4)

    @staticmethod
    def _max_loss_usdt(
        *, entry_price: float, stop_loss: float | None, position_size_usdt: float
    ) -> float | None:
        if stop_loss is None or entry_price <= 0 or position_size_usdt <= 0:
            return None
        sl_pct = abs(entry_price - stop_loss) / entry_price
        return round(position_size_usdt * sl_pct, 4)

    async def get_project_winrate(self, project_id: UUID) -> float:
        """Returns win rate as a percentage (0-100). Returns 0.0 if no closed trades."""
        from app.db.models.crypto_trading import TradeJournal

        result = await self.db.execute(
            select(TradeJournal).where(
                TradeJournal.project_id == project_id,
                TradeJournal.result.in_(["WIN", "LOSS"]),
            )
        )
        trades = result.scalars().all()
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.result == "WIN")
        return round((wins / len(trades)) * 100, 1)

    async def get_closed_trade_count(self, project_id: UUID) -> int:
        """Returns number of closed trades (WIN + LOSS + BREAK_EVEN) for the project."""
        from sqlalchemy import func

        from app.db.models.crypto_trading import TradeJournal

        result = await self.db.execute(
            select(func.count())
            .select_from(TradeJournal)
            .where(
                TradeJournal.project_id == project_id,
                TradeJournal.result.in_(["WIN", "LOSS", "BREAK_EVEN"]),
            )
        )
        count = result.scalar_one_or_none()
        return int(count or 0)

    async def has_open_position(self, project_id: UUID, symbol: str) -> bool:
        """Returns True if there is already an OPEN position for this project/symbol."""
        from app.db.models.crypto_trading import Position

        result = await self.db.execute(
            select(Position)
            .where(
                Position.project_id == project_id,
                Position.symbol == symbol.upper(),
                Position.status == "OPEN",
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
