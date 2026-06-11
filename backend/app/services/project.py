"""Project service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.rbac import Permission, ProjectAccess, ProjectRole
from app.db.models.project import Project
from app.db.models.user import User, UserRole
from app.repositories import project_member_repo, project_repo
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, project_id: UUID, user_id: UUID) -> Project:
        project = await project_repo.get_by_user_and_id(self.db, user_id=user_id, project_id=project_id)
        if not project:
            raise NotFoundError(message="Project not found", details={"project_id": str(project_id)})
        return project

    async def resolve_access(
        self,
        project_id: UUID,
        user: User,
        require: Permission | None = None,
    ) -> ProjectAccess:
        """Resolve the caller's RBAC authority within a project.

        Resolution order:

        * **Global admin** (``User.role == admin`` or ``is_app_admin``) → full
          access (``is_global_admin=True``).
        * **Project owner** (``Project.user_id``) → :data:`ProjectRole.OWNER`.
        * **Project member** → the role from their ``ProjectMember`` row.
        * **Anyone else** → :class:`NotFoundError` (we never reveal that a
          project the caller can't see exists).

        When ``require`` is provided the permission is enforced *before*
        returning, raising :class:`AuthorizationError` (HTTP 403) on failure.
        This is the single entry point every project route uses for both
        isolation (ownership/membership) and RBAC (permission) in one call.
        """
        project = await project_repo.get_by_id(self.db, project_id)
        if project is None:
            raise NotFoundError(
                message="Project not found", details={"project_id": str(project_id)}
            )

        is_global_admin = bool(getattr(user, "is_app_admin", False)) or (
            user.role == UserRole.ADMIN.value
        )

        if is_global_admin:
            access = ProjectAccess(
                project_id=project_id,
                user_id=user.id,
                role=ProjectRole.OWNER,
                is_global_admin=True,
                project=project,
            )
        elif project.user_id == user.id:
            access = ProjectAccess(
                project_id=project_id,
                user_id=user.id,
                role=ProjectRole.OWNER,
                project=project,
            )
        else:
            member = await project_member_repo.get(
                self.db, project_id=project_id, user_id=user.id
            )
            if member is None:
                raise NotFoundError(
                    message="Project not found",
                    details={"project_id": str(project_id)},
                )
            try:
                role = ProjectRole(member.project_role)
            except ValueError:
                role = ProjectRole.VIEWER
            access = ProjectAccess(
                project_id=project_id,
                user_id=user.id,
                role=role,
                project=project,
            )

        if require is not None:
            access.require(require)
        return access

    async def list(self, user_id: UUID, skip: int = 0, limit: int = 50) -> tuple[list[Project], int]:
        return await project_repo.list_by_user(self.db, user_id=user_id, skip=skip, limit=limit)

    async def create(self, user_id: UUID, data: ProjectCreate) -> Project:
        project = await project_repo.create(
            self.db,
            user_id=user_id,
            name=data.name,
            description=data.description,
        )
        # Auto-init per-project Obsidian vault and data directories
        try:
            from app.core.project_paths import project_vault_dir, project_run_artifacts_dir
            project_vault_dir(project.id)        # creates data/projects/{id}/vault/
            project_run_artifacts_dir(project.id)  # creates data/projects/{id}/run_artifacts/
            # Write a README so users know the vault location
            vault = project_vault_dir(project.id)
            readme = vault / "README.md"
            if not readme.exists():
                readme.write_text(
                    f"# {project.name}\n\nObsidian vault for project `{project.id}`.\n"
                    f"Trade journals, lessons, and run reports are auto-synced here.\n"
                )
        except Exception:
            pass
        return project

    async def update(self, project_id: UUID, user_id: UUID, data: ProjectUpdate) -> Project:
        project = await self.get(project_id, user_id)
        update_data = data.model_dump(exclude_unset=True)
        return await project_repo.update(self.db, db_project=project, update_data=update_data)

    async def delete(self, project_id: UUID, user_id: UUID) -> None:
        project = await self.get(project_id, user_id)
        await project_repo.delete(self.db, project.id)
