"""Workflow and Schedule services."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.workflow import Schedule, Workflow
from app.repositories import workflow_repo
from app.schemas.workflow import ScheduleCreate, ScheduleUpdate, WorkflowCreate, WorkflowUpdate


class WorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, workflow_id: UUID, project_id: UUID) -> Workflow:
        workflow = await workflow_repo.get_workflow_by_id(self.db, workflow_id)
        if not workflow or workflow.project_id != project_id:
            raise NotFoundError(
                message="Workflow not found", details={"workflow_id": str(workflow_id)}
            )
        return workflow

    async def list(
        self, project_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[Workflow], int]:
        return await workflow_repo.list_workflows_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, data: WorkflowCreate) -> Workflow:
        return await workflow_repo.create_workflow(
            self.db,
            project_id=project_id,
            name=data.name,
            description=data.description,
            trigger_kind=data.trigger_kind,
            definition_json=data.definition_json,
            is_enabled=data.is_enabled,
        )

    async def update(self, workflow_id: UUID, project_id: UUID, data: WorkflowUpdate) -> Workflow:
        workflow = await self.get(workflow_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        return await workflow_repo.update_workflow(
            self.db, db_workflow=workflow, update_data=update_data
        )

    async def delete(self, workflow_id: UUID, project_id: UUID) -> None:
        workflow = await self.get(workflow_id, project_id)
        await workflow_repo.delete_workflow(self.db, workflow.id)


class ScheduleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, schedule_id: UUID, workflow_id: UUID) -> Schedule:
        schedule = await workflow_repo.get_schedule_by_id(self.db, schedule_id)
        if not schedule or schedule.workflow_id != workflow_id:
            raise NotFoundError(
                message="Schedule not found", details={"schedule_id": str(schedule_id)}
            )
        return schedule

    async def list(
        self, workflow_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[Schedule], int]:
        return await workflow_repo.list_schedules_by_workflow(
            self.db, workflow_id=workflow_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, workflow_id: UUID, data: ScheduleCreate) -> Schedule:
        return await workflow_repo.create_schedule(
            self.db,
            project_id=project_id,
            workflow_id=workflow_id,
            cron_expr=data.cron_expr,
            timezone=data.timezone,
            input_payload_json=data.input_payload_json,
            enabled=data.enabled,
        )

    async def update(self, schedule_id: UUID, workflow_id: UUID, data: ScheduleUpdate) -> Schedule:
        schedule = await self.get(schedule_id, workflow_id)
        update_data = data.model_dump(exclude_unset=True)
        return await workflow_repo.update_schedule(
            self.db, db_schedule=schedule, update_data=update_data
        )

    async def delete(self, schedule_id: UUID, workflow_id: UUID) -> None:
        schedule = await self.get(schedule_id, workflow_id)
        await workflow_repo.delete_schedule(self.db, schedule.id)

    async def list_by_project(
        self, project_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[Schedule], int]:
        return await workflow_repo.list_schedules_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def update_by_project(
        self, schedule_id: UUID, project_id: UUID, data: ScheduleUpdate
    ) -> Schedule:
        schedule = await workflow_repo.get_schedule_by_id(self.db, schedule_id)
        if not schedule or schedule.project_id != project_id:
            raise NotFoundError(
                message="Schedule not found", details={"schedule_id": str(schedule_id)}
            )
        update_data = data.model_dump(exclude_unset=True)
        return await workflow_repo.update_schedule(
            self.db, db_schedule=schedule, update_data=update_data
        )

    async def delete_by_project(self, schedule_id: UUID, project_id: UUID) -> None:
        schedule = await workflow_repo.get_schedule_by_id(self.db, schedule_id)
        if not schedule or schedule.project_id != project_id:
            raise NotFoundError(
                message="Schedule not found", details={"schedule_id": str(schedule_id)}
            )
        await workflow_repo.delete_schedule(self.db, schedule.id)
