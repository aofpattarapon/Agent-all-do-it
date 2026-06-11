"""Admin-only endpoints for workspace bootstrapping."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentAdmin, DBSession
from app.core.exceptions import BadRequestError
from app.db.models.project import Project
from app.repositories import project as project_repo

router = APIRouter()

logger = logging.getLogger(__name__)

PIPELINE_PROJECT_NAME = "Binance Testnet — BTCUSDT Pipeline"


@router.post("/seed/crypto", status_code=status.HTTP_200_OK, response_model=None)
async def seed_crypto(
    db: DBSession,
    user: CurrentAdmin,
) -> Any:
    """Seed the NEXMIND crypto pipeline.

    1. Checks if a project named *Binance Testnet — BTCUSDT Pipeline* already exists.
    2. If not, creates the project and instantiates the full 12-agent pipeline.
    3. Returns the project_id so the frontend wizard can proceed to budget/API-key steps.
    """
    result = await db.execute(
        select(Project).where(Project.name == PIPELINE_PROJECT_NAME)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {
            "ok": True,
            "project_id": str(existing.id),
            "already_existed": True,
        }

    # Create the project under the admin user
    project = await project_repo.create(
        db,
        user_id=user.id,
        name=PIPELINE_PROJECT_NAME,
        description="Automated crypto trading pipeline with 12 NEXMIND agents",
    )
    await db.commit()

    # Instantiate agents + workflows into the project
    try:
        from app.commands.seed_crypto_workflow import _seed

        await _seed(clear=False, project_id=str(project.id), clear_project=False)
    except Exception as exc:
        logger.exception("seed-crypto project instantiation failed")
        raise BadRequestError(
            message=f"Pipeline instantiation failed: {exc}", details={}
        ) from exc

    return {
        "ok": True,
        "project_id": str(project.id),
        "already_existed": False,
    }
