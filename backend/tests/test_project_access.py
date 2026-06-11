"""Tests for ProjectService.resolve_access — project isolation + RBAC.

Follows the mocked-repository pattern used across ``tests/test_services.py``
(``AsyncMock`` db session + ``patch``-ed repositories). Validates the two
headline Phase 0 guarantees:

* **Isolation** — a user who is neither owner nor member cannot resolve another
  user's project (raises ``NotFoundError``; existence is never revealed).
* **RBAC** — a *trader* is the trade-approval gate but cannot edit agents; a
  *developer* is the code-review gate but cannot approve trades.

Note: requires the project's Python 3.12 runtime (the codebase uses
``datetime.UTC`` / ``enum.StrEnum``).
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.rbac import Permission, ProjectRole
from app.services.project import ProjectService


class MockUser:
    def __init__(self, id=None, role="user", is_app_admin=False):
        self.id = id or uuid4()
        self.role = role
        self.is_app_admin = is_app_admin


class MockProject:
    def __init__(self, id=None, user_id=None):
        self.id = id or uuid4()
        self.user_id = user_id or uuid4()


class MockMember:
    def __init__(self, project_role):
        self.project_role = project_role


@pytest.fixture
def service() -> ProjectService:
    return ProjectService(AsyncMock())


class TestResolveAccess:
    @pytest.mark.anyio
    async def test_owner_gets_owner_role_and_all_permissions(self, service):
        user = MockUser()
        project = MockProject(user_id=user.id)
        with patch("app.services.project.project_repo") as repo:
            repo.get_by_id = AsyncMock(return_value=project)
            access = await service.resolve_access(project.id, user)
        assert access.role == ProjectRole.OWNER
        assert access.has(Permission.PROJECT_DELETE)
        assert access.has(Permission.TRADE_APPROVE)

    @pytest.mark.anyio
    async def test_global_admin_gets_full_access_on_any_project(self, service):
        admin = MockUser(role="admin")
        project = MockProject()  # owned by someone else
        with patch("app.services.project.project_repo") as repo:
            repo.get_by_id = AsyncMock(return_value=project)
            access = await service.resolve_access(project.id, admin)
        assert access.is_global_admin is True
        assert access.has(Permission.PROJECT_DELETE)

    @pytest.mark.anyio
    async def test_non_member_cannot_see_project(self, service):
        outsider = MockUser()
        project = MockProject()  # owned by someone else
        with (
            patch("app.services.project.project_repo") as repo,
            patch("app.services.project.project_member_repo") as mrepo,
        ):
            repo.get_by_id = AsyncMock(return_value=project)
            mrepo.get = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await service.resolve_access(project.id, outsider)

    @pytest.mark.anyio
    async def test_missing_project_raises_not_found(self, service):
        with patch("app.services.project.project_repo") as repo:
            repo.get_by_id = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await service.resolve_access(uuid4(), MockUser())

    @pytest.mark.anyio
    async def test_trader_can_approve_trades_but_not_edit_agents(self, service):
        user = MockUser()
        project = MockProject()  # user is not the owner
        with (
            patch("app.services.project.project_repo") as repo,
            patch("app.services.project.project_member_repo") as mrepo,
        ):
            repo.get_by_id = AsyncMock(return_value=project)
            mrepo.get = AsyncMock(return_value=MockMember("trader"))

            access = await service.resolve_access(
                project.id, user, require=Permission.TRADE_APPROVE
            )
            assert access.role == ProjectRole.TRADER

            with pytest.raises(AuthorizationError):
                await service.resolve_access(
                    project.id, user, require=Permission.AGENT_EDIT
                )

    @pytest.mark.anyio
    async def test_developer_can_approve_code_but_not_trades(self, service):
        user = MockUser()
        project = MockProject()
        with (
            patch("app.services.project.project_repo") as repo,
            patch("app.services.project.project_member_repo") as mrepo,
        ):
            repo.get_by_id = AsyncMock(return_value=project)
            mrepo.get = AsyncMock(return_value=MockMember("developer"))

            access = await service.resolve_access(
                project.id, user, require=Permission.CODE_REVIEW_APPROVE
            )
            assert access.role == ProjectRole.DEVELOPER

            with pytest.raises(AuthorizationError):
                await service.resolve_access(
                    project.id, user, require=Permission.TRADE_APPROVE
                )
