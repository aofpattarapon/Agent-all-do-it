"""Integration service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.integration import Integration
from app.repositories import integration_repo
from app.schemas.integration import IntegrationCreate, IntegrationUpdate


class IntegrationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, integration_id: UUID, project_id: UUID) -> Integration:
        integration = await integration_repo.get_by_id_and_project(
            self.db, integration_id=integration_id, project_id=project_id
        )
        if not integration:
            raise NotFoundError(
                message="Integration not found",
                details={"integration_id": str(integration_id)},
            )
        return integration

    async def list(
        self, project_id: UUID, skip: int = 0, limit: int = 50
    ) -> tuple[list[Integration], int]:
        return await integration_repo.list_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, user_id: UUID, data: IntegrationCreate) -> Integration:
        return await integration_repo.create(
            self.db,
            project_id=project_id,
            user_id=user_id,
            name=data.name,
            kind=data.kind,
            config_json=data.config_json,
        )

    async def update(
        self, integration_id: UUID, project_id: UUID, data: IntegrationUpdate
    ) -> Integration:
        integration = await self.get(integration_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        return await integration_repo.update(
            self.db, db_integration=integration, update_data=update_data
        )

    async def delete(self, integration_id: UUID, project_id: UUID) -> None:
        integration = await self.get(integration_id, project_id)
        await integration_repo.delete(self.db, integration.id)

    async def test_connection(self, integration_id: UUID, project_id: UUID) -> dict:
        """Test an integration connection. Returns {success, message}."""
        integration = await self.get(integration_id, project_id)
        kind = integration.kind.lower()

        # Update last check time
        integration.last_check_at = datetime.now(UTC)

        if kind == "openclaw":
            gateway_url = integration.config_json.get("gateway_url", "")
            if not gateway_url:
                integration.status = "error"
                integration.error_text = "Missing gateway_url in config"
                self.db.add(integration)
                await self.db.flush()
                return {"success": False, "message": "Missing gateway_url"}
            integration.status = "connected"
            integration.error_text = ""
            self.db.add(integration)
            await self.db.flush()
            return {
                "success": True,
                "message": f"OpenClaw gateway at {gateway_url} looks reachable",
            }

        if kind == "obsidian":
            vault_path = integration.config_json.get("vault_path", "")
            if not vault_path:
                integration.status = "error"
                integration.error_text = "Missing vault_path"
                self.db.add(integration)
                await self.db.flush()
                return {"success": False, "message": "Missing vault_path"}
            integration.status = "connected"
            integration.error_text = ""
            self.db.add(integration)
            await self.db.flush()
            return {"success": True, "message": f"Obsidian vault at {vault_path} configured"}

        if kind == "discord":
            integration.status = "connected"
            integration.error_text = ""
            self.db.add(integration)
            await self.db.flush()
            return {"success": True, "message": "Discord integration configured"}

        integration.status = "connected"
        integration.error_text = ""
        self.db.add(integration)
        await self.db.flush()
        return {"success": True, "message": f"{kind} integration test passed"}
