"""Run and RunStep repositories."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import Run, RunMetric, RunStep

# ── Run ───────────────────────────────────────────────────────────────────────


async def get_run_by_id(db: AsyncSession, run_id: UUID) -> Run | None:
    return await db.get(Run, run_id)


async def list_runs_by_project(
    db: AsyncSession, *, project_id: UUID, skip: int = 0, limit: int = 50
) -> tuple[list[Run], int]:
    query = select(Run).where(Run.project_id == project_id).order_by(Run.created_at.desc())
    count_query = select(func.count()).select_from(Run).where(Run.project_id == project_id)
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create_run(
    db: AsyncSession,
    *,
    project_id: UUID,
    workflow_id: UUID | None = None,
    trigger: str = "manual",
    input_payload_json: dict | None = None,
) -> Run:
    run = Run(
        project_id=project_id,
        workflow_id=workflow_id,
        trigger=trigger,
        input_payload_json=input_payload_json or {},
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def update_run(db: AsyncSession, *, db_run: Run, update_data: dict[str, Any]) -> Run:
    for field, value in update_data.items():
        setattr(db_run, field, value)
    db.add(db_run)
    await db.flush()
    await db.refresh(db_run)
    return db_run


async def reset_run_for_retry(db: AsyncSession, *, db_run: Run) -> Run:
    """Reset a run's execution state so it can be re-executed from the start."""
    db_run.status = "queued"
    db_run.error_text = ""
    db_run.output_text = ""
    db_run.started_at = None
    db_run.finished_at = None
    db_run.current_step_index = 0
    db_run.paused_at = None
    db_run.retry_after_at = None
    db_run.pause_reason = ""
    db.add(db_run)
    await db.flush()
    await db.refresh(db_run)
    return db_run


async def delete_run(db: AsyncSession, run_id: UUID) -> Run | None:
    run = await get_run_by_id(db, run_id)
    if run:
        await db.delete(run)
        await db.flush()
    return run


# ── RunStep ───────────────────────────────────────────────────────────────────


async def get_run_step_by_id(db: AsyncSession, step_id: UUID) -> RunStep | None:
    return await db.get(RunStep, step_id)


async def list_steps_by_run(
    db: AsyncSession, *, run_id: UUID, skip: int = 0, limit: int = 100
) -> tuple[list[RunStep], int]:
    query = select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.created_at.asc())
    count_query = select(func.count()).select_from(RunStep).where(RunStep.run_id == run_id)
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create_run_step(
    db: AsyncSession,
    *,
    run_id: UUID,
    step_key: str,
    step_kind: str,
    agent_config_id: UUID | None = None,
    input_json: dict | None = None,
) -> RunStep:
    step = RunStep(
        run_id=run_id,
        step_key=step_key,
        step_kind=step_kind,
        agent_config_id=agent_config_id,
        input_json=input_json or {},
    )
    db.add(step)
    await db.flush()
    await db.refresh(step)
    return step


async def update_run_step(
    db: AsyncSession, *, db_step: RunStep, update_data: dict[str, Any]
) -> RunStep:
    for field, value in update_data.items():
        setattr(db_step, field, value)
    db.add(db_step)
    await db.flush()
    await db.refresh(db_step)
    return db_step


# ── RunMetric ─────────────────────────────────────────────────────────────────


async def get_run_metric_by_run(db: AsyncSession, run_id: UUID) -> RunMetric | None:
    result = await db.execute(select(RunMetric).where(RunMetric.run_id == run_id))
    return result.scalar_one_or_none()


async def upsert_run_metric(
    db: AsyncSession,
    *,
    run_id: UUID,
    project_id: UUID,
    step_count: int = 0,
    duration_ms: int = 0,
    total_tokens: int = 0,
    review_cycles: int = 0,
    model_switches: int = 0,
    passed_first_review: bool | None = None,
) -> RunMetric:
    """Insert a RunMetric row, or update the existing one for this run."""
    metric = await get_run_metric_by_run(db, run_id)
    if metric is None:
        metric = RunMetric(run_id=run_id, project_id=project_id)
        db.add(metric)
    metric.step_count = step_count
    metric.duration_ms = duration_ms
    metric.total_tokens = total_tokens
    metric.review_cycles = review_cycles
    metric.model_switches = model_switches
    if passed_first_review is not None:
        metric.passed_first_review = passed_first_review
    await db.flush()
    await db.refresh(metric)
    return metric
