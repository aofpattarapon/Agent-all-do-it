"""API tests for the read-only HAWK condition watch endpoint (Phase 6.14.W28M).

The endpoint is strictly read-only and advisory. These tests verify it returns a
posture object with the hard safety fields, honours the ``symbols`` query param,
degrades safely when market data is unavailable, is GET-only, and never invokes any
order / dispatch / approval path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

import app.agents.tools.exchange_tool as exchange_tool
from app.api.deps import (
    get_current_user,
    get_db_session,
    get_project_service,
    get_redis,
)
from app.main import app

_WATCH_PATH = "/api/v1/projects/{pid}/trading/hawk-condition-watch"

# A flat synthetic 1h candle: [open_time, open, high, low, close, volume, ...].
# 48 of these form a low-range, low-volatility series → NOT_READY (never READY).
_FLAT_CANDLE = [0, 100.0, 100.4, 99.6, 100.0, 1000.0, 0, 0, 0, 0, 0, 0]


def _flat_klines(n: int = 48) -> list[list]:
    return [list(_FLAT_CANDLE) for _ in range(n)]


@pytest.fixture
async def watch_client(mock_redis: MagicMock):
    user = SimpleNamespace(id=uuid4(), is_active=True)
    project_service = MagicMock()
    project_service.resolve_access = AsyncMock(
        return_value=SimpleNamespace(project=SimpleNamespace())
    )
    # Model AsyncSession: async ``execute`` returning a sync ``Result`` whose
    # ``.all()``/``.first()`` yield empty history. The watch only reads — there is
    # no add/flush/commit, so no mutation is even expressible here.
    result = MagicMock()
    result.all.return_value = []
    result.first.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_returns_200_and_posture_object(watch_client, monkeypatch):
    monkeypatch.setattr(exchange_tool, "get_klines", AsyncMock(return_value=_flat_klines()))

    resp = await watch_client.get(_WATCH_PATH.format(pid=uuid4()))

    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_posture"] in {"READY", "NOT_READY", "HOLD"}
    assert "recommended_action" in body
    assert isinstance(body["candidates"], list) and body["candidates"]
    assert "generated_at" in body


@pytest.mark.anyio
async def test_response_includes_hard_safety_fields(watch_client, monkeypatch):
    monkeypatch.setattr(exchange_tool, "get_klines", AsyncMock(return_value=_flat_klines()))

    body = (await watch_client.get(_WATCH_PATH.format(pid=uuid4()))).json()

    assert body["order_capable"] is False
    assert body["dispatch_capable"] is False
    assert body["approval_required_for_retry"] is True
    assert body["validation_only_unchanged"] is True


@pytest.mark.anyio
async def test_symbols_query_param_is_honoured(watch_client, monkeypatch):
    monkeypatch.setattr(exchange_tool, "get_klines", AsyncMock(return_value=_flat_klines()))

    resp = await watch_client.get(
        _WATCH_PATH.format(pid=uuid4()), params={"symbols": "btcusdt, ethusdt"}
    )

    assert resp.status_code == 200
    symbols = [c["symbol"] for c in resp.json()["candidates"]]
    assert symbols == ["BTCUSDT", "ETHUSDT"]


@pytest.mark.anyio
async def test_market_data_unavailable_is_safe(watch_client, monkeypatch):
    # No klines available → service must degrade to NOT_READY/HOLD, never READY.
    monkeypatch.setattr(exchange_tool, "get_klines", AsyncMock(return_value=[]))

    body = (await watch_client.get(_WATCH_PATH.format(pid=uuid4()))).json()

    assert body["overall_posture"] in {"NOT_READY", "HOLD"}
    assert body["overall_posture"] != "READY"
    assert all(c["posture"] != "READY" for c in body["candidates"])


@pytest.mark.anyio
async def test_endpoint_is_get_only(watch_client, monkeypatch):
    monkeypatch.setattr(exchange_tool, "get_klines", AsyncMock(return_value=_flat_klines()))
    path = _WATCH_PATH.format(pid=uuid4())

    for method in ("post", "put", "patch", "delete"):
        resp = await getattr(watch_client, method)(path)
        assert resp.status_code == 405, f"{method.upper()} should not be allowed"


@pytest.mark.anyio
async def test_endpoint_never_calls_order_or_dispatch_path(watch_client, monkeypatch):
    monkeypatch.setattr(exchange_tool, "get_klines", AsyncMock(return_value=_flat_klines()))

    # Any attempt to place/cancel an order would raise — proving the read-only path.
    def _boom(*_a, **_k):  # pragma: no cover - must never be invoked
        raise AssertionError("order/cancel path must never be called by the watch endpoint")

    for name in ("place_order", "place_market_order", "cancel_order", "cancel_all_open_orders"):
        if hasattr(exchange_tool, name):
            monkeypatch.setattr(exchange_tool, name, _boom)

    resp = await watch_client.get(_WATCH_PATH.format(pid=uuid4()))
    assert resp.status_code == 200
