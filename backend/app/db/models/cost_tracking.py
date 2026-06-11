"""Cost tracking models — per-run-step token cost events and per-project daily budgets."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Approximate cost per 1M tokens (input + output blended) in USD.
# Update these when providers change pricing.
MODEL_COST_PER_1M: dict[str, float] = {
    "claude-haiku-4-5-20251001": 0.80,
    "claude-sonnet-4-6": 3.00,
    "claude-opus-4-8": 15.00,
    "claude-fable-5": 8.00,
    "gpt-4o": 5.00,
    "gpt-4o-mini": 0.15,
    "moonshot-v1-8k": 1.00,
    "moonshot-v1-32k": 2.00,
    "moonshot-v1-128k": 8.00,
    "kimi-k2-0711-preview": 0.60,
    # OpenRouter free / stealth tiers — no token charge
    "openai/gpt-oss-120b:free": 0.00,
    "nvidia/nemotron-3-ultra-550b-a55b:free": 0.00,
    "openrouter/owl-alpha": 0.00,
    # default fallback
    "_default": 2.00,
}


def estimate_cost_usd(model: str, tokens: int) -> float:
    rate = MODEL_COST_PER_1M.get(model) or MODEL_COST_PER_1M["_default"]
    return round((tokens / 1_000_000) * rate, 6)


class CostEvent(Base, TimestampMixin):
    """One token-cost record per agent run step."""

    __tablename__ = "cost_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    agent_config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    def __repr__(self) -> str:
        return f"<CostEvent(project={self.project_id}, model={self.model}, tokens={self.tokens_used}, usd={self.cost_usd})>"


class CostBudget(Base, TimestampMixin):
    """Daily budget limit per project."""

    __tablename__ = "cost_budgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    daily_budget_usd: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    alert_at_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)  # 0-100
    hard_stop_at_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_reset_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<CostBudget(project={self.project_id}, daily_usd={self.daily_budget_usd})>"
