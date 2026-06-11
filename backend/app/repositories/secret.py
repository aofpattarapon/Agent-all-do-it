"""Secret repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.secret import Secret


async def get_by_id(db: AsyncSession, secret_id: UUID) -> Secret | None:
    return await db.get(Secret, secret_id)


async def get_by_id_and_project(
    db: AsyncSession, *, secret_id: UUID, project_id: UUID
) -> Secret | None:
    result = await db.execute(
        select(Secret).where(Secret.id == secret_id, Secret.project_id == project_id)
    )
    return result.scalar_one_or_none()


async def list_by_project(
    db: AsyncSession, *, project_id: UUID, skip: int = 0, limit: int = 50
) -> tuple[list[Secret], int]:
    query = (
        select(Secret)
        .where(Secret.project_id == project_id)
        .order_by(Secret.created_at.desc())
    )
    count_query = select(func.count()).select_from(Secret).where(
        Secret.project_id == project_id
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
    provider: str,
    environment: str,
    value_encrypted: str,
    value_masked: str,
) -> Secret:
    secret = Secret(
        project_id=project_id,
        user_id=user_id,
        name=name,
        provider=provider,
        environment=environment,
        value_encrypted=value_encrypted,
        value_masked=value_masked,
    )
    db.add(secret)
    await db.flush()
    await db.refresh(secret)
    return secret


async def update(
    db: AsyncSession, *, db_secret: Secret, update_data: dict[str, Any]
) -> Secret:
    for field, value in update_data.items():
        setattr(db_secret, field, value)
    db.add(db_secret)
    await db.flush()
    await db.refresh(db_secret)
    return db_secret


async def delete(db: AsyncSession, secret_id: UUID) -> Secret | None:
    secret = await get_by_id(db, secret_id)
    if secret:
        await db.delete(secret)
        await db.flush()
    return secret
