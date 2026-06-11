"""SkillVersion service — canary routing, promotion, and rollback."""

from __future__ import annotations

import logging
import random
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models.skill_version import SkillVersion
from app.repositories import skill_version as skill_version_repo

logger = logging.getLogger(__name__)

_CANARY_PROMOTE_THRESHOLD = 0.05   # +5% winrate improvement triggers human review flag
_CANARY_MIN_SAMPLES = 50


class SkillVersionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_fragment(self, skill_id: UUID, original_fragment: str) -> str:
        """Return the prompt fragment to use for this skill.

        Routes canary_percentage% of calls to the canary version when one exists.
        Falls back to the active version, then to the original fragment.
        """
        canary = await skill_version_repo.get_canary(self.db, skill_id)
        if canary and canary.canary_percentage > 0 and random.random() < canary.canary_percentage / 100:
            return canary.prompt_fragment

        active = await skill_version_repo.get_active(self.db, skill_id)
        if active:
            return active.prompt_fragment

        return original_fragment

    async def create_version(
        self,
        skill_id: UUID,
        prompt_fragment: str,
        notes: str = "",
    ) -> SkillVersion:
        """Create a new canary version. NEVER auto-promotes — human approval required."""
        max_v = await skill_version_repo.get_max_version_number(self.db, skill_id)
        version = await skill_version_repo.create(
            self.db,
            skill_id=skill_id,
            version_number=max_v + 1,
            prompt_fragment=prompt_fragment,
            status="canary",
            canary_percentage=20,
            notes=notes or None,
        )
        logger.info(
            "SkillVersion: created canary v%d for skill %s — AWAITING HUMAN APPROVAL",
            version.version_number,
            skill_id,
        )
        return version

    async def approve(self, version_id: UUID, approver_id: UUID) -> SkillVersion:
        """Promote a canary version to active. Requires human approval.

        Demotes the current active → rollback_ready.
        Archives older rollback_ready versions.
        """
        version = await skill_version_repo.get_by_id(self.db, version_id)
        if version is None:
            raise NotFoundError(message="Skill version not found", details={"version_id": str(version_id)})
        if version.status != "canary":
            raise BadRequestError(
                message=f"Only canary versions can be approved (current status: {version.status})",
                details={"version_id": str(version_id), "status": version.status},
            )

        # Demote current active → rollback_ready
        current_active = await skill_version_repo.get_active(self.db, version.skill_id)
        if current_active:
            # Archive older rollback_ready first to keep only one
            old_rollback = await skill_version_repo.get_rollback_ready(self.db, version.skill_id)
            if old_rollback:
                await skill_version_repo.update(self.db, db_version=old_rollback, update_data={"status": "archived"})
            await skill_version_repo.update(self.db, db_version=current_active, update_data={"status": "rollback_ready"})

        # Promote canary → active
        return await skill_version_repo.update(
            self.db,
            db_version=version,
            update_data={
                "status": "active",
                "canary_percentage": 0,
                "approved_by": approver_id,
            },
        )

    async def rollback(self, skill_id: UUID) -> SkillVersion:
        """Revert to the rollback_ready version."""
        rollback_version = await skill_version_repo.get_rollback_ready(self.db, skill_id)
        if rollback_version is None:
            raise BadRequestError(
                message="No rollback-ready version available for this skill",
                details={"skill_id": str(skill_id)},
            )

        current_active = await skill_version_repo.get_active(self.db, skill_id)
        if current_active:
            await skill_version_repo.update(
                self.db, db_version=current_active, update_data={"status": "archived"}
            )

        return await skill_version_repo.update(
            self.db,
            db_version=rollback_version,
            update_data={"status": "active", "canary_percentage": 0},
        )

    async def record_outcome(self, skill_id: UUID, *, success: bool) -> None:
        """Update canary version quality metrics after a run step completes.

        Auto-archives underperforming canaries. Flags well-performing ones for
        human review — NEVER auto-promotes.
        """
        canary = await skill_version_repo.get_canary(self.db, skill_id)
        if canary is None:
            return

        new_sample = canary.sample_size + 1
        current_winrate = canary.winrate or 0.0
        # Incremental winrate update: running average
        new_winrate = ((current_winrate * canary.sample_size) + (1 if success else 0)) / new_sample

        update: dict = {"sample_size": new_sample, "winrate": new_winrate}

        if new_sample >= _CANARY_MIN_SAMPLES:
            active = await skill_version_repo.get_active(self.db, skill_id)
            active_winrate = (active.winrate or 0.0) if active else 0.0
            delta = new_winrate - active_winrate

            if delta >= _CANARY_PROMOTE_THRESHOLD:
                # Good enough — flag for human review (rollback_ready = "ready to promote")
                update["status"] = "rollback_ready"
                logger.info(
                    "SkillVersion: canary v%d for skill %s ready for promotion "
                    "(winrate +%.1f%% vs active) — AWAITING HUMAN APPROVAL",
                    canary.version_number, skill_id, delta * 100,
                )
            else:
                # Not improving — auto-archive
                update["status"] = "archived"
                logger.info(
                    "SkillVersion: auto-archiving canary v%d for skill %s "
                    "(delta %.1f%% < threshold)",
                    canary.version_number, skill_id, delta * 100,
                )

        await skill_version_repo.update(self.db, db_version=canary, update_data=update)
