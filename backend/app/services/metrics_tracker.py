"""Per-run metrics tracking service (ported from SDLC MetricsTracker).

Writes to the ``run_metrics`` table. Uses ``flush()`` (never ``commit()``) —
the session auto-commits via ``get_db_session``.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import RunMetric


class MetricsTracker:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_for_run(self, run_id: UUID) -> RunMetric | None:
        result = await self.db.execute(select(RunMetric).where(RunMetric.run_id == run_id))
        return result.scalar_one_or_none()

    async def start_run(self, run_id: UUID, project_id: UUID) -> RunMetric:
        """Create the metric row for a run, or return the existing one (idempotent)."""
        existing = await self.get_for_run(run_id)
        if existing is not None:
            return existing
        metric = RunMetric(run_id=run_id, project_id=project_id)
        self.db.add(metric)
        await self.db.flush()
        await self.db.refresh(metric)
        return metric

    async def record_review_cycle(self, run_id: UUID) -> RunMetric | None:
        metric = await self.get_for_run(run_id)
        if metric is None:
            return None
        metric.review_cycles += 1
        await self.db.flush()
        return metric

    async def record_model_switch(self, run_id: UUID) -> RunMetric | None:
        metric = await self.get_for_run(run_id)
        if metric is None:
            return None
        metric.model_switches += 1
        await self.db.flush()
        return metric

    async def add_tokens(self, run_id: UUID, tokens: int) -> RunMetric | None:
        metric = await self.get_for_run(run_id)
        if metric is None:
            return None
        metric.total_tokens += tokens
        await self.db.flush()
        return metric

    async def complete_run(
        self,
        run_id: UUID,
        *,
        step_count: int,
        duration_ms: int,
        passed_first_review: bool | None = None,
    ) -> RunMetric | None:
        metric = await self.get_for_run(run_id)
        if metric is None:
            return None
        metric.step_count = step_count
        metric.duration_ms = duration_ms
        if passed_first_review is not None:
            metric.passed_first_review = passed_first_review
        await self.db.flush()
        return metric

    async def list_for_project(self, project_id: UUID) -> list[RunMetric]:
        result = await self.db.execute(
            select(RunMetric)
            .where(RunMetric.project_id == project_id)
            .order_by(RunMetric.created_at.desc())
        )
        return list(result.scalars().all())
