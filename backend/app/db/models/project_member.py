"""ProjectMember model — per-project RBAC role assignments.

The project *owner* (``Project.user_id``) implicitly holds the ``owner`` role and
needs no membership row. Additional users are granted a scoped role
(``project_manager`` | ``trader`` | ``developer`` | ``viewer``) on a specific
project via a row here. See ``app.core.rbac.ProjectRole`` for the canonical role
values and ``app.core.rbac.ROLE_PERMISSIONS`` for the permission matrix.
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProjectMember(Base, TimestampMixin):
    """A user's role within a single project."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="project_members_project_id_user_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # One of app.core.rbac.ProjectRole values (excluding "owner", which is implicit).
    project_role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ProjectMember(project_id={self.project_id}, "
            f"user_id={self.user_id}, role={self.project_role})>"
        )
