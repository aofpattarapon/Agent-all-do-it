"""ProjectMember repository — per-project role lookups for RBAC."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project_member import ProjectMember


async def get(
    db: AsyncSession, *, project_id: UUID, user_id: UUID
) -> ProjectMember | None:
    """Return the membership row for ``(project_id, user_id)`` or ``None``."""
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_for_project(
    db: AsyncSession, *, project_id: UUID
) -> list[ProjectMember]:
    """Return all membership rows for a project."""
    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at.asc())
    )
    return list(result.scalars().all())


async def upsert(
    db: AsyncSession, *, project_id: UUID, user_id: UUID, project_role: str
) -> ProjectMember:
    """Create or update a member's role within a project."""
    existing = await get(db, project_id=project_id, user_id=user_id)
    if existing is not None:
        existing.project_role = project_role
        db.add(existing)
        await db.flush()
        await db.refresh(existing)
        return existing
    member = ProjectMember(
        project_id=project_id, user_id=user_id, project_role=project_role
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


async def remove(db: AsyncSession, *, project_id: UUID, user_id: UUID) -> None:
    """Delete a membership row if it exists."""
    member = await get(db, project_id=project_id, user_id=user_id)
    if member is not None:
        await db.delete(member)
        await db.flush()
