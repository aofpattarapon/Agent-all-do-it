"""Handoff service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models.handoff import Handoff
from app.repositories import handoff_repo
from app.schemas.handoff import (
    HandoffApproveRequest,
    HandoffCreate,
    HandoffRejectRequest,
    HandoffUpdate,
)


class HandoffService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, handoff_id: UUID, project_id: UUID) -> Handoff:
        handoff = await handoff_repo.get_by_id_and_project(
            self.db, handoff_id=handoff_id, project_id=project_id
        )
        if not handoff:
            raise NotFoundError(
                message="Handoff not found",
                details={"handoff_id": str(handoff_id)},
            )
        return handoff

    async def list(
        self,
        project_id: UUID,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Handoff], int]:
        return await handoff_repo.list_by_project(
            self.db, project_id=project_id, status=status, skip=skip, limit=limit
        )

    async def list_by_run(
        self, run_id: UUID, skip: int = 0, limit: int = 50
    ) -> tuple[list[Handoff], int]:
        return await handoff_repo.list_by_run(self.db, run_id=run_id, skip=skip, limit=limit)

    async def list_pending(
        self, project_id: UUID | None = None, skip: int = 0, limit: int = 50
    ) -> tuple[list[Handoff], int]:
        return await handoff_repo.list_pending(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, data: HandoffCreate) -> Handoff:
        return await handoff_repo.create(
            self.db,
            project_id=project_id,
            run_id=data.run_id,
            from_step_id=data.from_step_id,
            to_step_id=data.to_step_id,
            from_agent_id=data.from_agent_id,
            to_agent_id=data.to_agent_id,
            summary=data.summary,
            package_json=data.package_json,
        )

    async def update(self, handoff_id: UUID, project_id: UUID, data: HandoffUpdate) -> Handoff:
        handoff = await self.get(handoff_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        return await handoff_repo.update(self.db, db_handoff=handoff, update_data=update_data)

    async def approve(
        self, handoff_id: UUID, project_id: UUID, user_id: UUID, data: HandoffApproveRequest
    ) -> Handoff:
        handoff = await self.get(handoff_id, project_id)
        if handoff.status in ("approved", "completed"):
            raise BadRequestError(
                message="Handoff already approved",
                details={"handoff_id": str(handoff_id), "status": handoff.status},
            )
        # Record any comment in the package
        if data.comment:
            handoff.package_json = {
                **handoff.package_json,
                "approval_comment": data.comment,
            }
        return await handoff_repo.approve(self.db, db_handoff=handoff, approved_by=user_id)

    async def reject(
        self, handoff_id: UUID, project_id: UUID, data: HandoffRejectRequest
    ) -> Handoff:
        handoff = await self.get(handoff_id, project_id)
        if handoff.status == "rejected":
            raise BadRequestError(
                message="Handoff already rejected",
                details={"handoff_id": str(handoff_id)},
            )
        return await handoff_repo.reject(self.db, db_handoff=handoff, reason=data.reason)

    async def request_revision(self, handoff_id: UUID, project_id: UUID, reason: str) -> Handoff:
        handoff = await self.get(handoff_id, project_id)
        return await handoff_repo.request_revision(self.db, db_handoff=handoff, reason=reason)

    async def delete(self, handoff_id: UUID, project_id: UUID) -> None:
        handoff = await self.get(handoff_id, project_id)
        await handoff_repo.delete(self.db, handoff.id)
