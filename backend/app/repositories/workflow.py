"""Workflow and Schedule repositories."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import Schedule, Workflow

# ── Workflow ──────────────────────────────────────────────────────────────────


async def get_workflow_by_id(db: AsyncSession, workflow_id: UUID) -> Workflow | None:
    return await db.get(Workflow, workflow_id)


async def list_workflows_by_project(
    db: AsyncSession, *, project_id: UUID, skip: int = 0, limit: int = 100
) -> tuple[list[Workflow], int]:
    query = (
        select(Workflow)
        .where(Workflow.project_id == project_id)
        .order_by(Workflow.created_at.asc())
    )
    count_query = (
        select(func.count()).select_from(Workflow).where(Workflow.project_id == project_id)
    )
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create_workflow(
    db: AsyncSession,
    *,
    project_id: UUID,
    name: str,
    description: str | None = None,
    trigger_kind: str = "manual",
    definition_json: dict | None = None,
    is_enabled: bool = True,
) -> Workflow:
    workflow = Workflow(
        project_id=project_id,
        name=name,
        description=description,
        trigger_kind=trigger_kind,
        definition_json=definition_json or {},
        is_enabled=is_enabled,
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)
    return workflow


async def update_workflow(
    db: AsyncSession, *, db_workflow: Workflow, update_data: dict[str, Any]
) -> Workflow:
    for field, value in update_data.items():
        setattr(db_workflow, field, value)
    db.add(db_workflow)
    await db.flush()
    await db.refresh(db_workflow)
    return db_workflow


async def delete_workflow(db: AsyncSession, workflow_id: UUID) -> Workflow | None:
    workflow = await get_workflow_by_id(db, workflow_id)
    if workflow:
        await db.delete(workflow)
        await db.flush()
    return workflow


# ── Schedule ──────────────────────────────────────────────────────────────────


async def get_schedule_by_id(db: AsyncSession, schedule_id: UUID) -> Schedule | None:
    return await db.get(Schedule, schedule_id)


async def list_schedules_by_workflow(
    db: AsyncSession, *, workflow_id: UUID, skip: int = 0, limit: int = 100
) -> tuple[list[Schedule], int]:
    query = (
        select(Schedule)
        .where(Schedule.workflow_id == workflow_id)
        .order_by(Schedule.created_at.asc())
    )
    count_query = (
        select(func.count()).select_from(Schedule).where(Schedule.workflow_id == workflow_id)
    )
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def list_schedules_by_project(
    db: AsyncSession, *, project_id: UUID, skip: int = 0, limit: int = 100
) -> tuple[list[Schedule], int]:
    query = (
        select(Schedule)
        .where(Schedule.project_id == project_id)
        .order_by(Schedule.created_at.asc())
    )
    count_query = (
        select(func.count()).select_from(Schedule).where(Schedule.project_id == project_id)
    )
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create_schedule(
    db: AsyncSession,
    *,
    project_id: UUID,
    workflow_id: UUID,
    cron_expr: str,
    timezone: str = "UTC",
    input_payload_json: dict | None = None,
    enabled: bool = True,
) -> Schedule:
    schedule = Schedule(
        project_id=project_id,
        workflow_id=workflow_id,
        cron_expr=cron_expr,
        timezone=timezone,
        input_payload_json=input_payload_json or {},
        enabled=enabled,
    )
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    return schedule


async def update_schedule(
    db: AsyncSession, *, db_schedule: Schedule, update_data: dict[str, Any]
) -> Schedule:
    for field, value in update_data.items():
        setattr(db_schedule, field, value)
    db.add(db_schedule)
    await db.flush()
    await db.refresh(db_schedule)
    return db_schedule


async def delete_schedule(db: AsyncSession, schedule_id: UUID) -> Schedule | None:
    schedule = await get_schedule_by_id(db, schedule_id)
    if schedule:
        await db.delete(schedule)
        await db.flush()
    return schedule
