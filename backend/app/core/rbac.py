"""Role-based access control (RBAC) for project-scoped operations.

Two independent layers of authority exist in the hub:

* **Global role** — stored on ``User.role`` (``admin`` | ``user``). ``admin`` is a
  superuser that implicitly holds every permission in every project.
* **Project role** — stored on ``ProjectMember.project_role`` and granted per
  ``(user, project)`` pair. The project *owner* (``Project.user_id``) implicitly
  holds the :data:`ProjectRole.OWNER` role without needing a membership row.

Concrete permissions are derived from the project role via
:data:`ROLE_PERMISSIONS`. The crypto pipeline needs a human to *approve trades*
(:data:`Permission.TRADE_APPROVE`); the SDLC pipeline needs a human to *approve
code reviews* (:data:`Permission.CODE_REVIEW_APPROVE`). These are deliberately
NOT granted to every role — they are the human-in-the-loop gates.

This module is intentionally **dependency-free** (standard library only) so the
permission matrix can be unit-tested in isolation, without importing FastAPI,
SQLAlchemy, or application settings. The FastAPI wiring lives in
``app.api.deps`` (``require_project_permission``) and the persistence lookup in
``app.services.project`` (``ProjectService.resolve_access``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.core.exceptions import AuthorizationError


class ProjectRole(StrEnum):
    """A user's role *within a single project*.

    Ordered loosely from most to least privileged. ``OWNER`` is the project
    creator; the remaining roles map to the two reference pipelines:

    * ``TRADER``    — crypto pipeline: approves/rejects trade signals.
    * ``DEVELOPER`` — SDLC pipeline: edits agents, runs workflows, approves code.
    * ``PROJECT_MANAGER`` — coordinates a project but is *not* a trade approver.
    * ``VIEWER``    — read-only observer.
    """

    OWNER = "owner"
    PROJECT_MANAGER = "project_manager"
    TRADER = "trader"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Permission(StrEnum):
    """A single, fine-grained capability checked at the API boundary."""

    # ── Project lifecycle ──
    PROJECT_VIEW = "project:view"
    PROJECT_EDIT = "project:edit"
    PROJECT_DELETE = "project:delete"
    MEMBER_MANAGE = "project:member_manage"

    # ── Agents & configuration ──
    AGENT_VIEW = "agent:view"
    AGENT_EDIT = "agent:edit"

    # ── Knowledge base ──
    KNOWLEDGE_VIEW = "knowledge:view"
    KNOWLEDGE_EDIT = "knowledge:edit"

    # ── Workflows & runs ──
    WORKFLOW_VIEW = "workflow:view"
    WORKFLOW_EDIT = "workflow:edit"
    RUN_EXECUTE = "run:execute"
    RUN_VIEW = "run:view"
    HANDOFF_APPROVE = "handoff:approve"

    # ── Trading (crypto project) — human-in-the-loop gate ──
    TRADE_VIEW = "trade:view"
    TRADE_APPROVE = "trade:approve"
    TRADE_REJECT = "trade:reject"

    # ── SDLC (dev project) — human-in-the-loop gate ──
    CODE_REVIEW_APPROVE = "code:review_approve"

    # ── Secrets ──
    SECRET_VIEW = "secret:view"
    SECRET_EDIT = "secret:edit"


#: Every permission in the system — what an OWNER / global admin holds.
ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)

#: Read-only "view" permissions, shared by VIEWER and every higher role.
_VIEW_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.PROJECT_VIEW,
        Permission.AGENT_VIEW,
        Permission.KNOWLEDGE_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.RUN_VIEW,
        Permission.TRADE_VIEW,
    }
)

#: A project_manager coordinates everything *except* destroying the project and
#: except the two human-in-the-loop approval gates (those require the explicit
#: trader / developer roles, per least-privilege).
_PROJECT_MANAGER_PERMISSIONS: frozenset[Permission] = _VIEW_PERMISSIONS | frozenset(
    {
        Permission.PROJECT_EDIT,
        Permission.MEMBER_MANAGE,
        Permission.AGENT_EDIT,
        Permission.KNOWLEDGE_EDIT,
        Permission.WORKFLOW_EDIT,
        Permission.RUN_EXECUTE,
        Permission.HANDOFF_APPROVE,
        Permission.SECRET_VIEW,
    }
)

#: A trader observes the pipeline and is the human gate on trade signals.
_TRADER_PERMISSIONS: frozenset[Permission] = _VIEW_PERMISSIONS | frozenset(
    {
        Permission.RUN_VIEW,
        Permission.HANDOFF_APPROVE,
        Permission.TRADE_APPROVE,
        Permission.TRADE_REJECT,
    }
)

#: A developer builds and runs the SDLC pipeline and is the human gate on code.
_DEVELOPER_PERMISSIONS: frozenset[Permission] = _VIEW_PERMISSIONS | frozenset(
    {
        Permission.AGENT_EDIT,
        Permission.KNOWLEDGE_EDIT,
        Permission.WORKFLOW_EDIT,
        Permission.RUN_EXECUTE,
        Permission.HANDOFF_APPROVE,
        Permission.CODE_REVIEW_APPROVE,
        Permission.SECRET_VIEW,
    }
)


#: The authoritative project-role → permission-set matrix.
ROLE_PERMISSIONS: dict[ProjectRole, frozenset[Permission]] = {
    ProjectRole.OWNER: ALL_PERMISSIONS,
    ProjectRole.PROJECT_MANAGER: _PROJECT_MANAGER_PERMISSIONS,
    ProjectRole.TRADER: _TRADER_PERMISSIONS,
    ProjectRole.DEVELOPER: _DEVELOPER_PERMISSIONS,
    ProjectRole.VIEWER: _VIEW_PERMISSIONS,
}


def permissions_for_role(role: ProjectRole | str) -> frozenset[Permission]:
    """Return the permission set granted by ``role`` (empty set if unknown)."""
    if not isinstance(role, ProjectRole):
        try:
            role = ProjectRole(role)
        except ValueError:
            return frozenset()
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: ProjectRole | str, permission: Permission) -> bool:
    """True if ``role`` grants ``permission``."""
    return permission in permissions_for_role(role)


@dataclass(frozen=True)
class ProjectAccess:
    """The resolved authority a user holds within one project.

    Produced by ``ProjectService.resolve_access`` and consumed by the
    ``require_project_permission`` FastAPI dependency. ``project`` carries the
    loaded ORM object (typed loosely to keep this module ORM-free) so routes
    don't need a second database round-trip.
    """

    project_id: UUID
    user_id: UUID
    role: ProjectRole
    is_global_admin: bool = False
    project: Any = field(default=None, repr=False)

    @property
    def permissions(self) -> frozenset[Permission]:
        """The effective permission set (global admins hold everything)."""
        if self.is_global_admin:
            return ALL_PERMISSIONS
        return permissions_for_role(self.role)

    def has(self, permission: Permission) -> bool:
        """Non-raising permission check."""
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        """Raise :class:`AuthorizationError` (HTTP 403) if ``permission`` is absent."""
        if not self.has(permission):
            raise AuthorizationError(
                message=f"Permission '{permission.value}' required for this action",
                details={
                    "required_permission": permission.value,
                    "project_role": self.role.value,
                    "project_id": str(self.project_id),
                },
            )
