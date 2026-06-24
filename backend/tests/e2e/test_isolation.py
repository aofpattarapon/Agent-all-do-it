"""E2E isolation tests — cross-project access must 404.

Tests use the mocked-repository pattern (AsyncMock db session + patched repos)
consistent with tests/test_project_access.py. No live database required.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.rbac import Permission, ProjectRole
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


# ── Non-member isolation ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_user_b_cannot_read_user_a_project(svc):
    """Non-member gets NotFoundError (we never reveal the project exists)."""
    user_a = _User()
    user_b = _User()
    project_a = _Project(owner_id=user_a.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project_a)
        member_repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.resolve_access(project_a.id, user_b, require=Permission.PROJECT_VIEW)


@pytest.mark.anyio
async def test_user_b_cannot_list_user_a_agents(svc):
    """Listing agents in a foreign project raises NotFoundError."""
    user_a = _User()
    user_b = _User()
    project_a = _Project(owner_id=user_a.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project_a)
        member_repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.resolve_access(project_a.id, user_b, require=Permission.AGENT_VIEW)


@pytest.mark.anyio
async def test_user_b_cannot_run_user_a_workflow(svc):
    """Attempting to run a workflow on a foreign project raises NotFoundError."""
    user_a = _User()
    user_b = _User()
    project_a = _Project(owner_id=user_a.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project_a)
        member_repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.resolve_access(project_a.id, user_b, require=Permission.RUN_EXECUTE)


@pytest.mark.anyio
async def test_user_b_cannot_read_user_a_knowledge(svc):
    """Knowledge base of a foreign project is hidden behind NotFoundError."""
    user_a = _User()
    user_b = _User()
    project_a = _Project(owner_id=user_a.id)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project_a)
        member_repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.resolve_access(project_a.id, user_b, require=Permission.KNOWLEDGE_VIEW)


# ── Member access ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_project_member_viewer_can_read_project(svc):
    """A VIEWER member can resolve PROJECT_VIEW without error."""
    owner = _User()
    viewer = _User()
    project = _Project(owner_id=owner.id)
    membership = _Member(ProjectRole.VIEWER)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=membership)

        access = await svc.resolve_access(project.id, viewer, require=Permission.PROJECT_VIEW)
    assert access.role == ProjectRole.VIEWER


@pytest.mark.anyio
async def test_project_member_viewer_cannot_execute_run(svc):
    """A VIEWER member cannot execute runs — AuthorizationError (not 404)."""
    owner = _User()
    viewer = _User()
    project = _Project(owner_id=owner.id)
    membership = _Member(ProjectRole.VIEWER)

    with (
        patch("app.services.project.project_repo") as repo,
        patch("app.services.project.project_member_repo") as member_repo,
    ):
        repo.get_by_id = AsyncMock(return_value=project)
        member_repo.get = AsyncMock(return_value=membership)

        with pytest.raises(AuthorizationError):
            await svc.resolve_access(project.id, viewer, require=Permission.RUN_EXECUTE)
