"""Phase 2B — DEMO mode boundary tests.

Proves the order boundary in ``exchange_tool.place_order``:
  * PAPER (local simulation) can NEVER reach ``_demo_execute`` / an exchange adapter.
  * PAPER + demo (the previously-dangerous mixed mode) is BLOCKED as a conflict.
  * DEMO + demo is order-capable and routes to ``_demo_execute`` (and never live).
  * Any mode conflict is blocked BEFORE any adapter call.
  * ``_demo_execute`` itself fails closed under local simulation (defense in depth).

No real order is ever placed — the paper/demo/exchange routes are replaced with mocks.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.tools import exchange_tool
from app.services.exchange_routing import RoutingValidation
from app.services.trading_mode import resolve_trading_mode


def _set_mode(monkeypatch, trading_mode: str, exchange_mode: str, *, live: str = "false") -> None:
    monkeypatch.setenv("TRADING_MODE", trading_mode)
    monkeypatch.setenv("EXCHANGE_MODE", exchange_mode)
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", live)


@pytest.fixture
def routes(monkeypatch):
    """Replace every real execution route with a sentinel so nothing hits the network."""
    paper = MagicMock(return_value={"execution_status": "FILLED", "route": "paper"})
    demo = AsyncMock(return_value={"execution_status": "FILLED", "route": "demo"})
    live = AsyncMock(return_value={"execution_status": "FILLED", "route": "live"})
    monkeypatch.setattr(exchange_tool, "_paper_execute", paper)
    monkeypatch.setattr(exchange_tool, "_demo_execute", demo)
    monkeypatch.setattr(exchange_tool, "_exchange_execute", live)
    monkeypatch.setattr(
        exchange_tool,
        "validate_demo_routing",
        lambda: RoutingValidation(passed=True, profile=None, errors=[]),
    )
    return paper, demo, live


async def _place(**over):
    kwargs: dict = {"symbol": "BTCUSDT", "side": "BUY", "amount": 0.01, "price": 50_000.0}
    kwargs.update(over)
    return await exchange_tool.place_order(**kwargs)


@pytest.mark.anyio
async def test_paper_paper_routes_to_paper_execute(monkeypatch, routes):
    paper, demo, live = routes
    _set_mode(monkeypatch, "PAPER", "paper")
    result = await _place()
    assert result["route"] == "paper"
    paper.assert_called_once()
    demo.assert_not_called()
    live.assert_not_called()


@pytest.mark.anyio
async def test_paper_demo_is_blocked_and_cannot_reach_demo_execute(monkeypatch, routes):
    paper, demo, live = routes
    _set_mode(monkeypatch, "PAPER", "demo")
    result = await _place()
    assert result["execution_status"] == "BLOCKED"
    assert "conflict" in result["error"].lower()
    demo.assert_not_called()
    paper.assert_not_called()
    live.assert_not_called()


@pytest.mark.anyio
async def test_demo_demo_routes_to_demo_execute_and_never_live(monkeypatch, routes):
    paper, demo, live = routes
    _set_mode(monkeypatch, "DEMO", "demo")
    result = await _place()
    assert result["route"] == "demo"
    demo.assert_awaited_once()
    paper.assert_not_called()
    live.assert_not_called()


@pytest.mark.anyio
async def test_conflict_blocks_before_any_adapter(monkeypatch, routes):
    paper, demo, live = routes
    # DEMO trading mode but live exchange mode → conflict, blocked before routing.
    _set_mode(monkeypatch, "DEMO", "live")
    result = await _place()
    assert result["execution_status"] == "BLOCKED"
    paper.assert_not_called()
    demo.assert_not_called()
    live.assert_not_called()


@pytest.mark.anyio
async def test_live_blocked_when_live_trading_disabled(monkeypatch, routes):
    paper, demo, live = routes
    _set_mode(monkeypatch, "LIVE", "live", live="false")
    result = await _place()
    assert result["execution_status"] == "BLOCKED"
    assert "LIVE_TRADING_ENABLED" in result["error"]
    live.assert_not_called()


@pytest.mark.anyio
async def test_live_disabled_does_not_block_demo(monkeypatch, routes):
    """LIVE_TRADING_ENABLED=false must gate only LIVE — DEMO still executes."""
    paper, demo, live = routes
    _set_mode(monkeypatch, "DEMO", "demo", live="false")
    result = await _place()
    assert result["route"] == "demo"
    demo.assert_awaited_once()


@pytest.mark.anyio
async def test_live_routes_when_enabled(monkeypatch, routes):
    paper, demo, live = routes
    _set_mode(monkeypatch, "LIVE", "live", live="true")
    result = await _place()
    assert result["route"] == "live"
    live.assert_awaited_once()


@pytest.mark.anyio
async def test_demo_execute_guard_fails_closed_under_local_simulation(monkeypatch):
    """Direct call to the real _demo_execute must refuse when resolved mode is paper."""
    _set_mode(monkeypatch, "PAPER", "paper")
    assert resolve_trading_mode().is_local_simulation is True
    result = await exchange_tool._demo_execute(
        symbol="BTCUSDT",
        side="BUY",
        amount=0.01,
        order_type="market",
        price=50_000.0,
        stop_loss=None,
        take_profits=None,
        notional_usdt=None,
        api_key=None,
        api_secret=None,
    )
    assert result["execution_status"] == "BLOCKED"
    assert "order-capable" in result["error"]
