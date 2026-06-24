"""API tests for the admin trading-mode settings endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_app_setting_service, get_current_user, get_redis
from app.db.models.user import UserRole
from app.main import app


class _AdminUser:
    def __init__(self) -> None:
        self.id = uuid4()
        self.is_active = True

    def has_role(self, role: UserRole) -> bool:
        return role == UserRole.ADMIN


@pytest.fixture
async def trading_settings_client(monkeypatch):
    user = _AdminUser()
    settings_service = MagicMock()
    settings_service.get_trading_mode_config = AsyncMock(
        return_value={"trading_mode": None, "exchange_mode": None}
    )
    settings_service.set_trading_mode_config = AsyncMock()
    mock_redis = MagicMock()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_app_setting_service] = lambda: settings_service
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, settings_service

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_get_trading_mode_config_returns_environment_values(
    trading_settings_client, monkeypatch
):
    client, _ = trading_settings_client
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "DEMO")

    response = await client.get("/api/v1/admin/settings/trading")

    assert response.status_code == 200
    body = response.json()
    assert body["trading_mode"] == "DEMO"
    assert body["exchange_mode"] == "demo"
    assert body["resolved_runtime_mode"] == "demo"
    assert body["conflict"] is None
    assert body["source"] == "environment"


@pytest.mark.anyio
async def test_get_trading_mode_config_reports_conflict(trading_settings_client, monkeypatch):
    client, _ = trading_settings_client
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "PAPER")

    response = await client.get("/api/v1/admin/settings/trading")

    assert response.status_code == 200
    body = response.json()
    assert body["conflict"] is not None
    assert "PAPER" in body["conflict"]


@pytest.mark.anyio
async def test_patch_trading_mode_config_rejects_mismatched_pair(trading_settings_client):
    client, _ = trading_settings_client

    response = await client.patch(
        "/api/v1/admin/settings/trading",
        json={"trading_mode": "PAPER", "exchange_mode": "demo"},
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_patch_trading_mode_config_rejects_live_without_confirmation(
    trading_settings_client,
):
    client, _ = trading_settings_client

    response = await client.patch(
        "/api/v1/admin/settings/trading",
        json={"trading_mode": "LIVE", "exchange_mode": "live"},
    )

    assert response.status_code == 400
    assert "confirm_live" in response.json()["detail"]


@pytest.mark.anyio
async def test_patch_trading_mode_config_accepts_demo_pair(trading_settings_client, monkeypatch):
    client, settings_service = trading_settings_client
    overrides: dict[str, str] = {}

    def fake_read() -> tuple[str | None, str | None]:
        return overrides.get("trading_mode"), overrides.get("exchange_mode")

    def fake_write(trading_mode: str, exchange_mode: str) -> None:
        overrides["trading_mode"] = trading_mode
        overrides["exchange_mode"] = exchange_mode

    monkeypatch.setattr(
        "app.services.trading_mode._read_redis_mode_overrides",
        fake_read,
    )
    monkeypatch.setattr(
        "app.api.routes.v1.app_settings.write_trading_mode_overrides",
        fake_write,
    )

    response = await client.patch(
        "/api/v1/admin/settings/trading",
        json={"trading_mode": "DEMO", "exchange_mode": "demo"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trading_mode"] == "DEMO"
    assert body["exchange_mode"] == "demo"
    assert body["conflict"] is None
    assert body["source"] == "runtime"
    settings_service.set_trading_mode_config.assert_awaited_once_with("DEMO", "demo")
