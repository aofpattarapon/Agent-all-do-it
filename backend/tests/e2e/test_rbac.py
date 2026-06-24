"""E2E RBAC tests — permission matrix boundaries + critical role spot-checks.

Mix of pure unit tests (no DB) and service-level tests with mocked repos.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError
from app.core.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    ProjectRole,
    permissions_for_role,
)
from app.services.project import ProjectService


class _User:
    def __init__(self, uid=None, role="user", is_app_admin=False):
        self.id = uid or uuid4()
        self.role = role
        self.is_app_admin = is_app_admin


class _Project:
    def __init__(self, pid=None, owner_id=None):
        self.id = pid or uuid4()
        self.user_id = owner_id or uuid4()


class _Member:
    def __init__(self, project_role: ProjectRole):
        self.project_role = project_role


@pytest.fixture
def svc() -> ProjectService:
    return ProjectService(AsyncMock())


# ── Pure unit tests — no DB ───────────────────────────────────────────────────


def test_role_permissions_matrix_completeness():
    """Every ProjectRole value must appear in ROLE_PERMISSIONS."""
    for role in ProjectRole:
        assert role in ROLE_PERMISSIONS, f"Missing role in ROLE_PERMISSIONS: {role}"


@pytest.mark.parametrize(
    "role,perm,expected",
    [
        (ProjectRole.TRADER, Permission.TRADE_APPROVE, True),
        (ProjectRole.TRADER, Permission.AGENT_EDIT, False),
        (ProjectRole.TRADER, Permission.CODE_REVIEW_APPROVE, False),
        (ProjectRole.DEVELOPER, Permission.CODE_REVIEW_APPROVE, True),
        (ProjectRole.DEVELOPER, Permission.TRADE_APPROVE, False),
        (ProjectRole.VIEWER, Permission.RUN_EXECUTE, False),
        (ProjectRole.VIEWER, Permission.PROJECT_VIEW, True),
        (ProjectRole.OWNER, Permission.PROJECT_DELETE, True),
        (ProjectRole.PROJECT_MANAGER, Permission.RUN_EXECUTE, True),
        (ProjectRole.PROJECT_MANAGER, Permission.PROJECT_DELETE, False),
    ],
)
def test_permission_matrix(role: ProjectRole, perm: Permission, expected: bool):
    assert (perm in permissions_for_role(role)) == expected


# ── Service-level role boundary tests ─────────────────────────────────────────


@pytest.mark.anyio
async def test_trader_can_approve_trade(svc):
    """TRADER role can resolve TRADE_APPROVE without error."""
    owner = _User()
    trader = _User()
    project = _Project(owner_id=owner.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=_Member(ProjectRole.TRADER))

        access = await svc.resolve_access(project.id, trader, require=Permission.TRADE_APPROVE)
    assert access.has(Permission.TRADE_APPROVE)


@pytest.mark.anyio
async def test_trader_cannot_edit_agent(svc):
    """TRADER role cannot edit agents — AuthorizationError."""
    owner = _User()
    trader = _User()
    project = _Project(owner_id=owner.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=_Member(ProjectRole.TRADER))

        with pytest.raises(AuthorizationError):
            await svc.resolve_access(project.id, trader, require=Permission.AGENT_EDIT)


@pytest.mark.anyio
async def test_developer_can_approve_code_review(svc):
    """DEVELOPER role can resolve CODE_REVIEW_APPROVE."""
    owner = _User()
    dev = _User()
    project = _Project(owner_id=owner.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=_Member(ProjectRole.DEVELOPER))

        access = await svc.resolve_access(project.id, dev, require=Permission.CODE_REVIEW_APPROVE)
    assert access.has(Permission.CODE_REVIEW_APPROVE)


@pytest.mark.anyio
async def test_developer_cannot_approve_trade(svc):
    """DEVELOPER role cannot approve trades — AuthorizationError."""
    owner = _User()
    dev = _User()
    project = _Project(owner_id=owner.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=_Member(ProjectRole.DEVELOPER))

        with pytest.raises(AuthorizationError):
            await svc.resolve_access(project.id, dev, require=Permission.TRADE_APPROVE)


@pytest.mark.anyio
async def test_project_manager_can_run_workflow(svc):
    """PROJECT_MANAGER can execute runs."""
    owner = _User()
    pm = _User()
    project = _Project(owner_id=owner.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=_Member(ProjectRole.PROJECT_MANAGER))

        access = await svc.resolve_access(project.id, pm, require=Permission.RUN_EXECUTE)
    assert access.has(Permission.RUN_EXECUTE)


@pytest.mark.anyio
async def test_project_manager_cannot_delete_project(svc):
    """PROJECT_MANAGER cannot delete the project — AuthorizationError."""
    owner = _User()
    pm = _User()
    project = _Project(owner_id=owner.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=_Member(ProjectRole.PROJECT_MANAGER))

        with pytest.raises(AuthorizationError):
            await svc.resolve_access(project.id, pm, require=Permission.PROJECT_DELETE)


@pytest.mark.anyio
async def test_viewer_cannot_run_anything(svc):
    """VIEWER member cannot execute runs — AuthorizationError."""
    owner = _User()
    viewer = _User()
    project = _Project(owner_id=owner.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=_Member(ProjectRole.VIEWER))

        with pytest.raises(AuthorizationError):
            await svc.resolve_access(project.id, viewer, require=Permission.RUN_EXECUTE)
