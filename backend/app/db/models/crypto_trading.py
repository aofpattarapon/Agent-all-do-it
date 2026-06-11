"""Crypto trading domain models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NewsEvent(Base, TimestampMixin):
    __tablename__ = "news_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    news_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    related_assets: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    reliability_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reliability_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    risk_flags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_for_trade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MarketSnapshot(Base, TimestampMixin):
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_regime: Mapped[str] = mapped_column(String(30), nullable=False)
    altcoin_condition: Mapped[str | None] = mapped_column(String(30), nullable=True)
    btc_condition: Mapped[str | None] = mapped_column(String(30), nullable=True)
    volatility_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fear_greed_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    btc_dominance: Mapped[float | None] = mapped_column(Float, nullable=True)
    funding_rate_btc: Mapped[float | None] = mapped_column(Float, nullable=True)
    long_short_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_permission: Mapped[str] = mapped_column(String(30), default="ALLOW", nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class TokenCandidate(Base, TimestampMixin):
    __tablename__ = "token_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    trend: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trend_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    liquidity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    momentum_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technical_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onchain_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentiment_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_status: Mapped[str] = mapped_column(String(30), default="WATCHLIST", nullable=False, index=True)
    signals: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AgentVote(Base, TimestampMixin):
    __tablename__ = "agent_votes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    token_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("token_candidates.id", ondelete="SET NULL"), nullable=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(50), nullable=False)
    vote: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    veto_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TradeProposal(Base, TimestampMixin):
    __tablename__ = "trade_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    strategy_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    time_horizon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entry_plan: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    take_profit: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_size_usdt: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_loss_usdt: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hawk_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sage_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kill_switch_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kill_switch_details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    agent_vote_summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    news_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_proposal_md: Mapped[str | None] = mapped_column(Text, nullable=True)


class TradeExecution(Base, TimestampMixin):
    __tablename__ = "trade_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade_proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    executed_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size: Mapped[float | None] = mapped_column(Float, nullable=True)
    sl_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tp_order_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    execution_status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade_executions.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profits: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)


class TradeJournal(Base, TimestampMixin):
    __tablename__ = "trade_journal"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positions.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    holding_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    original_thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_happened: Mapped[str | None] = mapped_column(Text, nullable=True)
    mistakes: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_worked: Mapped[str | None] = mapped_column(Text, nullable=True)
    improvement: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_review_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_log: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    news_used: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    agent_votes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
