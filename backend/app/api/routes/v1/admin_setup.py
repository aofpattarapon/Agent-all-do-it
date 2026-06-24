"""Admin Setup API — seed data and configuration via HTTP instead of CLI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.deps import CurrentAdmin, DBSession
from app.core.exceptions import BadRequestError

NEXMIND_PROJECT_NAME = "NEXMIND Crypto Trading Pipeline"


class SeedCryptoBody(BaseModel):
    project_id: str | None = None
    clear_project: bool = False


router = APIRouter(prefix="/setup", tags=["admin-setup"])
logger = logging.getLogger(__name__)


@router.get("/status", response_model=None)
async def get_setup_status(db: DBSession, _: CurrentAdmin) -> Any:
    """Return counts of already-seeded data so the UI can show checkmarks."""
    from sqlalchemy import func, select

    from app.db.models.agent_template import AgentTemplate
    from app.db.models.project import AgentConfig
    from app.db.models.skill import Skill
    from app.db.models.workflow import Workflow

    agent_count = (await db.execute(select(func.count()).select_from(AgentConfig))).scalar_one()
    skill_count = (await db.execute(select(func.count()).select_from(Skill))).scalar_one()
    workflow_count = (await db.execute(select(func.count()).select_from(Workflow))).scalar_one()
    template_count = (
        await db.execute(select(func.count()).select_from(AgentTemplate))
    ).scalar_one()

    return {
        "agents": agent_count,
        "skills": skill_count,
        "workflows": workflow_count,
        "agent_templates": template_count,
        "crypto_seeded": agent_count >= 12,
        "skills_seeded": skill_count >= 30,
    }


@router.post("/seed-crypto", status_code=status.HTTP_200_OK, response_model=None)
async def seed_crypto_workflow(
    db: DBSession, admin: CurrentAdmin, body: SeedCryptoBody | None = None
) -> Any:
    """Seed the 12-agent NEXMIND crypto trading pipeline into a project."""
    try:
        from sqlalchemy import select

        from app.commands.seed_crypto_workflow import run_seed, seed_crypto_project
        from app.db.models.project import Project
        from app.repositories import project as project_repo

        body = body or SeedCryptoBody()

        # 1. Seed global agent templates
        await run_seed(db)

        # 2. Resolve or create the target project
        already_existed = True
        if body.project_id:
            project = await db.get(Project, body.project_id)  # type: ignore[arg-type]
            if project is None:
                raise BadRequestError(message=f"Project {body.project_id} not found", details={})
        else:
            result_row = await db.execute(
                select(Project).where(
                    Project.name == NEXMIND_PROJECT_NAME, Project.user_id == admin.id
                )
            )
            project = result_row.scalar_one_or_none()
            if project is None:
                project = await project_repo.create(
                    db,
                    user_id=admin.id,
                    name=NEXMIND_PROJECT_NAME,
                    description="Multi-pair crypto trading powered by NEXMIND AI",
                )
                already_existed = False

        # 3. Seed agents / workflows / schedules into the project
        detail = await seed_crypto_project(db, str(project.id), clear_project=body.clear_project)
        await db.commit()

        return {
            "ok": True,
            "project_id": str(project.id),
            "already_existed": already_existed,
            "detail": detail,
        }
    except BadRequestError:
        raise
    except Exception as exc:
        logger.exception("seed-crypto failed")
        raise BadRequestError(message=f"Seed failed: {exc}", details={}) from exc


@router.post("/seed-skills", status_code=status.HTTP_200_OK, response_model=None)
async def seed_skills(db: DBSession, _: CurrentAdmin) -> Any:
    """Seed the skills catalog (37 skills, 15 categories)."""
    try:
        from app.commands.seed_skills import run_seed as run_skills_seed

        result = await run_skills_seed(db)
        return {"ok": True, "message": "Skills seeded", "detail": result}
    except Exception as exc:
        logger.exception("seed-skills failed")
        raise BadRequestError(message=f"Seed failed: {exc}", details={}) from exc
