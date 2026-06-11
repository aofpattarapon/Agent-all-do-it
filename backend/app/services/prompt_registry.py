"""Prompt version registry service (ported from SDLC PromptRegistry).

Stores SHA-256 hashes and character counts ONLY — never the full prompt text,
which may contain live runtime context. Versions auto-increment per
(project_id, role, task_type) whenever the prompt hash changes.
"""

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import PromptRegistryEntry


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class PromptRegistryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _latest(
        self, project_id: UUID, role: str, task_type: str
    ) -> PromptRegistryEntry | None:
        result = await self.db.execute(
            select(PromptRegistryEntry)
            .where(
                PromptRegistryEntry.project_id == project_id,
                PromptRegistryEntry.role == role,
                PromptRegistryEntry.task_type == task_type,
            )
            .order_by(PromptRegistryEntry.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def record(
        self,
        *,
        project_id: UUID,
        run_id: UUID | None,
        role: str,
        task_type: str,
        prompt_text: str,
        system_text: str,
    ) -> PromptRegistryEntry:
        """Record a prompt version.

        If the latest entry for (project_id, role, task_type) already has the
        same prompt hash, that entry is returned unchanged. Otherwise a new
        entry is created with version = latest.version + 1.
        """
        prompt_hash = _sha256(prompt_text)
        system_hash = _sha256(system_text) if system_text else ""

        latest = await self._latest(project_id, role, task_type)
        if latest is not None and latest.prompt_hash == prompt_hash:
            return latest

        version = (latest.version + 1) if latest is not None else 1
        entry = PromptRegistryEntry(
            project_id=project_id,
            run_id=run_id,
            role=role,
            task_type=task_type,
            prompt_hash=prompt_hash,
            system_hash=system_hash,
            prompt_chars=len(prompt_text or ""),
            system_chars=len(system_text or ""),
            version=version,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def list_for_project(self, project_id: UUID) -> list[PromptRegistryEntry]:
        result = await self.db.execute(
            select(PromptRegistryEntry)
            .where(PromptRegistryEntry.project_id == project_id)
            .order_by(PromptRegistryEntry.created_at.desc())
        )
        return list(result.scalars().all())

    async def versions_for_role(self, project_id: UUID, role: str) -> list[PromptRegistryEntry]:
        result = await self.db.execute(
            select(PromptRegistryEntry)
            .where(
                PromptRegistryEntry.project_id == project_id,
                PromptRegistryEntry.role == role,
            )
            .order_by(PromptRegistryEntry.version.desc())
        )
        return list(result.scalars().all())
