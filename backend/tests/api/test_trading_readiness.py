"""API test for the read-only trading readiness endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db_session, get_project_service, get_redis
from app.main import app


@pytest.fixture
async def trading_client(mock_redis: MagicMock):
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
async def test_readiness_demo_is_order_capable(trading_client, monkeypatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "DEMO")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.setenv("BINANCE_FUTURES_DEMO_API_KEY", "SECRET-KEY-XYZ")
    monkeypatch.setenv("BINANCE_FUTURES_DEMO_API_SECRET", "SECRET-SECRET-XYZ")

    response = await trading_client.get(f"/api/v1/projects/{uuid4()}/trading/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["is_order_capable"] is True
    assert body["will_send_exchange_order"] is True
    assert body["readiness"] == "ready"
    assert body["credential_values_exposed"] is False
    # No secret values leaked anywhere in the response body.
    assert "SECRET-KEY-XYZ" not in response.text
    assert "SECRET-SECRET-XYZ" not in response.text


@pytest.mark.anyio
async def test_readiness_paper_never_sends(trading_client, monkeypatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "paper")
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setenv("MARKET_TYPE", "futures")

    response = await trading_client.get(f"/api/v1/projects/{uuid4()}/trading/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["is_order_capable"] is False
    assert body["will_send_exchange_order"] is False
    assert body["readiness"] == "ready"
