"""Project repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project


async def get_by_id(db: AsyncSession, project_id: UUID) -> Project | None:
    return await db.get(Project, project_id)


async def get_by_user_and_id(db: AsyncSession, *, user_id: UUID, project_id: UUID) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_by_user(
    db: AsyncSession, *, user_id: UUID, skip: int = 0, limit: int = 50
) -> tuple[list[Project], int]:
    query = select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
    count_query = select(func.count()).select_from(Project).where(Project.user_id == user_id)
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create(
    db: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    description: str | None = None,
) -> Project:
    project = Project(user_id=user_id, name=name, description=description)
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


async def update(db: AsyncSession, *, db_project: Project, update_data: dict[str, Any]) -> Project:
    for field, value in update_data.items():
        setattr(db_project, field, value)
    db.add(db_project)
    await db.flush()
    await db.refresh(db_project)
    return db_project


async def delete(db: AsyncSession, project_id: UUID) -> Project | None:
    project = await get_by_id(db, project_id)
    if project:
        await db.delete(project)
        await db.flush()
    return project
