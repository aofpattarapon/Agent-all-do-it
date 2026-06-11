"""Agent template catalog API routes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSession
from app.schemas.agent_template import AgentTemplateFilter, AgentTemplateListItem, AgentTemplateRead
from app.services.agent_template import AgentTemplateService

router = APIRouter()


def _get_svc(db: DBSession) -> AgentTemplateService:
    return AgentTemplateService(db)


AgentTemplateSvc = Any  # type alias handled by Depends below


@router.get("/agent-templates", response_model=list[AgentTemplateListItem])
async def list_agent_templates(
    filters: AgentTemplateFilter = Depends(),
    db: DBSession = None,  # type: ignore[assignment]
) -> Any:
    """List agent templates with optional filtering and search."""
    svc = AgentTemplateService(db)
    templates, _total = await svc.list(filters)
    return templates


@router.get("/agent-templates/categories", response_model=list[str])
async def list_categories(
    db: DBSession = None,  # type: ignore[assignment]
) -> Any:
    """Get all distinct template categories."""
    svc = AgentTemplateService(db)
    return await svc.list_categories()


@router.get("/agent-templates/subcategories", response_model=list[str])
async def list_subcategories(
    category: str | None = None,
    db: DBSession = None,  # type: ignore[assignment]
) -> Any:
    """Get all distinct template subcategories, optionally filtered by category."""
    svc = AgentTemplateService(db)
    return await svc.list_subcategories(category=category)


@router.get("/agent-templates/{template_id}", response_model=AgentTemplateRead)
async def get_agent_template(
    template_id: UUID,
    db: DBSession = None,  # type: ignore[assignment]
) -> Any:
    """Get a single agent template by ID, including the full system_prompt."""
    svc = AgentTemplateService(db)
    return await svc.get(template_id)
