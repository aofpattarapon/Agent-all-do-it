"""Knowledge template catalog routes (public, no auth required)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DBSession
from app.schemas.knowledge_template import (
    KnowledgeTemplateFilter,
    KnowledgeTemplateListItem,
    KnowledgeTemplateRead,
)
from app.services.knowledge_template import KnowledgeTemplateService

router = APIRouter()


@router.get("/knowledge-templates", response_model=list[KnowledgeTemplateListItem])
async def list_knowledge_templates(filters: KnowledgeTemplateFilter = Depends(), db: DBSession = None) -> Any:
    svc = KnowledgeTemplateService(db)
    templates, _total = await svc.list_templates(filters)
    return templates


@router.get("/knowledge-templates/categories", response_model=list[str])
async def list_categories(db: DBSession = None) -> Any:
    svc = KnowledgeTemplateService(db)
    return await svc.list_categories()


@router.get("/knowledge-templates/subcategories", response_model=list[str])
async def list_subcategories(category: str | None = None, db: DBSession = None) -> Any:
    svc = KnowledgeTemplateService(db)
    return await svc.list_subcategories(category=category)


@router.get("/knowledge-templates/{template_id}", response_model=KnowledgeTemplateRead)
async def get_knowledge_template(template_id: UUID, db: DBSession = None) -> Any:
    svc = KnowledgeTemplateService(db)
    tmpl = await svc.get(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Knowledge template not found")
    return tmpl
