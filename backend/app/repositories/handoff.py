"""Handoff repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.handoff import Handoff


async def get_by_id(db: AsyncSession, handoff_id: UUID) -> Handoff | None:
    return await db.get(Handoff, handoff_id)


async def get_by_id_and_project(
    db: AsyncSession, *, handoff_id: UUID, project_id: UUID
) -> Handoff | None:
    result = await db.execute(
        select(Handoff).where(Handoff.id == handoff_id, Handoff.project_id == project_id)
    )
    return result.scalar_one_or_none()


async def list_by_project(
    db: AsyncSession,
    *,
    project_id: UUID,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Handoff], int]:
    query = select(Handoff).where(Handoff.project_id == project_id)
    count_query = select(func.count()).select_from(Handoff).where(Handoff.project_id == project_id)
    if status:
        query = query.where(Handoff.status == status)
        count_query = count_query.where(Handoff.status == status)
    query = query.order_by(Handoff.created_at.desc())
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def list_by_run(
    db: AsyncSession, *, run_id: UUID, skip: int = 0, limit: int = 50
) -> tuple[list[Handoff], int]:
    query = select(Handoff).where(Handoff.run_id == run_id).order_by(Handoff.created_at.desc())
    count_query = select(func.count()).select_from(Handoff).where(Handoff.run_id == run_id)
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def list_pending(
    db: AsyncSession, *, project_id: UUID | None = None, skip: int = 0, limit: int = 50
) -> tuple[list[Handoff], int]:
    query = select(Handoff).where(Handoff.status.in_(["draft", "ready", "sent"]))
    count_query = (
        select(func.count())
        .select_from(Handoff)
        .where(Handoff.status.in_(["draft", "ready", "sent"]))
    )
    if project_id:
        query = query.where(Handoff.project_id == project_id)
        count_query = count_query.where(Handoff.project_id == project_id)
    query = query.order_by(Handoff.created_at.desc())
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create(
    db: AsyncSession,
    *,
    project_id: UUID,
    run_id: UUID,
    from_step_id: UUID | None = None,
    to_step_id: UUID | None = None,
    from_agent_id: UUID | None = None,
    to_agent_id: UUID | None = None,
    summary: str = "",
    package_json: dict | None = None,
) -> Handoff:
    handoff = Handoff(
        project_id=project_id,
        run_id=run_id,
        from_step_id=from_step_id,
        to_step_id=to_step_id,
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        summary=summary,
        package_json=package_json or {},
    )
    db.add(handoff)
    await db.flush()
    await db.refresh(handoff)
    return handoff


async def update(db: AsyncSession, *, db_handoff: Handoff, update_data: dict[str, Any]) -> Handoff:
    for field, value in update_data.items():
        setattr(db_handoff, field, value)
    db.add(db_handoff)
    await db.flush()
    await db.refresh(db_handoff)
    return db_handoff


async def approve(
    db: AsyncSession,
    *,
    db_handoff: Handoff,
    approved_by: UUID,
) -> Handoff:
    from datetime import UTC, datetime

    db_handoff.status = "approved"
    db_handoff.approved_by = approved_by
    db_handoff.approved_at = datetime.now(UTC)
    db_handoff.rejected_reason = ""
    db.add(db_handoff)
    await db.flush()
    await db.refresh(db_handoff)
    return db_handoff


async def reject(
    db: AsyncSession,
    *,
    db_handoff: Handoff,
    reason: str,
) -> Handoff:
    db_handoff.status = "rejected"
    db_handoff.rejected_reason = reason
    db_handoff.approved_by = None
    db_handoff.approved_at = None
    db.add(db_handoff)
    await db.flush()
    await db.refresh(db_handoff)
    return db_handoff


async def request_revision(
    db: AsyncSession,
    *,
    db_handoff: Handoff,
    reason: str,
) -> Handoff:
    db_handoff.status = "draft"
    db_handoff.rejected_reason = reason
    db_handoff.approved_by = None
    db_handoff.approved_at = None
    db.add(db_handoff)
    await db.flush()
    await db.refresh(db_handoff)
    return db_handoff


async def delete(db: AsyncSession, handoff_id: UUID) -> Handoff | None:
    handoff = await get_by_id(db, handoff_id)
    if handoff:
        await db.delete(handoff)
        await db.flush()
    return handoff
