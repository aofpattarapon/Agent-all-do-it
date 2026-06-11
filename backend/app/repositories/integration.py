"""Integration repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.integration import Integration


async def get_by_id(db: AsyncSession, integration_id: UUID) -> Integration | None:
    return await db.get(Integration, integration_id)


async def get_by_id_and_project(
    db: AsyncSession, *, integration_id: UUID, project_id: UUID
) -> Integration | None:
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.project_id == project_id
        )
    )
    return result.scalar_one_or_none()


async def list_by_project(
    db: AsyncSession, *, project_id: UUID, skip: int = 0, limit: int = 50
) -> tuple[list[Integration], int]:
    query = (
        select(Integration)
        .where(Integration.project_id == project_id)
        .order_by(Integration.created_at.desc())
    )
    count_query = select(func.count()).select_from(Integration).where(
        Integration.project_id == project_id
    )
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    name: str,
    kind: str,
    config_json: dict | None = None,
) -> Integration:
    integration = Integration(
        project_id=project_id,
        user_id=user_id,
        name=name,
        kind=kind,
        config_json=config_json or {},
    )
    db.add(integration)
    await db.flush()
    await db.refresh(integration)
    return integration


async def update(
    db: AsyncSession, *, db_integration: Integration, update_data: dict[str, Any]
) -> Integration:
    for field, value in update_data.items():
        setattr(db_integration, field, value)
    db.add(db_integration)
    await db.flush()
    await db.refresh(db_integration)
    return db_integration


async def delete(db: AsyncSession, integration_id: UUID) -> Integration | None:
    integration = await get_by_id(db, integration_id)
    if integration:
        await db.delete(integration)
        await db.flush()
    return integration
