"""API tests for the read-only trading runtime-mode endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_current_user,
    get_db_session,
    get_project_service,
    get_redis,
)
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
async def test_runtime_mode_returns_exchange_demo(trading_client, monkeypatch):
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "DEMO")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.setenv("EXCHANGE", "BINANCE_FUTURES")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    monkeypatch.setenv("ALLOW_ORDER_EXECUTION", "true")

    response = await trading_client.get(f"/api/v1/projects/{uuid4()}/trading/runtime-mode")

    assert response.status_code == 200
    body = response.json()
    assert body["runtime_mode"] == "exchange_demo"
    assert body["label"] == "Binance Demo Futures"
    assert body["is_exchange_backed"] is True
    assert body["is_paper_simulation"] is False
    assert body["is_order_capable"] is True
    assert body["is_demo"] is True
    assert body["is_live"] is False
    assert body["order_placement_enabled"] is False
    assert body["monitoring_exchange_backed"] is True
    assert body["safety_label"] == "Virtual money / no live funds"
    assert body["trading_mode"] == "DEMO"
    assert body["conflict"] is None


@pytest.mark.anyio
async def test_runtime_mode_returns_paper_simulation(trading_client, monkeypatch):
    monkeypatch.setenv("EXCHANGE_MODE", "paper")
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")

    response = await trading_client.get(f"/api/v1/projects/{uuid4()}/trading/runtime-mode")

    assert response.status_code == 200
    body = response.json()
    assert body["runtime_mode"] == "paper_simulation"
    assert body["label"] == "Paper Simulation"
    assert body["is_exchange_backed"] is False
    assert body["monitoring_exchange_backed"] is False
