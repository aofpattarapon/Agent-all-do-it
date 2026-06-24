from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_agent_config_service,
    get_app_setting_service,
    get_current_user,
    get_db_session,
    get_project_service,
    get_redis,
)
from app.main import app


@pytest.fixture
async def runtime_profile_client(mock_redis: MagicMock):
    user = SimpleNamespace(id=uuid4(), is_active=True)
    project_service = MagicMock()
    project_service.resolve_access = AsyncMock(
        return_value=SimpleNamespace(project=SimpleNamespace())
    )
    agent_service = MagicMock()
    agent_service.list = AsyncMock(return_value=([], 0))
    settings_service = MagicMock()
    settings_service.get = AsyncMock(return_value="test")
    settings_service.set = AsyncMock()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_agent_config_service] = lambda: agent_service
    app.dependency_overrides[get_app_setting_service] = lambda: settings_service
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, settings_service, db

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_get_runtime_profile_returns_all_valid_profiles(runtime_profile_client):
    client, _, _ = runtime_profile_client
    response = await client.get(f"/api/v1/projects/{uuid4()}/runtime-profile")

    assert response.status_code == 200
    assert response.json()["valid_profiles"] == [
        "test",
        "test-2",
        "test-minimal-paid",
        "test-jam",
        "test-local-free-24x7-safe",
        "production",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "profile",
    [
        "test",
        "test-2",
        "test-minimal-paid",
        "test-jam",
        "test-local-free-24x7-safe",
        "production",
    ],
)
async def test_post_runtime_profile_accepts_all_valid_profiles(
    runtime_profile_client, profile: str
):
    client, settings_service, db = runtime_profile_client
    project_id = uuid4()

    response = await client.post(
        f"/api/v1/projects/{project_id}/runtime-profile", json={"profile": profile}
    )

    assert response.status_code == 200
    assert response.json() == {
        "profile": profile,
        "valid_profiles": [
            "test",
            "test-2",
            "test-minimal-paid",
            "test-jam",
            "test-local-free-24x7-safe",
            "production",
        ],
    }
    settings_service.set.assert_awaited_with(f"project.{project_id}.runtime_profile", profile)
    db.commit.assert_awaited()


@pytest.mark.anyio
async def test_post_runtime_profile_rejects_unknown_profile(runtime_profile_client):
    client, _, _ = runtime_profile_client

    response = await client.post(
        f"/api/v1/projects/{uuid4()}/runtime-profile", json={"profile": "staging"}
    )

    assert response.status_code == 422
