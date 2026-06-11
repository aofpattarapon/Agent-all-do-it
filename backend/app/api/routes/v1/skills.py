"""Skill catalog API routes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSession
from app.schemas.skill import SkillFilter, SkillListItem, SkillRead
from app.services.skill import SkillService

router = APIRouter()


def _get_svc(db: DBSession) -> SkillService:
    return SkillService(db)


@router.get("/skills", response_model=list[SkillListItem])
async def list_skills(
    filters: SkillFilter = Depends(),
    db: DBSession = None,  # type: ignore[assignment]
) -> Any:
    """List skills with optional filtering and search."""
    svc = SkillService(db)
    skills, _total = await svc.list(filters)
    return skills


@router.get("/skills/categories", response_model=list[str])
async def list_categories(
    db: DBSession = None,  # type: ignore[assignment]
) -> Any:
    """Get all distinct skill categories."""
    svc = SkillService(db)
    return await svc.list_categories()


@router.get("/skills/{skill_id}", response_model=SkillRead)
async def get_skill(
    skill_id: UUID,
    db: DBSession = None,  # type: ignore[assignment]
) -> Any:
    """Get a single skill by ID, including the full system_prompt_fragment."""
    svc = SkillService(db)
    return await svc.get(skill_id)
