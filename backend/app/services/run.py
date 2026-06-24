"""Run service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.workflow import Run
from app.repositories import run_repo
from app.schemas.run import RunCreate, RunUpdate


class RunService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, run_id: UUID, project_id: UUID) -> Run:
        run = await run_repo.get_run_by_id(self.db, run_id)
        if not run or run.project_id != project_id:
            raise NotFoundError(message="Run not found", details={"run_id": str(run_id)})
        return run

    async def list(self, project_id: UUID, skip: int = 0, limit: int = 50) -> tuple[list[Run], int]:
        return await run_repo.list_runs_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, data: RunCreate) -> Run:
        return await run_repo.create_run(
            self.db,
            project_id=project_id,
            workflow_id=data.workflow_id,
            trigger=data.trigger,
            input_payload_json=data.input_payload_json,
        )

    async def update(self, run_id: UUID, project_id: UUID, data: RunUpdate) -> Run:
        run = await self.get(run_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        return await run_repo.update_run(self.db, db_run=run, update_data=update_data)

    async def delete(self, run_id: UUID, project_id: UUID) -> None:
        run = await self.get(run_id, project_id)
        await run_repo.delete_run(self.db, run.id)

    async def reset_for_retry(self, run_id: UUID, project_id: UUID) -> Run:
        run = await self.get(run_id, project_id)
        return await run_repo.reset_run_for_retry(self.db, db_run=run)
