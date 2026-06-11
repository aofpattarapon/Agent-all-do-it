"""Cost guard — records token usage and enforces per-project daily budgets.

Usage in RunExecutor after each LLM call:
    guard = CostGuard(db)
    status = await guard.record(
        project_id=project_id,
        run_id=run_id,
        provider=meta["runtime"],
        model=meta.get("model", ""),
        tokens=meta.get("tokens_used") or 0,
    )
    if status == "hard_stop":
        raise RuntimeError("Daily budget exceeded — run aborted")
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cost_tracking import CostBudget, CostEvent, estimate_cost_usd

logger = logging.getLogger(__name__)

BudgetStatus = str  # "ok" | "alert" | "hard_stop"


class CostGuard:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        *,
        project_id: UUID,
        run_id: UUID | None,
        provider: str,
        model: str,
        tokens: int,
        agent_config_id: UUID | None = None,
    ) -> BudgetStatus:
        """Persist a CostEvent and check budget thresholds.

        Returns "ok", "alert" (>= alert_at_pct), or "hard_stop" (>= hard_stop_at_pct).
        Never raises — budget failures are surfaced as return values so the caller
        decides whether to abort.
        """
        if tokens <= 0:
            return "ok"

        cost = estimate_cost_usd(model, tokens)
        event = CostEvent(
            project_id=project_id,
            run_id=run_id,
            agent_config_id=agent_config_id,
            provider=provider,
            model=model,
            tokens_used=tokens,
            cost_usd=cost,
        )
        self.db.add(event)
        await self.db.flush()

        try:
            return await self._check_budget(project_id)
        except Exception as exc:
            logger.warning("CostGuard._check_budget failed: %s", exc)
            return "ok"

    async def _check_budget(self, project_id: UUID) -> BudgetStatus:
        budget = await self._get_or_create_budget(project_id)

        since = datetime.now(UTC) - timedelta(hours=24)
        result = await self.db.execute(
            select(func.sum(CostEvent.cost_usd)).where(
                CostEvent.project_id == project_id,
                CostEvent.created_at >= since,
            )
        )
        daily_spent: float = result.scalar_one() or 0.0

        pct = (daily_spent / budget.daily_budget_usd * 100) if budget.daily_budget_usd > 0 else 0

        if pct >= budget.hard_stop_at_pct:
            logger.warning(
                "Project %s HARD STOP: daily budget $%.4f exceeded (spent $%.4f)",
                project_id, budget.daily_budget_usd, daily_spent,
            )
            return "hard_stop"
        if pct >= budget.alert_at_pct:
            logger.warning(
                "Project %s budget alert: %.1f%% used ($%.4f / $%.2f)",
                project_id, pct, daily_spent, budget.daily_budget_usd,
            )
            return "alert"
        return "ok"

    async def _get_or_create_budget(self, project_id: UUID) -> CostBudget:
        result = await self.db.execute(
            select(CostBudget).where(CostBudget.project_id == project_id)
        )
        budget = result.scalar_one_or_none()
        if budget is None:
            budget = CostBudget(project_id=project_id)
            self.db.add(budget)
            await self.db.flush()
            await self.db.refresh(budget)
        return budget

    async def get_summary(self, project_id: UUID) -> dict:
        """Return a cost summary for the last 24 hours."""
        since = datetime.now(UTC) - timedelta(hours=24)
        result = await self.db.execute(
            select(func.sum(CostEvent.cost_usd), func.sum(CostEvent.tokens_used)).where(
                CostEvent.project_id == project_id,
                CostEvent.created_at >= since,
            )
        )
        row = result.one()
        spent = float(row[0] or 0)
        tokens = int(row[1] or 0)
        budget = await self._get_or_create_budget(project_id)
        pct = round(spent / budget.daily_budget_usd * 100, 1) if budget.daily_budget_usd > 0 else 0
        return {
            "project_id": str(project_id),
            "daily_budget_usd": budget.daily_budget_usd,
            "daily_spent_usd": round(spent, 4),
            "daily_tokens": tokens,
            "budget_used_pct": pct,
            "alert_at_pct": budget.alert_at_pct,
            "hard_stop_at_pct": budget.hard_stop_at_pct,
        }
