"""Skill version CRUD and human approval gate."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentAdmin, CurrentUser, DBSession
from app.core.exceptions import NotFoundError
from app.repositories import skill_version as skill_version_repo
from app.schemas.skill_version import SkillVersionCreate, SkillVersionList, SkillVersionRead
from app.services.skill_version import SkillVersionService

router = APIRouter()


def _get_svc(db: AsyncSession) -> SkillVersionService:
    return SkillVersionService(db)


@router.get("/skills/{skill_id}/versions", response_model=SkillVersionList)
async def list_skill_versions(
    skill_id: UUID,
    db: DBSession,
    _user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    items, total = await skill_version_repo.list_by_skill(db, skill_id, skip=skip, limit=limit)
    return SkillVersionList(items=items, total=total)


@router.get("/skills/{skill_id}/versions/{version_id}", response_model=SkillVersionRead)
async def get_skill_version(
    skill_id: UUID,
    version_id: UUID,
    db: DBSession,
    _user: CurrentUser,
) -> Any:
    version = await skill_version_repo.get_by_id(db, version_id)
    if version is None or version.skill_id != skill_id:
        raise NotFoundError(message="Skill version not found", details={"version_id": str(version_id)})
    return version


@router.post(
    "/skills/{skill_id}/versions",
    response_model=SkillVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_skill_version(
    skill_id: UUID,
    data: SkillVersionCreate,
    db: DBSession,
    _admin: CurrentAdmin,
) -> Any:
    return await _get_svc(db).create_version(
        skill_id=skill_id,
        prompt_fragment=data.prompt_fragment,
        notes=data.notes or "",
    )


@router.post("/skills/{skill_id}/versions/{version_id}/approve", response_model=SkillVersionRead)
async def approve_skill_version(
    skill_id: UUID,
    version_id: UUID,
    db: DBSession,
    admin: CurrentAdmin,
) -> Any:
    """Promote a canary version to active. Admin approval required."""
    version = await skill_version_repo.get_by_id(db, version_id)
    if version is None or version.skill_id != skill_id:
        raise NotFoundError(message="Skill version not found", details={"version_id": str(version_id)})
    return await _get_svc(db).approve(version_id=version_id, approver_id=admin.id)


@router.post("/skills/{skill_id}/versions/{version_id}/rollback", response_model=SkillVersionRead)
async def rollback_skill_version(
    skill_id: UUID,
    version_id: UUID,
    db: DBSession,
    _admin: CurrentAdmin,
) -> Any:
    """Revert skill to a specific rollback-ready version. Admin only."""
    version = await skill_version_repo.get_by_id(db, version_id)
    if version is None or version.skill_id != skill_id:
        raise NotFoundError(message="Skill version not found", details={"version_id": str(version_id)})
    return await _get_svc(db).rollback(skill_id=skill_id)


@router.post("/skills/{skill_id}/versions/rollback", response_model=SkillVersionRead)
async def rollback_skill(
    skill_id: UUID,
    db: DBSession,
    _admin: CurrentAdmin,
) -> Any:
    """Revert skill to the previous rollback-ready version. Admin only."""
    return await _get_svc(db).rollback(skill_id=skill_id)


@router.delete(
    "/skills/{skill_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def archive_skill_version(
    skill_id: UUID,
    version_id: UUID,
    db: DBSession,
    _admin: CurrentAdmin,
) -> None:
    """Archive a skill version (soft delete). Admin only."""
    version = await skill_version_repo.get_by_id(db, version_id)
    if version is None or version.skill_id != skill_id:
        raise NotFoundError(message="Skill version not found", details={"version_id": str(version_id)})
    await skill_version_repo.update(db, db_version=version, update_data={"status": "archived"})
