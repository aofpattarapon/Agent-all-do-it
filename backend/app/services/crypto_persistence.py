"""Persistence helpers for crypto workflow outputs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.json_utils import extract_json_object
from app.db.models.crypto_trading import AgentVote, MarketSnapshot, NewsEvent, TradeProposal
from app.services.kill_switch import KillSwitch, KillSwitchConfig

logger = logging.getLogger(__name__)


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

        if agent_role == "news_monitor":
            await self.save_news_events(project_id=project_id, run_id=run_id, payload=payload)
            return
        if agent_role == "source_reliability":
            await self.update_news_reliability(project_id=project_id, run_id=run_id, payload=payload)
            return
        if agent_role == "market_regime":
            await self.save_market_snapshot(project_id=project_id, run_id=run_id, payload=payload)
            return
        if agent_role.startswith("hawk_") or agent_role == "sage":
            await self.save_agent_vote(project_id=project_id, run_id=run_id, agent_role=agent_role, payload=payload)
            return
        if agent_role == "trade_proposal":
            await self.save_trade_proposal(project_id=project_id, run_id=run_id, payload=payload)

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

            existing = await self._latest_news_event(project_id=project_id, run_id=run_id, news_id=news_id)
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
                        reliability_status=self._optional_str(item.get("reliability_status"), max_len=30),
                        used_for_trade=False,
                        **values,
                    )
                )
            else:
                for field, value in values.items():
                    setattr(existing, field, value)
                existing.reliability_score = self._as_int(item.get("reliability_score")) or existing.reliability_score
                existing.reliability_status = (
                    self._optional_str(item.get("reliability_status"), max_len=30) or existing.reliability_status
                )
                self.db.add(existing)
        await self.db.flush()

    async def update_news_reliability(self, *, project_id: UUID, run_id: UUID, payload: dict) -> None:
        items = payload.get("items")
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            news_id = str(item.get("news_id") or "").strip()
            if not news_id:
                continue
            existing = await self._latest_news_event(project_id=project_id, run_id=run_id, news_id=news_id)
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
            existing.reliability_status = self._optional_str(item.get("reliability_status"), max_len=30)
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
        existing = await self._latest_agent_vote(project_id=project_id, run_id=run_id, agent_role=agent_role)
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

    async def save_trade_proposal(self, *, project_id: UUID, run_id: UUID, payload: dict) -> TradeProposal | None:
        if payload.get("sage_approved") is not True:
            return None

        symbol = str(payload.get("symbol") or "").strip()
        direction = str(payload.get("direction") or "").strip().upper()
        entry_plan = payload.get("entry_plan")
        take_profit = payload.get("take_profit")
        stop_loss = self._as_float(payload.get("stop_loss"))
        if not symbol or direction not in {"LONG", "SHORT"} or not isinstance(entry_plan, dict):
            return None

        entry_price = self._entry_price(entry_plan)
        normalized_take_profit = self._normalize_take_profit_items(
            take_profit,
            entry_price=entry_price,
            stop_loss=stop_loss,
            direction=direction,
        )
        tp_levels = self._take_profit_levels(normalized_take_profit)
        if entry_price <= 0 or stop_loss is None:
            return None

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
        if not ks_result.passed:
            logger.info("Skipping trade proposal persistence; kill switch blocked proposal for %s", symbol)
            return None

        existing = await self._latest_trade_proposal(project_id=project_id, run_id=run_id)
        hawk_vote_count = await self._count_hawk_votes(project_id=project_id, run_id=run_id)
        expires_at = datetime.now(UTC) + timedelta(minutes=KillSwitchConfig().proposal_expiry_minutes)
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
            "kill_switch_passed": True,
            "kill_switch_details": {
                "warnings": ks_result.warnings,
                "checks_run": ks_result.checks_run,
                "adjusted_position_size_usdt": ks_result.adjusted_position_size_usdt,
                "proposal_normalized": True,
            },
            "agent_vote_summary": payload.get("agent_vote_summary") if isinstance(payload.get("agent_vote_summary"), dict) else {},
            "news_summary": self._optional_str(payload.get("news_summary")),
            "status": "PENDING_APPROVAL",
            "expires_at": expires_at,
            "full_proposal_md": self._optional_str(payload.get("full_proposal_md")),
        }
        if values["max_loss_usdt"] is None and values["position_size_usdt"] and stop_loss and entry_price > 0:
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

    async def _latest_news_event(self, *, project_id: UUID, run_id: UUID, news_id: str) -> NewsEvent | None:
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

    async def _latest_market_snapshot(self, *, project_id: UUID, run_id: UUID) -> MarketSnapshot | None:
        result = await self.db.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.project_id == project_id, MarketSnapshot.run_id == run_id)
            .order_by(MarketSnapshot.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_agent_vote(self, *, project_id: UUID, run_id: UUID, agent_role: str) -> AgentVote | None:
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

    async def _latest_trade_proposal(self, *, project_id: UUID, run_id: UUID) -> TradeProposal | None:
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
        risk_distance = abs(entry_price - stop_loss) if stop_loss is not None and entry_price > 0 else 0.0
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
    def _max_loss_usdt(*, entry_price: float, stop_loss: float | None, position_size_usdt: float) -> float | None:
        if stop_loss is None or entry_price <= 0 or position_size_usdt <= 0:
            return None
        sl_pct = abs(entry_price - stop_loss) / entry_price
        return round(position_size_usdt * sl_pct, 4)

    async def get_project_winrate(self, project_id: UUID) -> float:
        """Returns win rate as a percentage (0–100). Returns 0.0 if no closed trades."""
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
