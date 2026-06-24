"""API tests for the read-only agents/quality endpoint (Phase F)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_project_service, get_redis
from app.main import app


@pytest.fixture
async def quality_client(mock_redis: MagicMock):
    user = SimpleNamespace(id=uuid4(), is_active=True)
    project_service = MagicMock()
    project_service.resolve_access = AsyncMock(
        return_value=SimpleNamespace(project=SimpleNamespace())
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_list_agent_quality_returns_metrics(quality_client) -> None:
    project_id = uuid4()

    mock_data = {
        "items": [
            {
                "agent_id": str(uuid4()),
                "name": "HAWK",
                "role": "hawk_gate",
                "is_active": True,
                "total_steps": 10,
                "total_runs": 5,
                "successful_outputs": 8,
                "failed_outputs": 2,
                "validation_failures": 0,
                "contract_failures": 0,
                "retry_count": 0,
                "error_runs": 0,
                "last_activity": "2024-01-15T10:30:00+00:00",
                "quality_rate": 80.0,
            }
        ],
        "generated_at": "2024-01-15T10:30:00+00:00",
    }

    with patch(
        "app.api.routes.v1.agent_quality.AgentQualityService.aggregate",
        new=AsyncMock(return_value=mock_data),
    ):
        response = await quality_client.get(f"/api/v1/projects/{project_id}/agents/quality")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["name"] == "HAWK"
    assert item["quality_rate"] == 80.0
    assert item["total_steps"] == 10
