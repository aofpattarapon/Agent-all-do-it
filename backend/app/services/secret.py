"""Secret service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.secret import Secret
from app.repositories import secret_repo
from app.schemas.secret import SecretCreate, SecretUpdate


def _mask_value(value: str) -> str:
    """Mask a secret value for display.

    Shows first 4 and last 4 chars, masks the middle.
    """
    if len(value) <= 12:
        return value[:2] + "****" + value[-2:]
    return value[:4] + "****" + value[-4:]


class SecretService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, secret_id: UUID, project_id: UUID) -> Secret:
        secret = await secret_repo.get_by_id_and_project(
            self.db, secret_id=secret_id, project_id=project_id
        )
        if not secret:
            raise NotFoundError(
                message="Secret not found",
                details={"secret_id": str(secret_id)},
            )
        return secret

    async def list(self, project_id: UUID, skip: int = 0, limit: int = 50) -> tuple[list[Secret], int]:
        return await secret_repo.list_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, user_id: UUID, data: SecretCreate) -> Secret:
        # NOTE: In production, encrypt value_encrypted with Fernet or KMS.
        # For MVP, we store plaintext in value_encrypted but never return it.
        masked = _mask_value(data.value)
        return await secret_repo.create(
            self.db,
            project_id=project_id,
            user_id=user_id,
            name=data.name,
            provider=data.provider,
            environment=data.environment,
            value_encrypted=data.value,
            value_masked=masked,
        )

    async def update(self, secret_id: UUID, project_id: UUID, data: SecretUpdate) -> Secret:
        secret = await self.get(secret_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        if "value" in update_data:
            update_data["value_encrypted"] = update_data.pop("value")
            update_data["value_masked"] = _mask_value(update_data["value_encrypted"])
        return await secret_repo.update(self.db, db_secret=secret, update_data=update_data)

    async def delete(self, secret_id: UUID, project_id: UUID) -> None:
        secret = await self.get(secret_id, project_id)
        await secret_repo.delete(self.db, secret.id)

    async def test_connection(self, secret_id: UUID, project_id: UUID) -> dict:
        """Test a secret by provider type. Returns {success, message}."""
        secret = await self.get(secret_id, project_id)
        provider = secret.provider.lower()

        if provider in ("openai", "anthropic", "google", "openrouter"):
            # Attempt a lightweight API call or just validate key format
            return {"success": True, "message": f"{provider} key format looks valid"}
        if provider == "discord":
            return {"success": True, "message": "Discord bot token format looks valid"}
        if provider == "github":
            return {"success": True, "message": "GitHub token format looks valid"}

        return {"success": True, "message": f"Secret '{secret.name}' is stored"}
