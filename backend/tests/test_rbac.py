"""Unit tests for the project RBAC permission matrix (app.core.rbac).

These are pure-logic tests — no database or FastAPI required.
"""

from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError
from app.core.rbac import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    ProjectAccess,
    ProjectRole,
    permissions_for_role,
    role_has_permission,
)


def test_owner_holds_every_permission():
    assert permissions_for_role(ProjectRole.OWNER) == ALL_PERMISSIONS


def test_every_role_is_in_the_matrix():
    for role in ProjectRole:
        assert role in ROLE_PERMISSIONS


def test_viewer_is_read_only():
    perms = permissions_for_role(ProjectRole.VIEWER)
    assert Permission.PROJECT_VIEW in perms
    assert Permission.TRADE_VIEW in perms
    # No mutation or approval capability whatsoever.
    for forbidden in (
        Permission.PROJECT_EDIT,
        Permission.AGENT_EDIT,
        Permission.KNOWLEDGE_EDIT,
        Permission.WORKFLOW_EDIT,
        Permission.RUN_EXECUTE,
        Permission.TRADE_APPROVE,
        Permission.CODE_REVIEW_APPROVE,
        Permission.PROJECT_DELETE,
    ):
        assert forbidden not in perms


def test_trader_is_the_trade_gate_only():
    perms = permissions_for_role(ProjectRole.TRADER)
    assert Permission.TRADE_APPROVE in perms
    assert Permission.TRADE_REJECT in perms
    assert Permission.HANDOFF_APPROVE in perms
    # A trader does not edit agents or approve code reviews.
    assert Permission.AGENT_EDIT not in perms
    assert Permission.CODE_REVIEW_APPROVE not in perms
    assert Permission.PROJECT_DELETE not in perms


def test_developer_is_the_code_gate_not_the_trade_gate():
    perms = permissions_for_role(ProjectRole.DEVELOPER)
    assert Permission.CODE_REVIEW_APPROVE in perms
    assert Permission.AGENT_EDIT in perms
    assert Permission.RUN_EXECUTE in perms
    # The single most important separation: a developer cannot approve trades.
    assert Permission.TRADE_APPROVE not in perms
    assert Permission.TRADE_REJECT not in perms


def test_project_manager_cannot_approve_trades_or_delete_project():
    perms = permissions_for_role(ProjectRole.PROJECT_MANAGER)
    assert Permission.PROJECT_EDIT in perms
    assert Permission.MEMBER_MANAGE in perms
    assert Permission.RUN_EXECUTE in perms
    assert Permission.TRADE_APPROVE not in perms
    assert Permission.PROJECT_DELETE not in perms


def test_only_owner_can_delete_project():
    holders = [r for r in ProjectRole if Permission.PROJECT_DELETE in permissions_for_role(r)]
    assert holders == [ProjectRole.OWNER]


def test_only_trader_and_owner_can_approve_trades():
    holders = {r for r in ProjectRole if Permission.TRADE_APPROVE in permissions_for_role(r)}
    assert holders == {ProjectRole.OWNER, ProjectRole.TRADER}


def test_unknown_role_grants_nothing():
    assert permissions_for_role("nonexistent-role") == frozenset()
    assert role_has_permission("nonexistent-role", Permission.PROJECT_VIEW) is False


def test_project_access_require_raises_when_missing():
    access = ProjectAccess(
        project_id=uuid4(), user_id=uuid4(), role=ProjectRole.VIEWER
    )
    assert access.has(Permission.PROJECT_VIEW) is True
    with pytest.raises(AuthorizationError):
        access.require(Permission.TRADE_APPROVE)


def test_global_admin_access_holds_everything():
    access = ProjectAccess(
        project_id=uuid4(),
        user_id=uuid4(),
        role=ProjectRole.VIEWER,  # role is irrelevant for a global admin
        is_global_admin=True,
    )
    assert access.permissions == ALL_PERMISSIONS
    access.require(Permission.PROJECT_DELETE)  # must not raise
