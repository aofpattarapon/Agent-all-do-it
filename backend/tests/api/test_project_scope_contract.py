"""Isolation contract tests for project-scoped operational config."""

from app.db.models.integration import Integration
from app.db.models.secret import Secret


def test_secret_project_scope_is_required():
    """Secrets are operational project config, not mixed-scope rows."""
    assert Secret.__table__.c.project_id.nullable is False


def test_integration_project_scope_is_required():
    """Integrations are operational project config, not mixed-scope rows."""
    assert Integration.__table__.c.project_id.nullable is False
