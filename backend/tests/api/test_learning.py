"""API tests for the read-only learning/lessons endpoint (Phase F)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db_session, get_project_service, get_redis
from app.main import app


@pytest.fixture
async def learning_client(mock_redis: MagicMock):
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
async def test_list_lessons_returns_trade_lessons(learning_client) -> None:
    project_id = uuid4()
    doc_id = uuid4()

    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.project_id = project_id
    mock_doc.agent_config_id = None
    mock_doc.title = "Trade Lesson: BTCUSDT SL"
    mock_doc.content = "Summary"
    mock_doc.tags = ["trade_lesson", "BTCUSDT", "loss"]
    mock_doc.source_url = None
    mock_doc.source_type = "trade_lesson"
    mock_doc.created_at = "2024-01-15T10:30:00+00:00"

    result = MagicMock()
    result.scalars.return_value.all.return_value = [mock_doc]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    app.dependency_overrides[get_db_session] = lambda: db

    response = await learning_client.get(f"/api/v1/projects/{project_id}/learning/lessons")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["title"] == "Trade Lesson: BTCUSDT SL"
    assert item["source_type"] == "trade_lesson"
    assert "trade_lesson" in item["tags"]
