"""API test for the read-only run-summary endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db_session, get_project_service, get_redis
from app.main import app


@pytest.fixture
async def runs_client(mock_redis: MagicMock):
    user = SimpleNamespace(id=uuid4(), is_active=True)
    project_service = MagicMock()
    project_service.resolve_access = AsyncMock(
        return_value=SimpleNamespace(project=SimpleNamespace())
    )
    db = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_runs_summary_aggregates_canonical_display_status(runs_client, monkeypatch) -> None:
    classified = [
        {"display_status": "active", "workflow_category": "trade"},
        {"display_status": "complete-trade", "workflow_category": "trade"},
        {"display_status": "complete-reject", "workflow_category": "trade"},
        {"display_status": "complete-reject", "workflow_category": "trade"},
        {"display_status": "limit", "workflow_category": "trade"},
        {"display_status": "error", "workflow_category": "trade"},
        {"display_status": "complete-reject", "workflow_category": "monitor"},
    ]

    async def fake_classify(_db, _project_id):
        return classified

    monkeypatch.setattr("app.api.routes.v1.runs.classify_project_runs", fake_classify)

    response = await runs_client.get(f"/api/v1/projects/{uuid4()}/runs/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 7
    assert body["active"] == 1
    assert body["terminal"] == 6
    assert body["by_display_status"] == {
        "active": 1,
        "complete-trade": 1,
        "complete-reject": 3,
        "limit": 1,
        "error": 1,
    }
    # complete-reject and limit are NOT errors.
    assert body["by_display_status"]["error"] == 1
    # trade_pipeline excludes the monitor run.
    assert body["trade_pipeline"]["total"] == 6
    assert body["trade_pipeline"]["complete-reject"] == 2
    assert "generated_at" in body
